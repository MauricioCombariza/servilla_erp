#!/usr/bin/env bash
# Despliegue en producción (/opt/servilla_erp). Lo llama GitHub Actions al unir algo a master
# (.github/workflows/deploy.yml) por ssh, con una llave que solo puede correr este script
# (command= en authorized_keys). También se puede correr a mano en el servidor.
#
# 1. Trae master y se vuelve a ejecutar con la versión nueva de este script.
# 2. Si cambian las migraciones, saca un respaldo de la base antes (el backend las aplica al arrancar).
# 3. Descarga de GHCR las imágenes de ese commit (las construye GitHub Actions: aquí NO se compila,
#    el VPS de 4 GB se quedaba sin memoria) y reinicia solo lo que cambió (backend / flujo / frontend / nginx).
# 4. Comprueba /health; si falla, termina con error (el workflow queda en rojo).
set -euo pipefail

REPO=/opt/servilla_erp
BACKUPS=/opt/backups
MIN_LIBRE_GB=3          # sin esto libre no se descarga (la imagen del backend pesa ~2,7 GB)
REGISTRO=ghcr.io
ESPERA_IMAGENES_MIN=15  # si master avanzó, las imágenes del commit nuevo pueden estar construyéndose
RESPALDOS_A_GUARDAR=3

# Borra SOLO imágenes del ERP que ya no usa ningún contenedor (las de commits anteriores y las
# viejas compiladas aquí, infra-*). Nunca `docker image prune -a`: en este VPS hay otros
# proyectos (apriltag-api, backend-jobs, ...) cuyas imágenes no se deben tocar.
limpiar_imagenes_erp() {
  local actual="${IMAGEN_TAG:-}"
  docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E '^(ghcr\.io/mauriciocombariza/servilla-[a-z]+|infra-(backend|frontend|flujo)):' \
    | grep -v ":${actual}\$" \
    | xargs -r docker rmi >/dev/null 2>&1 || true   # las que siguen en uso fallan y se quedan
  docker image prune -f >/dev/null   # solo las <none> colgadas
}

cd "$REPO"

if [ -z "${DEPLOY_ANTES:-}" ]; then
  export DEPLOY_ANTES
  DEPLOY_ANTES=$(git rev-parse HEAD)
  GIT_SSH_COMMAND="ssh -i /root/.ssh/github_deploy_servilla" git pull -q --ff-only origin master
  exec bash "$REPO/infra/deploy.sh" "$@"
fi

DESPUES=$(git rev-parse HEAD)
echo "Código: ${DEPLOY_ANTES:0:7} -> ${DESPUES:0:7}"

# GitHub Actions manda por stdin un token de solo lectura de GHCR que vence al terminar el job.
# A mano (sin stdin) se usa el `docker login ghcr.io` que ya tenga el servidor, si lo hay.
GHCR_TOKEN=""
if [ ! -t 0 ]; then
  read -r -t 5 GHCR_TOKEN || true
fi
if [ -n "$GHCR_TOKEN" ]; then
  printf '%s' "$GHCR_TOKEN" | docker login "$REGISTRO" -u servilla-deploy --password-stdin >/dev/null
  trap 'docker logout "$REGISTRO" >/dev/null 2>&1 || true' EXIT
fi

# Por ssh (llave de GitHub Actions) el argumento llega en SSH_ORIGINAL_COMMAND. Solo se acepta --todo
FORZAR=${1:-${SSH_ORIGINAL_COMMAND:-}}
if [ -n "$FORZAR" ] && [ "$FORZAR" != "--todo" ]; then
  echo "ERROR: argumento no permitido: $FORZAR (solo --todo)" >&2
  exit 2
fi
if [ "$FORZAR" = "--todo" ]; then
  CAMBIOS="backend/ flujo/ frontend/ infra/"
elif [ "$DEPLOY_ANTES" = "$DESPUES" ]; then
  echo "Nada nuevo en master: no se despliega"
  exit 0
else
  CAMBIOS=$(git diff --name-only "$DEPLOY_ANTES" "$DESPUES")
fi

SERVICIOS=()
grep -q '^backend/' <<<"$CAMBIOS" && SERVICIOS+=(backend)
grep -q '^flujo/' <<<"$CAMBIOS" && SERVICIOS+=(flujo)
grep -q '^frontend/' <<<"$CAMBIOS" && SERVICIOS+=(frontend)
grep -v '^infra/deploy.sh$' <<<"$CAMBIOS" | grep -q '^infra/' && SERVICIOS+=(backend flujo frontend nginx)
if [ "${#SERVICIOS[@]}" -eq 0 ]; then
  echo "Los cambios no tocan backend, flujo, frontend ni infra: no se despliega"
  exit 0
fi
mapfile -t SERVICIOS < <(printf '%s\n' "${SERVICIOS[@]}" | sort -u)
echo "Se despliega: ${SERVICIOS[*]}"

LIBRE_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
echo "Disco libre: ${LIBRE_GB} GB"
if [ "$LIBRE_GB" -lt "$MIN_LIBRE_GB" ]; then
  echo "Se limpian imágenes viejas del ERP y la caché de construcción por falta de espacio"
  docker builder prune -af >/dev/null
  limpiar_imagenes_erp
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
export IMAGEN_TAG="$DESPUES"
# De a un servicio: descargar, reiniciar y borrar la imagen anterior antes del siguiente.
# Así el disco nunca tiene que alojar todas las imágenes nuevas a la vez junto a las viejas.
# El backend va primero (sort): aplica las migraciones que espera flujo.
LIMITE=$(( $(date +%s) + ESPERA_IMAGENES_MIN * 60 ))
for SERVICIO in "${SERVICIOS[@]}"; do
  echo "Descargando $SERVICIO ($IMAGEN_TAG)..."
  until docker compose pull -q "$SERVICIO"; do
    if [ "$(date +%s)" -ge "$LIMITE" ]; then
      echo "ERROR: la imagen de $SERVICIO para ${DESPUES:0:7} no está en GHCR después de ${ESPERA_IMAGENES_MIN} min." >&2
      echo "Revisa el job 'construir' en GitHub Actions. Si GHCR no responde, se puede compilar aquí:" >&2
      echo "  cd $REPO/infra && IMAGEN_TAG=$DESPUES docker compose up -d --build --no-deps $SERVICIO" >&2
      exit 1
    fi
    echo "Aún no está (¿se está construyendo?); reintento en 30 s"
    sleep 30
  done
  docker compose up -d --no-build --no-deps "$SERVICIO"
  limpiar_imagenes_erp
done

echo "Esperando a que el backend responda (aplica migraciones al arrancar)..."
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    echo "OK: $(curl -fsS http://localhost:8080/health)"
    break
  fi
  sleep 2
done
if ! curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
  echo "ERROR: /health no responde después de 2 minutos. Últimas líneas del backend:" >&2
  docker logs --tail 40 servilla_backend >&2 || true
  exit 1
fi

# El servicio Go espera la migración que aplica el backend: se revisa después
echo "Esperando al servicio Go (flujo)..."
for _ in $(seq 1 60); do
  if docker exec servilla_flujo node -e "fetch('http://localhost:8090/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1; then
    echo "OK: flujo responde"
    docker ps --filter name=servilla_ --format '{{.Names}}: {{.Status}}'
    df -h / | tail -1
    exit 0
  fi
  sleep 2
done

echo "ERROR: flujo no responde después de 2 minutos. Últimas líneas:" >&2
docker logs --tail 40 servilla_flujo >&2 || true
exit 1
