# ── 1. Compilar ──────────────────────────────────────────────────────────────
FROM golang:1.22.12-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/replicador ./cmd/replicador

# ── 2. Imagen final: smbclient (el SCO solo habla SMB1) + el binario ─────────
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends smbclient ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/replicador /usr/local/bin/replicador
ARG APP_UID=10001
RUN groupadd --gid ${APP_UID} servilla \
    && useradd --uid ${APP_UID} --gid servilla --no-create-home --shell /usr/sbin/nologin servilla
USER servilla
ENTRYPOINT ["replicador"]
CMD ["-config", "/etc/replicador/replicador.json"]
