"""
Migración one-shot: MySQL logistica → PostgreSQL servilla_erp

Uso:
    cd backend
    python scripts/migrate_mysql.py [--dry-run] [--tabla clientes,personal,seriales]

Tablas soportadas (en orden de dependencias):
    clientes    → clientes
    personal    → personal
    seriales    → seriales_gestion (desde logistica.seriales_gestion)
    histo       → seriales_gestion (desde bases_web.histo — alternativa)

El script es idempotente: usa INSERT ... ON CONFLICT DO NOTHING.
"""

import argparse
import logging
import os
import sys
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config desde entorno ──────────────────────────────────────────────────────

MYSQL_CFG = {
    "host":     os.environ.get("MYSQL_HOST", "localhost"),
    "port":     int(os.environ.get("MYSQL_PORT", 3306)),
    "user":     os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "db_log":   os.environ.get("MYSQL_DB_LOGISTICA", "logistica"),
    "db_bw":    os.environ.get("MYSQL_DB_BASES_WEB", "bases_web"),
}

PG_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://servilla:servilla_dev@localhost:5440/servilla_erp",
).replace("+asyncpg", "")   # psycopg2 no usa +asyncpg

BATCH = 500  # filas por commit


# ── Helpers ───────────────────────────────────────────────────────────────────

@contextmanager
def mysql_cursor(database: str):
    try:
        import mysql.connector
    except ImportError:
        log.error("Instalar: pip install mysql-connector-python")
        sys.exit(1)

    conn = mysql.connector.connect(
        host=MYSQL_CFG["host"],
        port=MYSQL_CFG["port"],
        user=MYSQL_CFG["user"],
        password=MYSQL_CFG["password"],
        database=database,
        charset="utf8mb4",
    )
    cur = conn.cursor(dictionary=True)
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


