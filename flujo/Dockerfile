# ── 1. Compilar el servicio ──────────────────────────────────────────────────
FROM golang:1.22.12-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/flujo ./cmd/flujo

# ── 2. Imagen final: node + driver de Playwright + Chromium ──────────────────
# playwright-go v0.5700.1 exige exactamente el driver 1.57.0 (node + playwright-core).
# El CDN del que lo bajaba playwright-go (azureedge) ya no existe: se arma desde npm.
FROM node:22.12.0-bookworm-slim
ENV PLAYWRIGHT_DRIVER_PATH=/opt/playwright-driver \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
WORKDIR /opt/playwright-driver
RUN npm pack playwright-core@1.57.0 --silent \
    && tar xzf playwright-core-1.57.0.tgz && rm playwright-core-1.57.0.tgz \
    && ln -s /usr/local/bin/node ./node \
    && ./node package/cli.js install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm
COPY --from=build /out/flujo /usr/local/bin/flujo
WORKDIR /app
EXPOSE 8090
CMD ["flujo"]
