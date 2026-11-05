# flujo — servicio Go de escaneo de tulas y asignación

Atiende `/api/tulas`, `/api/asignacion-zonas`, `/api/asignacion-qr`, `/api/imile-sesion`,
`/api/flujo/*` y `/api/paquetes-despacho/{destino,base}` (nginx le manda solo esas rutas;
el resto sigue en FastAPI). Usa la misma base PostgreSQL y el mismo `JWT_SECRET` que el
backend. Las migraciones siguen en Alembic: arranca solo cuando la base tiene la `047`.

- **Escanear no espera a iMile**: la lectura se guarda y deja una tarea en `imile_tareas`.
- **iMile en paralelo**: un navegador Playwright con varias páginas (`IMILE_POOL_INGRESO`,
  `IMILE_POOL_ASIGNAR`); cada página es de un solo worker. Si la sesión se cae, se vuelve
  a entrar una sola vez para todos.
- **Sin señal**: el celular guarda cada operación con un `op_id` y la manda a
  `POST /api/flujo/sync`; reenviarla nunca duplica (`operaciones_cliente`).

## Pruebas

```bash
go test ./...                                  # unitarias
# Integración: base de pruebas con las migraciones (¡se BORRAN sus datos del flujo!)
FLUJO_TEST_DATABASE_URL=postgresql://servilla:...@localhost:5440/flujo_test go test -race -p 1 ./...
# Pool de Playwright contra el iMile falso de backend/tests/fake_imile.py
FAKE_IMILE_URL=http://127.0.0.1:NNNN FLUJO_TEST_DATABASE_URL=... \
  PLAYWRIGHT_DRIVER_PATH=~/.cache/ms-playwright-go/1.57.0 go test -race -run Pool ./internal/imile/
# Pantallas de punta a punta (FastAPI + Go + Vite + navegador)
cd ../backend && bash scripts/e2e_flujo_paquetes.sh
```

Para crear `flujo_test`: copiar el esquema de la base de desarrollo y aplicar Alembic
(`DATABASE_URL=...flujo_test uv run alembic upgrade head` desde `backend/`).

## Driver de Playwright

playwright-go `v0.5700.1` exige exactamente el driver **1.57.0**, y el CDN del que lo baja
(`playwright.azureedge.net`) ya no existe. Se arma desde npm, igual que en el `Dockerfile`:

```bash
D=~/.cache/ms-playwright-go/1.57.0 && mkdir -p $D && cd $D
npm pack playwright-core@1.57.0 && tar xzf playwright-core-1.57.0.tgz && rm playwright-core-1.57.0.tgz
cp "$(which node)" ./node && ./node package/cli.js install chromium
```

Al subir de versión playwright-go hay que cambiar también la versión de `playwright-core`
en el `Dockerfile` y aquí.
