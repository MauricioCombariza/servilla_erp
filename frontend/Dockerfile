# ── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Configuración nginx para SPA (react-router)
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    # La app y su número de versión nunca se guardan en el navegador: tras un despliegue\n\
    # se ve la versión nueva sin volver a iniciar sesión (src/components/AlDia.tsx)\n\
    location = /index.html {\n\
        add_header Cache-Control "no-cache";\n\
    }\n\
    location = /version.json {\n\
        add_header Cache-Control "no-store";\n\
    }\n\
    # Los archivos de /assets llevan hash en el nombre: no cambian nunca\n\
    location /assets/ {\n\
        add_header Cache-Control "public, max-age=31536000, immutable";\n\
    }\n\
    gzip on;\n\
    gzip_types text/plain text/css application/json application/javascript;\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80
