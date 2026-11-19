FROM python:3.12-slim

# Corre como usuario sin privilegios (Semgrep missing-user). UID 10001, el mismo de flujo:
# los dos escriben la sesión de iMile en el volumen compartido imile_secrets.
# infra/deploy.sh le pasa el volumen a ese dueño antes de reiniciar.
ARG APP_UID=10001
RUN groupadd --gid ${APP_UID} servilla \
    && useradd --uid ${APP_UID} --gid servilla --create-home --shell /usr/sbin/nologin servilla

# Navegadores de Playwright fuera de /root, para que el usuario servilla los encuentre
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instalar dependencias del sistema para asyncpg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

# Navegador para la automatización de iMile (app/services/imile_sesion.py) con sus
# librerías del sistema; sin esto Playwright no puede abrir Chromium en el servidor
RUN playwright install --with-deps chromium

COPY . .

# Lo único que escribe en /app es la sesión de iMile (volumen montado en /app/.secrets)
RUN mkdir -p /app/.secrets && chown servilla:servilla /app/.secrets

USER servilla

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
