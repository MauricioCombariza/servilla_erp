#!/usr/bin/env bash
# Despliegue en producción (/opt/servilla_erp). Lo llama GitHub Actions al unir algo a master
# (.github/workflows/deploy.yml) por ssh, con una llave que solo puede correr este script
# (command= en authorized_keys). También se puede correr a mano en el servidor.
#
# 1. Trae master y se vuelve a ejecutar con la versión nueva de este script.
# 2. Si cambian las migraciones, saca un respaldo de la base antes (el backend las aplica al arrancar).
# 3. Reconstruye solo lo que cambió (backend / frontend / nginx) y limpia la caché de construcción.
# 4. Comprueba /health; si falla, termina con error (el workflow queda en rojo).
set -euo pipefail

REPO=/opt/servilla_erp
BACKUPS=/opt/backups
MIN_LIBRE_GB=3          # sin esto libre no se construye (la imagen del backend pesa ~2,7 GB)
RESPALDOS_A_GUARDAR=3

cd "$REPO"

if [ -z "${DEPLOY_ANTES:-}" ]; then
  export DEPLOY_ANTES
  DEPLOY_ANTES=$(git rev-parse HEAD)
  GIT_SSH_COMMAND="ssh -i /root/.ssh/github_deploy_servilla" git pull -q --ff-only origin master
  exec bash "$REPO/infra/deploy.sh" "$@"
fi

DESPUES=$(git rev-parse HEAD)
echo "Código: ${DEPLOY_ANTES:0:7} -> ${DESPUES:0:7}"

# Por ssh (llave de GitHub Actions) el argumento llega en SSH_ORIGINAL_COMMAND. Solo se acepta --todo
FORZAR=${1:-${SSH_ORIGINAL_COMMAND:-}}
if [ -n "$FORZAR" ] && [ "$FORZAR" != "--todo" ]; then
  echo "ERROR: argumento no permitido: $FORZAR (solo --todo)" >&2
  exit 2
fi
if [ "$FORZAR" = "--todo" ]; then
  CAMBIOS="backend/ frontend/ infra/"
elif [ "$DEPLOY_ANTES" = "$DESPUES" ]; then
  echo "Nada nuevo en master: no se despliega"
  exit 0
else
  CAMBIOS=$(git diff --name-only "$DEPLOY_ANTES" "$DESPUES")
fi

SERVICIOS=()
grep -q '^backend/' <<<"$CAMBIOS" && SERVICIOS+=(backend)
grep -q '^frontend/' <<<"$CAMBIOS" && SERVICIOS+=(frontend)
grep -v '^infra/deploy.sh$' <<<"$CAMBIOS" | grep -q '^infra/' && SERVICIOS+=(backend frontend nginx)
if [ "${#SERVICIOS[@]}" -eq 0 ]; then
  echo "Los cambios no tocan backend, frontend ni infra: no se despliega"
  exit 0
fi
mapfile -t SERVICIOS < <(printf '%s\n' "${SERVICIOS[@]}" | sort -u)
echo "Se despliega: ${SERVICIOS[*]}"

LIBRE_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "Disco libre: ${LIBRE_GB} GB"
if [ "$LIBRE_GB" -lt "$MIN_LIBRE_GB" ]; then
  echo "Se limpia la caché de construcción por falta de espacio"
  docker builder prune -af >/dev/null
  LIBRE_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  if [ "$LIBRE_GB" -lt "$MIN_LIBRE_GB" ]; then
    echo "ERROR: solo hay ${LIBRE_GB} GB libres (mínimo ${MIN_LIBRE_GB}). No se despliega." >&2
    exit 1
  fi
fi

if [ "$FORZAR" = "--todo" ] || grep -q '^backend/app/migrations/' <<<"$CAMBIOS"; then
  mkdir -p "$BACKUPS"
  RESPALDO="$BACKUPS/servilla_erp_$(date +%Y%m%d_%H%M%S)_deploy_${DESPUES:0:7}.dump"
  echo "Hay migraciones nuevas: respaldo de la base en $RESPALDO"
  docker exec servilla_pg pg_dump -U servilla -d servilla_erp -Fc > "$RESPALDO"
  # Solo los respaldos de despliegue automático se rotan; los manuales no se tocan
  ls -1t "$BACKUPS"/servilla_erp_*_deploy_*.dump | tail -n +$((RESPALDOS_A_GUARDAR + 1)) | xargs -r rm -f
fi

cd "$REPO/infra"
docker compose up -d --build --no-deps "${SERVICIOS[@]}"
docker builder prune -af >/dev/null
docker image prune -f >/dev/null

echo "Esperando a que el backend responda (aplica migraciones al arrancar)..."
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    echo "OK: $(curl -fsS http://localhost:8080/health)"
    docker ps --filter name=servilla_ --format '{{.Names}}: {{.Status}}'
    df -h / | tail -1
    exit 0
  fi
  sleep 2
done

echo "ERROR: /health no responde después de 2 minutos. Últimas líneas del backend:" >&2
docker logs --tail 40 servilla_backend >&2 || true
exit 1
