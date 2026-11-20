-- Rol del replicador. Se corre UNA vez en el servidor, como el dueño de la base (servilla),
-- después de la migración 062 (esquema legacy). La clave NO va en el repositorio:
--   docker exec -i servilla_pg psql -U servilla -d servilla_erp \
--     -v clave="'$(openssl rand -base64 32)'" < replicador/sql/rol.sql
-- y esa misma clave va en REPLICADOR_DB_URL del equipo del replicador.

CREATE ROLE replicador LOGIN PASSWORD :clave CONNECTION LIMIT 4;

-- Solo el esquema legacy: crea sus tablas (una por archivo) y escribe estado y conciliación
GRANT USAGE, CREATE ON SCHEMA legacy TO replicador;
GRANT SELECT, INSERT, UPDATE ON legacy._archivos TO replicador;
GRANT SELECT, INSERT ON legacy._conciliacion TO replicador;
GRANT USAGE ON SEQUENCE legacy._conciliacion_id_seq TO replicador;

-- El backend (servilla) lee lo que cree el replicador
ALTER DEFAULT PRIVILEGES FOR ROLE replicador IN SCHEMA legacy GRANT SELECT ON TABLES TO servilla;

-- Nada fuera de legacy
REVOKE ALL ON SCHEMA public FROM replicador;
