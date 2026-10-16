#!/usr/bin/env bash
# Recorrido de punta a punta del flujo de paquetes (FLUJO.md) contra una BASE TEMPORAL
# y un iMile FALSO. No toca producción ni el iMile real.
#
#   1. Levanta un PostgreSQL 16 desechable (contenedor servilla_e2e_pg, puerto 5441)
#   2. Copia ahí la base local de desarrollo (contenedor servilla_pg) y aplica las migraciones
#   3. Levanta el backend (puerto 8010) y el frontend con Vite (puerto 5180) contra esa base
#   4. Corre las pruebas marcadas e2e (API + pantalla /subir-despacho en tamaño celular)
#   5. Apaga todo y borra el contenedor
#
# Uso (desde servilla_erp/backend):  bash scripts/e2e_flujo_paquetes.sh [--sin-pantalla] [-- args de pytest]
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$BACKEND_DIR/../frontend"
PG_CONTENEDOR=servilla_e2e_pg
PG_PUERTO=5441
BACKEND_PUERTO=8010
FRONTEND_PUERTO=5180
CON_PANTALLA=1
PYTEST_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sin-pantalla) CON_PANTALLA=0; shift ;;
    --) shift; PYTEST_ARGS=("$@"); break ;;
    *) echo "Opción desconocida: $1"; exit 2 ;;
  esac
done

LOG_DIR="$(mktemp -d)"
PIDS=()

limpiar() {
  for pid in "${PIDS[@]:-}"; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done
  docker rm -f "$PG_CONTENEDOR" >/dev/null 2>&1 || true
  echo "Logs del backend y el frontend: $LOG_DIR"
}
trap limpiar EXIT

esperar_http() {  # url, nombre
  for _ in $(seq 1 60); do
    curl -fs -o /dev/null "$1" && return 0
    sleep 1
  done
  echo "No respondió $2 ($1)"; return 1
}

# Todo lo que corre aquí apunta a la base temporal y a un iMile inexistente: aunque algo
# se saltara el iMile falso de las pruebas, no hay credenciales reales con qué entrar.
export DATABASE_URL="postgresql+asyncpg://e2e:e2e@localhost:$PG_PUERTO/servilla_e2e"
export JWT_SECRET="e2e-$(date +%s)"
export IMILE_USER="e2e-sin-credenciales"
export IMILE_PASS="e2e-sin-credenciales"
export IMILE_INGRESO_ACTIVO=false
export IMILE_SESION_STATE_PATH="$LOG_DIR/imile_sesion.json"
export ALLOWED_ORIGINS="http://localhost:$FRONTEND_PUERTO"

echo "▶ Base temporal ($PG_CONTENEDOR, puerto $PG_PUERTO)"
docker rm -f "$PG_CONTENEDOR" >/dev/null 2>&1 || true
docker run -d --name "$PG_CONTENEDOR" -e POSTGRES_USER=e2e -e POSTGRES_PASSWORD=e2e \
  -e POSTGRES_DB=servilla_e2e -p "$PG_PUERTO:5432" postgres:16 >/dev/null
for _ in $(seq 1 30); do
  docker exec "$PG_CONTENEDOR" pg_isready -U e2e -d servilla_e2e -q && break
  sleep 1
done
sleep 1

echo "▶ Copia de la base local de desarrollo (servilla_pg) + migraciones"
docker exec servilla_pg pg_dump -U servilla --no-owner --no-privileges servilla_erp \
  | docker exec -i "$PG_CONTENEDOR" psql -q -U e2e -d servilla_e2e -v ON_ERROR_STOP=1 >/dev/null
cd "$BACKEND_DIR"
uv run alembic upgrade head 2>&1 | tail -n 3

if [[ $CON_PANTALLA -eq 1 ]]; then
  echo "▶ Backend (puerto $BACKEND_PUERTO) y frontend (puerto $FRONTEND_PUERTO)"
  uv run uvicorn app.main:app --port "$BACKEND_PUERTO" >"$LOG_DIR/backend.log" 2>&1 &
  PIDS+=($!)
  (cd "$FRONTEND_DIR" && VITE_API_PROXY="http://localhost:$BACKEND_PUERTO" \
    npx vite --port "$FRONTEND_PUERTO" --strictPort >"$LOG_DIR/frontend.log" 2>&1) &
  PIDS+=($!)
  esperar_http "http://localhost:$BACKEND_PUERTO/docs" backend
  esperar_http "http://localhost:$FRONTEND_PUERTO/" frontend
  export E2E_FRONTEND_URL="http://localhost:$FRONTEND_PUERTO"
fi

echo "▶ Pruebas de punta a punta"
uv run pytest -m e2e -v -x -p no:cacheprovider "${PYTEST_ARGS[@]}"