@contextmanager
def pg_cursor():
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        log.error("Instalar: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn, cur
    finally:
        cur.close()
        conn.close()


def batched(iterable, n):
    it = list(iterable)
    for i in range(0, len(it), n):
        yield it[i : i + n]


# ── Migración: clientes ───────────────────────────────────────────────────────

def migrate_clientes(dry_run: bool):
    log.info("── clientes ──────────────────────────────────────────")
    with mysql_cursor(MYSQL_CFG["db_log"]) as my:
        my.execute("""
            SELECT id, nombre_empresa, nit, contacto_nombre, contacto_telefono,
                   contacto_email, direccion, ciudad, plazo_pago_dias,
                   activo, notas, fecha_creacion
            FROM clientes
            ORDER BY id
        """)
        rows = my.fetchall()

    log.info(f"  MySQL: {len(rows)} clientes")
    if dry_run or not rows:
        return

    with pg_cursor() as (conn, cur):
        inserted = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                cur.execute("""
                    INSERT INTO clientes
                        (nombre_empresa, nit, contacto_nombre, contacto_telefono,
                         contacto_email, direccion, ciudad, plazo_pago_dias,
                         activo, notas, fecha_creacion)
                    VALUES
                        (%(nombre_empresa)s, %(nit)s, %(contacto_nombre)s, %(contacto_telefono)s,
                         %(contacto_email)s, %(direccion)s, %(ciudad)s, %(plazo_pago_dias)s,
                         %(activo)s, %(notas)s, %(fecha_creacion)s)
                    ON CONFLICT (nit) DO NOTHING
                """, r)
                inserted += cur.rowcount
            conn.commit()
    log.info(f"  PostgreSQL: {inserted} insertados (resto ya existían)")


# ── Migración: personal ───────────────────────────────────────────────────────

def migrate_personal(dry_run: bool):
    log.info("── personal ──────────────────────────────────────────")
    with mysql_cursor(MYSQL_CFG["db_log"]) as my:
        my.execute("""
            SELECT id, codigo, nombre_completo, identificacion, telefono, email,
                   tipo_personal, banco, numero_cuenta, tipo_cuenta,
                   dia_pago, activo, observaciones, fecha_ingreso,
                   precio_local, precio_nacional, fecha_creacion
            FROM personal
            ORDER BY id
        """)
        rows = my.fetchall()

    log.info(f"  MySQL: {len(rows)} registros")
    if dry_run or not rows:
        return

    TIPOS_VALIDOS = {"mensajero", "alistamiento", "conductor", "courier_externo", "transportadora"}

    with pg_cursor() as (conn, cur):
        inserted = skipped = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                if r["tipo_personal"] not in TIPOS_VALIDOS:
                    log.warning(f"  Omitiendo personal id={r['id']}: tipo '{r['tipo_personal']}' no válido")
                    skipped += 1
                    continue
                cur.execute("""
                    INSERT INTO personal
                        (codigo, nombre_completo, identificacion, telefono, email,
                         tipo_personal, banco, numero_cuenta, tipo_cuenta,
                         dia_pago, activo, observaciones, fecha_ingreso,
                         precio_local, precio_nacional, fecha_creacion)
                    VALUES
                        (%(codigo)s, %(nombre_completo)s, %(identificacion)s, %(telefono)s, %(email)s,
                         %(tipo_personal)s, %(banco)s, %(numero_cuenta)s, %(tipo_cuenta)s,
                         %(dia_pago)s, %(activo)s, %(observaciones)s, %(fecha_ingreso)s,
                         %(precio_local)s, %(precio_nacional)s, %(fecha_creacion)s)
                    ON CONFLICT (codigo)        DO NOTHING
                """, r)
                inserted += cur.rowcount
            conn.commit()
    log.info(f"  PostgreSQL: {inserted} insertados, {skipped} omitidos")


# ── Migración: seriales_gestion (desde logistica) ────────────────────────────

def migrate_seriales(dry_run: bool):
    log.info("── seriales_gestion (desde logistica) ────────────────")
    with mysql_cursor(MYSQL_CFG["db_log"]) as my:
        my.execute("""
            SELECT serial, f_emi, f_esc, planilla, cod_men,
                   tipo_gestion, tipo_envio, ambito,
                   precio_cliente, precio_mensajero,
                   estado, origen, editado_manualmente, observaciones,
                   fecha_creacion
            FROM seriales_gestion
            ORDER BY f_esc, id
        """)
        rows = my.fetchall()

    log.info(f"  MySQL: {len(rows)} seriales")
    if dry_run or not rows:
        return

    _insertar_seriales(rows)


def migrate_histo(dry_run: bool):
    """Migra desde bases_web.histo cuando seriales_gestion no existe en MySQL."""
    log.info("── seriales_gestion (desde bases_web.histo) ──────────")
    with mysql_cursor(MYSQL_CFG["db_bw"]) as my:
        my.execute("""
            SELECT
                serial,
                fecha_emision   AS f_emi,
                fecha_escaner   AS f_esc,
                planilla,
                cod_mensajero   AS cod_men,
                tipo_gestion,
                'sobre'         AS tipo_envio,
                'bogota'        AS ambito,
                0               AS precio_cliente,
                0               AS precio_mensajero,
                'pendiente'     AS estado,
                'scanner'       AS origen,
                FALSE           AS editado_manualmente,
                NULL            AS observaciones,
                fecha_escaner   AS fecha_creacion
            FROM histo
            WHERE fecha_escaner IS NOT NULL
            ORDER BY fecha_escaner, id
        """)
        rows = my.fetchall()

    log.info(f"  bases_web.histo: {len(rows)} filas")
    if dry_run or not rows:
        return

    _insertar_seriales(rows)


def _insertar_seriales(rows):
    ESTADOS = {"pendiente", "liquidado", "facturado", "anulado", "en_revision"}
    TIPOS_G = {"Entrega", "Devolucion"}
    TIPOS_E = {"sobre", "paquete"}
    AMBITOS = {"bogota", "nacional"}

    with pg_cursor() as (conn, cur):
        inserted = skipped = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                # Normalizar / validar
                if r.get("tipo_gestion") not in TIPOS_G:
                    skipped += 1
                    continue
                r["tipo_envio"]  = r.get("tipo_envio")  if r.get("tipo_envio")  in TIPOS_E else "sobre"
                r["ambito"]      = r.get("ambito")      if r.get("ambito")      in AMBITOS else "bogota"
                r["estado"]      = r.get("estado")      if r.get("estado")      in ESTADOS else "pendiente"
                r["origen"]      = r.get("origen")      or "scanner"
                r["precio_cliente"]   = r.get("precio_cliente")   or 0
                r["precio_mensajero"] = r.get("precio_mensajero") or 0
                r["editado_manualmente"] = bool(r.get("editado_manualmente", False))

                cur.execute("""
                    INSERT INTO seriales_gestion
                        (serial, f_emi, f_esc, planilla, cod_men,
                         tipo_gestion, tipo_envio, ambito,
                         precio_cliente, precio_mensajero,
                         estado, origen, editado_manualmente, observaciones,
                         fecha_creacion)
                    VALUES
                        (%(serial)s, %(f_emi)s, %(f_esc)s, %(planilla)s, %(cod_men)s,
                         %(tipo_gestion)s, %(tipo_envio)s, %(ambito)s,
                         %(precio_cliente)s, %(precio_mensajero)s,
                         %(estado)s, %(origen)s, %(editado_manualmente)s, %(observaciones)s,
                         %(fecha_creacion)s)
                    ON CONFLICT (serial) DO NOTHING
                """, r)
                inserted += cur.rowcount
            conn.commit()
    log.info(f"  PostgreSQL: {inserted} insertados, {skipped} omitidos")


# ── Main ──────────────────────────────────────────────────────────────────────

TABLAS = {
    "clientes":  migrate_clientes,
    "personal":  migrate_personal,
    "seriales":  migrate_seriales,
    "histo":     migrate_histo,
}

def main():
    parser = argparse.ArgumentParser(description="Migración MySQL → PostgreSQL Servilla ERP")
    parser.add_argument(
        "--tabla",
        default="clientes,personal,seriales",
        help="Tablas a migrar separadas por coma. Opciones: clientes, personal, seriales, histo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo cuenta filas, no inserta nada",
    )
    args = parser.parse_args()

    tablas = [t.strip() for t in args.tabla.split(",")]
    desconocidas = [t for t in tablas if t not in TABLAS]
    if desconocidas:
        log.error(f"Tablas desconocidas: {desconocidas}. Opciones: {list(TABLAS)}")
        sys.exit(1)

    if args.dry_run:
        log.info("MODO DRY-RUN — no se escribirá nada en PostgreSQL")

    for tabla in tablas:
        try:
            TABLAS[tabla](args.dry_run)
        except Exception as e:
            log.error(f"Error migrando {tabla}: {e}")
            raise

    log.info("✓ Migración completada")


if __name__ == "__main__":
    main()
