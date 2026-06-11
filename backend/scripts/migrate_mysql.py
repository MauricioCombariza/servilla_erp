"""
Migración MySQL → PostgreSQL Servilla ERP

Uso:
    cd backend
    python scripts/migrate_mysql.py [--dry-run] [--tabla clientes,personal,histo,mensajeros]

Tablas soportadas (en orden de dependencias):
    clientes          → migra logistica.clientes
    personal          → migra logistica.personal
    seriales          → migra logistica.seriales_gestion (con precios)
    histo             → migra bases_web.histo desde HISTO_FECHA_DESDE hasta HISTO_FECHA_HASTA
    histo-incremental → migra bases_web.histo desde el último f_esc ya migrado hasta hoy
    mensajeros        → resuelve cod_men → mensajero_id (ejecutar al final)
    tipo_gestion      → corrige tipo_gestion en seriales históricos de histo (Entrega/Devolucion)
    precios           → activa precios_cliente 2026 (activo=false → true) para backfill
    imile             → migra imile.paquetes (ene–abr 2026) a seriales_gestion

Idempotente: usa INSERT ... ON CONFLICT DO NOTHING.

Variables de entorno requeridas:
    DATABASE_URL              URL completa de PostgreSQL (ver .env.example)

Variables de entorno para MySQL logistica:
    MYSQL_HOST                (default: 127.0.0.1)
    MYSQL_PORT                (default: 3306)
    MYSQL_USER                (default: root)
    MYSQL_PASSWORD            (requerida)
    MYSQL_DB_LOGISTICA        (default: logistica)

Variables adicionales para bases_web.histo:
    MYSQL_HOST_BW             (default: 186.180.15.66)
    MYSQL_PORT_BW             (default: 12539)
    MYSQL_USER_BW             (default: servilla_remoto)
    MYSQL_PASSWORD_BW         (requerida)
    MYSQL_DB_BW               (default: bases_web)
    HISTO_FECHA_DESDE         (default: 2026-01-01)
    HISTO_FECHA_HASTA         (default: hoy)

Variables para imile.paquetes:
    MYSQL_DB_IMILE            (default: imile)
    IMILE_FECHA_DESDE         (default: 2026-01-01)
    IMILE_FECHA_HASTA         (default: 2026-04-30)
"""

import argparse
import logging
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

MYSQL_LOG = {
    "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port":     int(os.environ.get("MYSQL_PORT", 3306)),
    "user":     os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DB_LOGISTICA", "logistica"),
}

MYSQL_BW = {
    "host":     os.environ.get("MYSQL_HOST_BW", "186.180.15.66"),
    "port":     int(os.environ.get("MYSQL_PORT_BW", 12539)),
    "user":     os.environ.get("MYSQL_USER_BW", "servilla_remoto"),
    "password": os.environ.get("MYSQL_PASSWORD_BW", ""),
    "database": os.environ.get("MYSQL_DB_BW", "bases_web"),
}

_hoy = date.today().isoformat()
HISTO_DESDE = os.environ.get("HISTO_FECHA_DESDE", "2026-01-01")
HISTO_HASTA = os.environ.get("HISTO_FECHA_HASTA", _hoy)

