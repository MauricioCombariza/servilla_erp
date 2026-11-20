# Replicador SCO → Postgres

Ola 1 de la migración del FoxPro. Lee las tablas vivas del SCO (`.his`/`.dbf`) **por Samba, en solo lectura**, y las copia al esquema `legacy` de Postgres. Cada pasada manda solo los registros nuevos, cambiados o borrados y concilia (conteo + suma de hashes). Diseño completo: `actualizacion_programa/docs/diseno_ola1_replicador.md`.

```
SCO (Samba SMB1, 139) ──► replicador (equipo Linux en la LAN) ──WireGuard──► Postgres (legacy.*)
```

## Cómo funciona

| Paso | Qué hace |
|---|---|
| 1 | `smbclient ls` del archivo: si el tamaño y la fecha no cambiaron, no lo lee |
| 2 | `smbclient get` a una FIFO: lo lee en streaming, sin escribirlo en disco |
| 3 | Por registro, hash FNV-64 de los bytes crudos; solo los que cambiaron van a Postgres (`COPY` + upsert) |
| 4 | Si el archivo quedó más corto (PACK en el FoxPro), recarga la tabla completa |
| 5 | Filtro opcional por fecha (`f_emi >= 2025-01-01`): lo anterior no sale de la oficina |
| 6 | Concilia y guarda el resultado en `legacy._conciliacion`; el estado en `legacy._archivos` |

- Una tabla por archivo (`legacy.guia2601`, `legacy.lote_apl`…), creada sola con los campos del DBF más `_recno`, `_hash`, `_borrado`, `_crudo` (valores imposibles, como fechas del año 9620) y `_visto_en`.
- Textos en Windows 1252. Fechas fuera de 1900–2100 → `NULL` y el valor original en `_crudo`.
- Si la conciliación no cuadra, no guarda la marca: la siguiente pasada vuelve a leer y completa.

## Instalación (equipo de la LAN)

1. **SCO**: usuario `replica` y recursos de solo lectura (`docs/diseno_ola1_replicador.md` §3).
2. **Servidor**: migración 062 (esquema `legacy`) y el rol con `sql/rol.sql`; Postgres escuchando en la IP del túnel WireGuard.
3. **Equipo**: Docker + WireGuard. En esta carpeta:
   - `replicador.json` (copia de `replicador.ejemplo.json`)
   - `smb_auth` con `username = replica`, `password = …`, `domain = WORKGROUP` (`chmod 600`)
   - `.env` con `REPLICADOR_DB_URL=postgres://replicador:<clave>@<IP túnel>:5432/servilla_erp`
   - `docker compose up -d --build`

Una sola pasada, para probar: `docker compose run --rm replicador -config /etc/replicador/replicador.json -una-vez`.

## Desarrollo

```
go vet ./... && go test ./...
REPLICADOR_TEST_DB=postgres://usuario:clave@localhost:5440/ci_prueba go test ./internal/destino/   # contra Postgres
```

Las pruebas usan DBF sintéticos (`internal/dbf/dbftest`) y un `smbclient` falso; nunca datos reales.