MYSQL_IMILE = {
    "host":     os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port":     int(os.environ.get("MYSQL_PORT", 3306)),
    "user":     os.environ.get("MYSQL_USER", "root"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DB_IMILE", "imile"),
}
IMILE_DESDE = os.environ.get("IMILE_FECHA_DESDE", "2026-01-01")
IMILE_HASTA = os.environ.get("IMILE_FECHA_HASTA", "2026-04-30")

_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    log.error("DATABASE_URL no configurada. Agrega DATABASE_URL al archivo .env")
    sys.exit(1)
PG_DSN = _db_url.replace("+asyncpg", "")

BATCH = 500


# ── Helpers ───────────────────────────────────────────────────────────────────

@contextmanager
def mysql_conn(cfg: dict, buffered: bool = True):
    try:
        import mysql.connector
    except ImportError:
        log.error("Instalar: pip install mysql-connector-python")
        sys.exit(1)
    conn = mysql.connector.connect(charset="utf8mb4", **cfg)
    cur = conn.cursor(dictionary=True, buffered=buffered)
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


@contextmanager
def pg_conn():
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


def batched(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i: i + n]


def parse_fecha(valor) -> date | None:
    """Convierte fechas en varios formatos a date. Devuelve None si inválida."""
    if valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        return valor if isinstance(valor, date) else valor.date()
    s = str(valor).strip()
    if not s or s in ("0000-00-00", "0000.00.00", "00.00.0000"):
        return None
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ── Migración: clientes ───────────────────────────────────────────────────────

def migrate_clientes(dry_run: bool):
    log.info("── clientes ──────────────────────────────────────────")
    with mysql_conn(MYSQL_LOG) as my:
        my.execute("""
            SELECT id, nombre_empresa, nit, contacto_nombre, contacto_telefono,
                   contacto_email, direccion, ciudad, plazo_pago_dias,
                   activo, notas, fecha_creacion
            FROM clientes ORDER BY id
        """)
        rows = my.fetchall()
    log.info(f"  MySQL: {len(rows)} clientes")
    if dry_run or not rows:
        return
    with pg_conn() as (conn, cur):
        inserted = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                nit = (r.get("nit") or "").strip() or f"SIN_NIT_{r['id']}"
                cur.execute("""
                    INSERT INTO clientes
                        (nombre_empresa, nit, contacto_nombre, contacto_telefono,
                         contacto_email, direccion, ciudad, plazo_pago_dias,
                         activo, notas, fecha_creacion)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (nit) DO NOTHING
                """, (
                    r["nombre_empresa"], nit,
                    r.get("contacto_nombre"), r.get("contacto_telefono"),
                    r.get("contacto_email"), r.get("direccion"),
                    r.get("ciudad"), r.get("plazo_pago_dias") or 30,
                    bool(r.get("activo", True)),
                    r.get("notas"), r.get("fecha_creacion"),
                ))
                inserted += cur.rowcount
            conn.commit()
    log.info(f"  PostgreSQL: {inserted} insertados")


# ── Migración: personal ───────────────────────────────────────────────────────

def migrate_personal(dry_run: bool):
    log.info("── personal ──────────────────────────────────────────")
    with mysql_conn(MYSQL_LOG) as my:
        my.execute("""
            SELECT codigo, nombre_completo, identificacion, telefono, email,
                   tipo_personal, banco, numero_cuenta, tipo_cuenta,
                   dia_pago, activo, observaciones, fecha_ingreso,
                   COALESCE(tarifa_entrega_local,  precio_local,    0) AS precio_local,
                   COALESCE(tarifa_entrega_nacional, precio_nacional, 0) AS precio_nacional,
                   fecha_creacion
            FROM personal ORDER BY id
        """)
        rows = my.fetchall()
    log.info(f"  MySQL: {len(rows)} registros")
    if dry_run or not rows:
        return

    TIPOS_VALIDOS = {"mensajero", "alistamiento", "conductor", "courier_externo", "transportadora"}
    with pg_conn() as (conn, cur):
        inserted = skipped = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                if r.get("tipo_personal") not in TIPOS_VALIDOS:
                    log.warning(f"  Omitiendo código {r['codigo']}: tipo '{r['tipo_personal']}' no válido")
                    skipped += 1
                    continue
                ident = (r.get("identificacion") or "").strip() or f"SIN_ID_{r['codigo']}"
                cur.execute("""
                    INSERT INTO personal
                        (codigo, nombre_completo, identificacion, telefono, email,
                         tipo_personal, banco, numero_cuenta, tipo_cuenta,
                         dia_pago, activo, observaciones, fecha_ingreso,
                         precio_local, precio_nacional, fecha_creacion)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (codigo) DO UPDATE SET
                        precio_local    = EXCLUDED.precio_local,
                        precio_nacional = EXCLUDED.precio_nacional
                """, (
                    r["codigo"], r["nombre_completo"], ident,
                    r.get("telefono"), r.get("email"),
                    r["tipo_personal"],
                    r.get("banco"), r.get("numero_cuenta"), r.get("tipo_cuenta"),
                    r.get("dia_pago") or 8,
                    bool(r.get("activo", True)),
                    r.get("observaciones"),
                    parse_fecha(r.get("fecha_ingreso")),
                    r.get("precio_local"), r.get("precio_nacional"),
                    r.get("fecha_creacion"),
                ))
                inserted += cur.rowcount
            conn.commit()
    log.info(f"  PostgreSQL: {inserted} insertados, {skipped} omitidos")


# ── Migración: seriales desde logistica.seriales_gestion (Mayo en adelante) ──

def migrate_seriales(dry_run: bool):
    """
    Importa logistica.seriales_gestion al ERP.
    MySQL usa 'fecha_escaner' (= f_esc en ERP).
    Preserva precios, cod_men, estado y editado_manualmente.
    """
    log.info("── seriales_gestion (desde logistica) ────────────────")
    with mysql_conn(MYSQL_LOG) as my:
        my.execute("""
            SELECT
                serial,
                NULL                AS f_emi,
                fecha_escaner       AS f_esc_raw,
                planilla,
                cod_men,
                tipo_gestion,
                tipo_envio,
                ambito,
                precio_cliente,
                precio_mensajero,
                estado,
                origen,
                editado_manualmente,
                observaciones,
                fecha_creacion,
                cliente             AS cliente_nombre,
                cliente_id          AS cliente_id_mysql
            FROM seriales_gestion
            WHERE fecha_escaner IS NOT NULL
            ORDER BY fecha_escaner, id
        """)
        rows = my.fetchall()
    log.info(f"  MySQL: {len(rows)} seriales")
    if dry_run or not rows:
        return

    # Construir mapa cliente_nombre → cliente_id de PostgreSQL
    cliente_map = _build_cliente_map()

    _insertar_seriales(rows, cliente_map=cliente_map, fecha_campo="f_esc_raw")


# ── Migración: seriales desde bases_web.histo (Enero-Abril) ──────────────────

def migrate_histo(dry_run: bool):
    """
    Importa desde bases_web.histo el rango HISTO_DESDE..HISTO_HASTA.
    Usa cursor no-buffered + fetchmany para evitar cargar 1M+ filas en memoria.
    """
    desde_histo = HISTO_DESDE.replace("-", ".")
    hasta_histo = HISTO_HASTA.replace("-", ".")

    log.info(f"── bases_web.histo ({HISTO_DESDE} → {HISTO_HASTA}) ─────────────")

    if dry_run:
        # Para dry-run sí contamos con buffered (más rápido)
        with mysql_conn(MYSQL_BW) as my:
            my.execute(
                "SELECT COUNT(*) AS n FROM histo WHERE serial IS NOT NULL "
                "AND f_esc IS NOT NULL AND f_esc BETWEEN %s AND %s "
                "AND f_esc NOT LIKE '%%Entr%%' AND f_esc NOT LIKE '%%Devo%%' "
                "AND cod_men NOT IN (SELECT cod_men FROM mensajeros WHERE nombre IN ('Lecta', 'Prindel'))",
                (desde_histo, hasta_histo)
            )
            total = my.fetchone()["n"]
        log.info(f"  bases_web.histo: {total} filas (dry-run, excluye Lecta/Prindel)")
        return

    cliente_map = _build_cliente_map()

    # cursor no-buffered para streaming — evita traer todo a RAM de una vez
    with mysql_conn(MYSQL_BW, buffered=False) as my:
        my.execute("""
            SELECT
                serial,
                f_emi               AS f_emi_raw,
                f_esc               AS f_esc_raw,
                planilla,
                cod_men,
                no_entidad          AS cliente_nombre,
                ret_esc,
                motivo,
                ciudad              AS ciudad_raw,
                'sobre'             AS tipo_envio,
                0                   AS precio_cliente,
                0                   AS precio_mensajero,
                'pendiente'         AS estado,
                'scanner'           AS origen,
                NULL                AS observaciones,
                NULL                AS fecha_creacion,
                NULL                AS cliente_id_mysql
            FROM histo
            WHERE serial IS NOT NULL
              AND f_esc IS NOT NULL
              AND f_esc BETWEEN %s AND %s
              AND f_esc NOT LIKE '%%Entr%%'
              AND f_esc NOT LIKE '%%Devo%%'
              AND cod_men NOT IN (
                  SELECT cod_men FROM mensajeros
                  WHERE nombre IN ('Lecta', 'Prindel')
              )
        """, (desde_histo, hasta_histo))

        ESTADOS = {"pendiente", "liquidado", "facturado", "anulado", "en_revision"}
        TIPOS_E  = {"sobre", "paquete"}
        AMBITOS  = {"bogota", "nacional"}

        total_inserted = total_skipped = total_bad = total_motivo21 = 0
        chunk_num = 0

        with pg_conn() as (conn, cur):
            while True:
                rows = my.fetchmany(BATCH)
                if not rows:
                    break
                chunk_num += 1

                for r in rows:
                    f_esc = parse_fecha(r.get("f_esc_raw"))
                    if f_esc is None:
                        total_bad += 1
                        continue
                    f_emi = parse_fecha(r.get("f_emi_raw"))
                    ret   = (r.get("ret_esc") or "").strip()
                    tipo_g = "Devolucion" if ret else "Entrega"
                    tipo_e = r.get("tipo_envio") if r.get("tipo_envio") in TIPOS_E else "sobre"
                    # Determinar ambito desde campo ciudad: Bogotá → 'bogota', resto → 'nacional'
                    _BOGOTA = {"BOGOTA", "BOGOTÁ", "BOGOTA D.C.", "BOGOTÁ D.C.",
                                "SANTA FE DE BOGOTA", "SANTA FE DE BOGOTÁ"}
                    ciudad  = (r.get("ciudad_raw") or "").strip().upper()
                    ambito  = "bogota" if ciudad in _BOGOTA else "nacional"
                    estado = r.get("estado")     if r.get("estado")     in ESTADOS else "pendiente"
                    nombre_cl  = (r.get("cliente_nombre") or "").strip().lower()
                    cliente_id = cliente_map.get(nombre_cl)
                    fecha_creacion = r.get("fecha_creacion") or f_esc

                    # Motivo 21 → devolución sin cobro; editado_manualmente protege
                    # el precio $0 frente a recalculaciones futuras de precios
                    motivo = str(r.get("motivo") or "").strip()
                    es_motivo21 = (motivo == "21")
                    if es_motivo21:
                        total_motivo21 += 1

                    cur.execute("""
                        INSERT INTO seriales_gestion
                            (serial, f_emi, f_esc, planilla, cod_men,
                             cliente_id, tipo_gestion, tipo_envio, ambito,
                             precio_cliente, precio_mensajero,
                             estado, origen, editado_manualmente, observaciones,
                             fecha_creacion)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (serial) DO UPDATE SET
                            ambito       = EXCLUDED.ambito,
                            tipo_gestion = EXCLUDED.tipo_gestion,
                            precio_cliente  = EXCLUDED.precio_cliente,
                            precio_mensajero = EXCLUDED.precio_mensajero
                        WHERE seriales_gestion.editado_manualmente = FALSE
                    """, (
                        r["serial"], f_emi, f_esc,
                        r.get("planilla") or "", r.get("cod_men") or "",
                        cliente_id, tipo_g, tipo_e, ambito,
                        0, 0, estado, "scanner", es_motivo21,
                        r.get("observaciones"), fecha_creacion,
                    ))
                    total_inserted += cur.rowcount

                conn.commit()
                if chunk_num % 10 == 0:
                    log.info(f"  ... chunk {chunk_num}: {total_inserted} insertados hasta ahora")

    log.info(
        f"  PostgreSQL: {total_inserted} insertados, {total_skipped} omitidos, "
        f"{total_bad} sin fecha, {total_motivo21} motivo-21 (precio=0 protegido)"
    )


# ── Helpers internos ──────────────────────────────────────────────────────────

def _build_cliente_map() -> dict:
    """
    Devuelve {nombre_lower: cliente_id} desde PostgreSQL.
    Incluye variantes conocidas para cubrir diferencias de nombre entre histo y ERP.
    """
    ALIASES = {
        # histo no_entidad lower → nombre_empresa en ERP (lower)
        "banco caja social":         "banco caja social",
        "fiduciaria caja social":    "banco caja social",
        "vehigroup sas":             "vehigrupo sas",
        "-vehigroup sas":            "vehigrupo sas",
        "leonisa":                   "leonisa",
        "pronticourrier express sa": "pronticourier express s.a.s",
        "pronticourier express sa":  "pronticourier express s.a.s",
        "imile":                     "imile sas",
        "imile sas":                 "imile sas",
    }
    with pg_conn() as (_, cur):
        cur.execute("SELECT id, nombre_empresa FROM clientes")
        base = {r["nombre_empresa"].lower(): r["id"] for r in cur.fetchall()}
    # Expandir con aliases
    result = dict(base)
    for alias, canonical in ALIASES.items():
        if canonical in base:
            result[alias] = base[canonical]
    return result


def _insertar_seriales(rows, *, cliente_map: dict, fecha_campo: str, fecha_emi_campo: str = "f_emi"):
    ESTADOS = {"pendiente", "liquidado", "facturado", "anulado", "en_revision"}
    TIPOS_G = {"Entrega", "Devolucion"}
    TIPOS_E = {"sobre", "paquete"}
    AMBITOS = {"bogota", "nacional"}

    with pg_conn() as (conn, cur):
        inserted = skipped = bad_date = 0
        for batch in batched(rows, BATCH):
            for r in batch:
                # Parsear fechas
                f_esc = parse_fecha(r.get(fecha_campo))
                if f_esc is None:
                    bad_date += 1
                    continue

                f_emi = parse_fecha(r.get(fecha_emi_campo)) if fecha_emi_campo != "f_emi" else parse_fecha(r.get("f_emi"))

                # Validar tipo_gestion
                if r.get("tipo_gestion") not in TIPOS_G:
                    skipped += 1
                    continue

                # Normalizar enums
                tipo_envio = r.get("tipo_envio") if r.get("tipo_envio") in TIPOS_E else "sobre"
                ambito     = r.get("ambito")     if r.get("ambito")     in AMBITOS else "bogota"
                estado     = r.get("estado")     if r.get("estado")     in ESTADOS else "pendiente"
                origen     = r.get("origen")     or "scanner"
                precio_c   = float(r.get("precio_cliente")   or 0)
                precio_m   = float(r.get("precio_mensajero") or 0)
                editado    = bool(r.get("editado_manualmente", False))

                # Resolver cliente_id
                nombre_cl = (r.get("cliente_nombre") or "").strip().lower()
                cliente_id = cliente_map.get(nombre_cl)

                fecha_creacion = r.get("fecha_creacion") or f_esc
                cur.execute("""
                    INSERT INTO seriales_gestion
                        (serial, f_emi, f_esc, planilla, cod_men,
                         cliente_id,
                         tipo_gestion, tipo_envio, ambito,
                         precio_cliente, precio_mensajero,
                         estado, origen, editado_manualmente, observaciones,
                         fecha_creacion)
                    VALUES
                        (%s, %s, %s, %s, %s,
                         %s,
                         %s, %s, %s,
                         %s, %s,
                         %s, %s, %s, %s,
                         %s)
                    ON CONFLICT (serial) DO NOTHING
                """, (
                    r["serial"], f_emi, f_esc,
                    r.get("planilla") or "", r.get("cod_men") or "",
                    cliente_id,
                    r["tipo_gestion"], tipo_envio, ambito,
                    precio_c, precio_m,
                    estado, origen, editado,
                    r.get("observaciones"),
                    fecha_creacion,
                ))
                inserted += cur.rowcount
            conn.commit()

        log.info(f"  PostgreSQL: {inserted} insertados, {skipped} omitidos (tipo inválido), {bad_date} sin fecha")


# ── Sincronización incremental: bases_web.histo desde último f_esc migrado ───

def migrate_histo_incremental(dry_run: bool):
    """
    Migra registros de bases_web.histo publicados después del último f_esc
    ya existente en seriales_gestion. Útil para actualizaciones periódicas.
    """
    log.info("── histo incremental ─────────────────────────────────")

    with pg_conn() as (_, cur):
        cur.execute("SELECT MAX(f_esc) AS ultimo FROM seriales_gestion")
        row = cur.fetchone()
        ultimo = row["ultimo"] if row else None

    if ultimo is None:
        log.info("  No hay datos en seriales_gestion. Usa --tabla histo para la carga inicial.")
        return

    desde = ultimo.isoformat()
    hasta = date.today().isoformat()
    log.info(f"  Rango incremental: {desde} → {hasta}")

    desde_histo = desde.replace("-", ".")
    hasta_histo = hasta.replace("-", ".")

    if dry_run:
        with mysql_conn(MYSQL_BW) as my:
            my.execute(
                "SELECT COUNT(*) AS n FROM histo WHERE serial IS NOT NULL "
                "AND f_esc IS NOT NULL AND f_esc > %s AND f_esc <= %s "
                "AND f_esc NOT LIKE '%%Entr%%' AND f_esc NOT LIKE '%%Devo%%' "
                "AND cod_men NOT IN (SELECT cod_men FROM mensajeros WHERE nombre IN ('Lecta', 'Prindel'))",
                (desde_histo, hasta_histo)
            )
            total = my.fetchone()["n"]
        log.info(f"  bases_web.histo: {total} filas nuevas (dry-run, excluye Lecta/Prindel)")
        return

    cliente_map = _build_cliente_map()

    with mysql_conn(MYSQL_BW, buffered=False) as my:
        my.execute("""
            SELECT
                serial,
                f_emi               AS f_emi_raw,
                f_esc               AS f_esc_raw,
                planilla,
                cod_men,
                no_entidad          AS cliente_nombre,
                ret_esc,
                motivo,
                ciudad              AS ciudad_raw,
                'sobre'             AS tipo_envio,
                0                   AS precio_cliente,
                0                   AS precio_mensajero,
                'pendiente'         AS estado,
                'scanner'           AS origen,
                NULL                AS observaciones,
                NULL                AS fecha_creacion,
                NULL                AS cliente_id_mysql
            FROM histo
            WHERE serial IS NOT NULL
              AND f_esc IS NOT NULL
              AND f_esc > %s AND f_esc <= %s
              AND f_esc NOT LIKE '%%Entr%%'
              AND f_esc NOT LIKE '%%Devo%%'
              AND cod_men NOT IN (
                  SELECT cod_men FROM mensajeros
                  WHERE nombre IN ('Lecta', 'Prindel')
              )
        """, (desde_histo, hasta_histo))

        ESTADOS = {"pendiente", "liquidado", "facturado", "anulado", "en_revision"}
        TIPOS_E  = {"sobre", "paquete"}
        AMBITOS  = {"bogota", "nacional"}

        total_inserted = total_bad = total_motivo21 = 0

        with pg_conn() as (conn, cur):
            while True:
                rows = my.fetchmany(BATCH)
                if not rows:
                    break
                for r in rows:
                    f_esc = parse_fecha(r.get("f_esc_raw"))
                    if f_esc is None:
                        total_bad += 1
                        continue
                    f_emi  = parse_fecha(r.get("f_emi_raw"))
                    ret    = (r.get("ret_esc") or "").strip()
                    tipo_g = "Devolucion" if ret else "Entrega"
                    tipo_e = r.get("tipo_envio") if r.get("tipo_envio") in TIPOS_E else "sobre"
                    # Determinar ambito desde campo ciudad: Bogotá → 'bogota', resto → 'nacional'
                    _BOGOTA = {"BOGOTA", "BOGOTÁ", "BOGOTA D.C.", "BOGOTÁ D.C.",
                                "SANTA FE DE BOGOTA", "SANTA FE DE BOGOTÁ"}
                    ciudad  = (r.get("ciudad_raw") or "").strip().upper()
                    ambito  = "bogota" if ciudad in _BOGOTA else "nacional"
                    estado = r.get("estado")     if r.get("estado")     in ESTADOS else "pendiente"
                    nombre_cl  = (r.get("cliente_nombre") or "").strip().lower()
                    cliente_id = cliente_map.get(nombre_cl)
                    fecha_creacion = r.get("fecha_creacion") or f_esc

                    motivo = str(r.get("motivo") or "").strip()
                    es_motivo21 = (motivo == "21")
                    if es_motivo21:
                        total_motivo21 += 1

                    cur.execute("""
                        INSERT INTO seriales_gestion
                            (serial, f_emi, f_esc, planilla, cod_men,
                             cliente_id, tipo_gestion, tipo_envio, ambito,
                             precio_cliente, precio_mensajero,
                             estado, origen, editado_manualmente, observaciones,
                             fecha_creacion)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (serial) DO UPDATE SET
                            ambito       = EXCLUDED.ambito,
                            tipo_gestion = EXCLUDED.tipo_gestion,
                            precio_cliente  = EXCLUDED.precio_cliente,
                            precio_mensajero = EXCLUDED.precio_mensajero
                        WHERE seriales_gestion.editado_manualmente = FALSE
                    """, (
                        r["serial"], f_emi, f_esc,
                        r.get("planilla") or "", r.get("cod_men") or "",
                        cliente_id, tipo_g, tipo_e, ambito,
                        0, 0, estado, "scanner", es_motivo21,
                        r.get("observaciones"), fecha_creacion,
                    ))
                    total_inserted += cur.rowcount
                conn.commit()

    log.info(
        f"  PostgreSQL: {total_inserted} nuevos insertados, {total_bad} sin fecha válida, "
        f"{total_motivo21} motivo-21 (precio=0 protegido)"
    )
    if total_inserted > 0:
        log.info("  Ejecuta --tabla mensajeros para resolver mensajero_id en los nuevos registros")


# ── Activar precios históricos 2026 en precios_cliente ───────────────────────

def activar_precios_historicos(dry_run: bool):
    """
    Marca activo=TRUE en precios_cliente para registros de 2026 cuya
    vigencia_hasta >= vigencia_desde (es decir, registros válidos).
    Deja inactivos los que tienen vigencia_hasta anterior a vigencia_desde
    (datos inconsistentes ingresados por error).
    """
    log.info("── activar precios históricos 2026 ───────────────────")
    if dry_run:
        with pg_conn() as (conn, cur):
            cur.execute("""
                SELECT COUNT(*) AS n FROM precios_cliente
                WHERE activo = FALSE
                  AND vigencia_desde >= '2026-01-01'
                  AND (vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde)
            """)
            n = cur.fetchone()["n"]
        log.info(f"  (dry-run) {n} precios serían activados")
        return

    with pg_conn() as (conn, cur):
        cur.execute("""
            UPDATE precios_cliente
            SET activo = TRUE
            WHERE activo = FALSE
              AND vigencia_desde >= '2026-01-01'
              AND (vigencia_hasta IS NULL OR vigencia_hasta >= vigencia_desde)
        """)
        activados = cur.rowcount
        conn.commit()
    log.info(f"  Activados: {activados} registros de precios_cliente")


# ── Corregir tipo_gestion en seriales migrados desde histo ───────────────────

def corregir_tipo_gestion_histo(dry_run: bool):
    """
    Relee bases_web.histo y corrige tipo_gestion en seriales_gestion para el
    período histórico (HISTO_FECHA_DESDE..HISTO_FECHA_HASTA).

    Lógica: ret_esc se considera un retorno real solo si su valor tiene formato
    de fecha (YYYY.MM.DD o similar). Si contiene otro tipo de dato (código,
    planilla, etc.) se trata como Entrega. Esto corrige el error original de
    la migración donde ret_esc siempre era truthy aunque no fuera una fecha de
    retorno real.
    """
    import re
    DATE_RE = re.compile(r"^\d{4}[.\-/]\d{2}[.\-/]\d{2}$")

    desde_histo = HISTO_DESDE.replace("-", ".")
    hasta_histo = HISTO_HASTA.replace("-", ".")

    log.info(f"── corregir tipo_gestion histo ({HISTO_DESDE} → {HISTO_HASTA}) ──")

    with mysql_conn(MYSQL_BW, buffered=False) as my:
        my.execute("""
            SELECT serial, ret_esc
            FROM histo
            WHERE serial IS NOT NULL
              AND f_esc IS NOT NULL
              AND f_esc BETWEEN %s AND %s
              AND f_esc NOT LIKE '%%Entr%%'
              AND f_esc NOT LIKE '%%Devo%%'
        """, (desde_histo, hasta_histo))

        entregas = devoluciones = omitidos = 0
        batch_e: list[str] = []   # seriales → Entrega
        batch_d: list[str] = []   # seriales → Devolucion

        with pg_conn() as (conn, cur):
            while True:
                rows = my.fetchmany(BATCH)
                if not rows:
                    break

                for r in rows:
                    serial = r["serial"]
                    ret = (r.get("ret_esc") or "").strip()
                    # 'D' = código explícito de devolución; fecha = retorno real
                    # 'E' y minúsculas (i, p, l...) → Entrega/pendiente
                    es_devolucion = (
                        ret == 'D' or
                        bool(ret and DATE_RE.match(ret))
                    )

                    if es_devolucion:
                        batch_d.append(serial)
                        devoluciones += 1
                    else:
                        batch_e.append(serial)
                        entregas += 1

                if not dry_run:
                    if batch_e:
                        cur.executemany(
                            "UPDATE seriales_gestion SET tipo_gestion = 'Entrega' "
                            "WHERE serial = %s AND editado_manualmente = FALSE",
                            [(s,) for s in batch_e],
                        )
                    if batch_d:
                        cur.executemany(
                            "UPDATE seriales_gestion SET tipo_gestion = 'Devolucion' "
                            "WHERE serial = %s AND editado_manualmente = FALSE",
                            [(s,) for s in batch_d],
                        )
                    conn.commit()

                batch_e.clear()
                batch_d.clear()

    log.info(f"  Resultado: {entregas} Entregas, {devoluciones} Devoluciones, {omitidos} omitidos")
    if dry_run:
        log.info("  (dry-run — no se actualizó nada)")


# ── Post-migración: asignar mensajero_id desde cod_men ───────────────────────

def asignar_mensajero_ids(dry_run: bool):
    """
    Actualiza mensajero_id en seriales_gestion cruzando cod_men con personal.codigo.
    Correr después de migrate_personal y migrate_seriales/histo.
    """
    log.info("── asignar mensajero_id desde cod_men ────────────────")
    if dry_run:
        log.info("  (dry-run, no se actualizará nada)")
        return
    with pg_conn() as (conn, cur):
        cur.execute("""
            UPDATE seriales_gestion sg
            SET mensajero_id = p.id
            FROM personal p
            WHERE sg.cod_men = p.codigo
              AND sg.mensajero_id IS NULL
        """)
        updated = cur.rowcount
        conn.commit()
    log.info(f"  Actualizados: {updated} seriales con mensajero_id")


# ── Migración: imile.paquetes (ene–abr 2026) → seriales_gestion ──────────────

def migrate_imile(dry_run: bool):
    """
    Migra imile.paquetes (ene–abr 2026) a seriales_gestion.

    imile.paquetes no tiene mensajero por serial: se toma el cod_mensajero
    principal del día desde logistica.gestiones_mensajero (el que más seriales
    manejó ese día). Si un día no tiene registro en gestiones_mensajero se usa
    'IMIL' como placeholder (varchar 4 requerido).

    Valores fijos: paquete / bogota / Entrega / $2900 cliente / $1600 mensajero.
    f_esc = f_emi (mejor aproximación disponible).
    planilla = 'IM' + YYYYMMDD (mismo formato que los registros de mayo en PG).
    Idempotente: ON CONFLICT (serial) DO NOTHING.
    """
    log.info(f"── imile.paquetes ({IMILE_DESDE} → {IMILE_HASTA}) ───────────────")

    # 1. Mapa fecha → cod_mensajero principal desde gestiones_mensajero
    cod_men_por_fecha: dict[date, str] = {}
    with mysql_conn(MYSQL_LOG) as my:
        my.execute("""
            SELECT fecha_registro, cod_mensajero, SUM(total_seriales) AS total
            FROM gestiones_mensajero
            WHERE cliente LIKE %s
              AND fecha_registro BETWEEN %s AND %s
            GROUP BY fecha_registro, cod_mensajero
            ORDER BY fecha_registro, total DESC
        """, ("%mile%", IMILE_DESDE, IMILE_HASTA))
        for row in my.fetchall():
            f = row["fecha_registro"]
            if isinstance(f, str):
                try:
                    f = date.fromisoformat(f)
                except ValueError:
                    continue
            # Solo guardamos el primero por fecha (ORDER BY total DESC → el de mayor volumen)
            if f not in cod_men_por_fecha:
                cod_men_por_fecha[f] = (row["cod_mensajero"] or "IMIL")[:4]
    log.info(f"  gestiones_mensajero: {len(cod_men_por_fecha)} días con mensajero asignado")

    # 2. Leer paquetes Imile del período
    with mysql_conn(MYSQL_IMILE) as my:
        my.execute("""
            SELECT serial, f_emi
            FROM paquetes
            WHERE f_emi BETWEEN %s AND %s
            ORDER BY f_emi, serial
        """, (IMILE_DESDE, IMILE_HASTA))
        paquetes = my.fetchall()
    log.info(f"  imile.paquetes: {len(paquetes)} registros")

    if dry_run or not paquetes:
        if dry_run:
            log.info("  (dry-run — no se escribirá nada)")
        return

    # 3. Obtener cliente_id de Imile SAS en PG
    cliente_map = _build_cliente_map()
    imile_id = cliente_map.get("imile sas")
    if imile_id is None:
        log.error("  No se encontró 'Imile SAS' en clientes de PG. Abortando.")
        return

    # 4. Insertar en seriales_gestion
    with pg_conn() as (conn, cur):
        inserted = skipped_dup = bad_date = 0
        for batch in batched(paquetes, BATCH):
            for r in batch:
                f_emi = parse_fecha(r.get("f_emi"))
                if f_emi is None:
                    bad_date += 1
                    continue

                planilla  = f"IM{f_emi.strftime('%Y%m%d')}"
                cod_men   = cod_men_por_fecha.get(f_emi, "IMIL")

                cur.execute("""
                    INSERT INTO seriales_gestion
                        (serial, f_emi, f_esc, planilla, cod_men,
                         cliente_id, tipo_gestion, tipo_envio, ambito,
                         precio_cliente, precio_mensajero,
                         estado, origen, editado_manualmente)
                    VALUES
                        (%s, %s, %s, %s, %s,
                         %s, %s, %s, %s,
                         %s, %s,
                         %s, %s, %s)
                    ON CONFLICT (serial) DO NOTHING
                """, (
                    str(r["serial"]), f_emi, f_emi, planilla, cod_men,
                    imile_id, "Entrega", "paquete", "bogota",
                    2900.00, 1600.00,
                    "pendiente", "imile", False,
                ))
                if cur.rowcount:
                    inserted += 1
                else:
                    skipped_dup += 1

            conn.commit()

    log.info(f"  PostgreSQL: {inserted} insertados, {skipped_dup} duplicados ignorados, {bad_date} sin fecha")


# ── Migración: registro_horas y registro_labores ──────────────────────────────

def _build_orden_map(pg_cur) -> dict:
    """Devuelve {numero_orden: pg_id} para todas las órdenes en PostgreSQL."""
    pg_cur.execute("SELECT id, numero_orden FROM ordenes")
    return {r["numero_orden"]: r["id"] for r in pg_cur.fetchall()}


def _build_usuario_map(pg_cur) -> dict:
    """Devuelve {username: pg_id} para todos los usuarios en PostgreSQL."""
    pg_cur.execute("SELECT id, username FROM usuarios")
    return {r["username"]: r["id"] for r in pg_cur.fetchall()}


def _build_aprobado_por_map(my_cur, pg_cur) -> dict:
    """Devuelve {mysql_usuario_id: pg_usuario_id} mapeando por username."""
    my_cur.execute("SELECT id, username FROM usuarios")
    mysql_users = {r["id"]: r["username"] for r in my_cur.fetchall()}
    pg_users = _build_usuario_map(pg_cur)
    return {
        my_id: pg_users[username]
        for my_id, username in mysql_users.items()
        if username in pg_users
    }


def migrate_labores(dry_run: bool):
    log.info("── registro_horas + registro_labores ────────────────")

    with mysql_conn(MYSQL_LOG) as my:
        my.execute("""
            SELECT rh.personal_id, rh.orden_id, o.numero_orden,
                   rh.fecha, rh.horas_trabajadas, rh.tarifa_hora,
                   rh.tipo_trabajo, rh.aprobado, rh.aprobado_por,
                   rh.fecha_aprobacion, rh.liquidado, rh.liquidacion_id,
                   rh.observaciones, rh.fecha_creacion
            FROM registro_horas rh
            LEFT JOIN ordenes o ON rh.orden_id = o.id
            ORDER BY rh.fecha, rh.id
        """)
        horas = my.fetchall()

        my.execute("""
            SELECT rl.personal_id, rl.orden_id, o.numero_orden,
                   rl.fecha, rl.tipo_labor, rl.cantidad, rl.tarifa_unitaria,
                   rl.aprobado, rl.aprobado_por,
                   rl.fecha_aprobacion, rl.liquidado, rl.liquidacion_id,
                   rl.observaciones, rl.fecha_creacion
            FROM registro_labores rl
            LEFT JOIN ordenes o ON rl.orden_id = o.id
            ORDER BY rl.fecha, rl.id
        """)
        labores = my.fetchall()

        aprobado_map_raw = {}
        my.execute("SELECT id, username FROM usuarios")
        aprobado_map_raw = {r["id"]: r["username"] for r in my.fetchall()}

    log.info(f"  MySQL: {len(horas)} horas, {len(labores)} labores")

    if dry_run:
        return

    with pg_conn() as (conn, pg_cur):
        orden_map = _build_orden_map(pg_cur)
        pg_cur.execute("SELECT id, username FROM usuarios")
        pg_users = {r["username"]: r["id"] for r in pg_cur.fetchall()}
        aprobado_por_map = {
            my_id: pg_users[uname]
            for my_id, uname in aprobado_map_raw.items()
            if uname in pg_users
        }

        pg_cur.execute("SELECT DISTINCT fecha FROM registro_horas")
        pg_horas_fechas = {r["fecha"] for r in pg_cur.fetchall()}
        pg_cur.execute("SELECT DISTINCT fecha FROM registro_labores")
        pg_labores_fechas = {r["fecha"] for r in pg_cur.fetchall()}

        inserted_h = skipped_h = inserted_l = skipped_l = 0
        sin_orden_h = sin_orden_l = 0

        for batch in batched(horas, BATCH):
            for r in batch:
                if r["fecha"] in pg_horas_fechas:
                    skipped_h += 1
                    continue
                pg_orden_id = orden_map.get(r["numero_orden"]) if r["numero_orden"] else None
                if r["orden_id"] and not pg_orden_id:
                    sin_orden_h += 1
                pg_aprobado_por = aprobado_por_map.get(r["aprobado_por"]) if r["aprobado_por"] else None
                pg_cur.execute("""
                    INSERT INTO registro_horas
                        (personal_id, orden_id, fecha, horas_trabajadas, tarifa_hora,
                         tipo_trabajo, aprobado, aprobado_por, fecha_aprobacion,
                         liquidado, liquidacion_id, observaciones, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    r["personal_id"], pg_orden_id,
                    r["fecha"], r["horas_trabajadas"], r["tarifa_hora"],
                    r["tipo_trabajo"],
                    bool(r.get("aprobado", False)),
                    pg_aprobado_por,
                    r.get("fecha_aprobacion"),
                    bool(r.get("liquidado", False)),
                    r.get("liquidacion_id"),
                    r.get("observaciones"),
                    r.get("fecha_creacion"),
                ))
                inserted_h += 1
            conn.commit()

        for batch in batched(labores, BATCH):
            for r in batch:
                if r["fecha"] in pg_labores_fechas:
                    skipped_l += 1
                    continue
                pg_orden_id = orden_map.get(r["numero_orden"]) if r["numero_orden"] else None
                if r["orden_id"] and not pg_orden_id:
                    sin_orden_l += 1
                pg_aprobado_por = aprobado_por_map.get(r["aprobado_por"]) if r["aprobado_por"] else None
                pg_cur.execute("""
                    INSERT INTO registro_labores
                        (personal_id, orden_id, fecha, tipo_labor, cantidad,
                         tarifa_unitaria, aprobado, aprobado_por, fecha_aprobacion,
                         liquidado, liquidacion_id, observaciones, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    r["personal_id"], pg_orden_id,
                    r["fecha"], r["tipo_labor"], r["cantidad"],
                    r["tarifa_unitaria"],
                    bool(r.get("aprobado", False)),
                    pg_aprobado_por,
                    r.get("fecha_aprobacion"),
                    bool(r.get("liquidado", False)),
                    r.get("liquidacion_id"),
                    r.get("observaciones"),
                    r.get("fecha_creacion"),
                ))
                inserted_l += 1
            conn.commit()

    log.info(f"  registro_horas:   {inserted_h} insertados, {skipped_h} fechas ya en PG, {sin_orden_h} sin orden en PG")
    log.info(f"  registro_labores: {inserted_l} insertados, {skipped_l} fechas ya en PG, {sin_orden_l} sin orden en PG")


# ── Main ──────────────────────────────────────────────────────────────────────

TABLAS = {
    "clientes":          migrate_clientes,
    "personal":          migrate_personal,
    "seriales":          migrate_seriales,
    "histo":             migrate_histo,
    "histo-incremental": migrate_histo_incremental,
    "mensajeros":        asignar_mensajero_ids,
    "tipo_gestion":      corregir_tipo_gestion_histo,
    "precios":           activar_precios_historicos,
    "imile":             migrate_imile,
    "labores":           migrate_labores,
}

def main():
    parser = argparse.ArgumentParser(description="Migración MySQL → PostgreSQL Servilla ERP")
    parser.add_argument(
        "--tabla",
        default="clientes,personal,histo,mensajeros",
        help="Tablas a migrar (coma-separadas): clientes, personal, seriales, histo, histo-incremental, mensajeros, tipo_gestion, precios, imile, labores",
    )
    parser.add_argument("--dry-run", action="store_true", help="Cuenta filas sin insertar")
    args = parser.parse_args()

    tablas = [t.strip() for t in args.tabla.split(",")]
    desconocidas = [t for t in tablas if t not in TABLAS]
    if desconocidas:
        log.error(f"Tablas desconocidas: {desconocidas}. Opciones: {list(TABLAS)}")
        sys.exit(1)

    if args.dry_run:
        log.info("MODO DRY-RUN — no se escribirá nada en PostgreSQL")

    log.info(f"Tablas a migrar: {tablas}")
    log.info(f"PostgreSQL: {PG_DSN.split('@')[-1] if '@' in PG_DSN else PG_DSN}")
    log.info(f"MySQL logistica: {MYSQL_LOG['host']}:{MYSQL_LOG['port']}/{MYSQL_LOG['database']}")
    if any(t in ("histo", "histo-incremental") for t in tablas):
        log.info(f"MySQL bases_web: {MYSQL_BW['host']}:{MYSQL_BW['port']}/{MYSQL_BW['database']}")
        if "histo" in tablas:
            log.info(f"Rango histo: {HISTO_DESDE} → {HISTO_HASTA}")

    for tabla in tablas:
        try:
            TABLAS[tabla](args.dry_run)
        except Exception as e:
            log.error(f"Error migrando '{tabla}': {e}")
            raise

    log.info("✓ Migración completada")


if __name__ == "__main__":
    main()
