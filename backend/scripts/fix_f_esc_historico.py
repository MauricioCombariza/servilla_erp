"""
Backfill one-time: corrige f_esc y f_emi en seriales_gestion para filas del flujo
iMile histórico, afectadas por el bug donde ordenes_service reusaba el mismo valor
derivado (fecha de emisión) para ambas columnas en vez de la fecha real de escáner
(ver ordenes_service.py, _SERIAL_UPSERT, antes de este fix).

Alcance (a propósito, NO se corrige nada fuera de esto):
  - Solo filas con f_esc >= 2026-07-01 (columna DATE nativa en Postgres,
    comparación directa segura). Períodos anteriores pueden estar ya
    liquidados/facturados y quedan fuera de este backfill.
  - Solo filas con editado_manualmente = FALSE (mismo guard que usa el propio
    upsert de carga masiva — no se tocan ediciones manuales).
  - Solo filas cuyo serial existe en bases_web.histo, fuente real de f_esc/f_emi
    para el flujo histórico. Seriales de origen iMile-escáner o CSV-manual no
    están en histo y quedan naturalmente fuera de este backfill (no-op
    silencioso) — no es un bug de este script, es el alcance correcto: esos
    orígenes no vienen del histórico y su f_esc ya es (o pasa a ser, con el fix
    de ordenes_service hacia adelante) correcto.
  - Si el f_esc real (de histo) resulta ser ANTERIOR al 2026-07-01, la fila NO
    se corrige — queda con su f_esc actual tal cual, aunque sea incorrecto
    (decisión explícita: no se retrocede a un período anterior).

Money-safety: este script NUNCA toca precio_cliente ni precio_mensajero. Solo
reporta (no aplica) los casos donde el f_esc corregido caería en un período de
vigencia de precios_cliente distinto al que el f_esc actual implicaría — esos
casos requieren revisión humana aparte (ver
backend/app/services/planillas_service.py:recalcular_precios).

bases_web.histo NO garantiza UNIQUE(serial); si un serial aparece en histo con
f_esc/f_emi ambiguos (varias filas con valores distintos), se reporta y se
omite — no se adivina (mismo criterio que fix_planilla_nan.py).

Uso:
    DATABASE_URL="postgresql://servilla:PASS@localhost:5440/servilla_erp" \
    MYSQL_PASSWORD_BW="..." \
    python scripts/fix_f_esc_historico.py                          # solo reporta
    python scripts/fix_f_esc_historico.py --apply                  # aplica los UPDATE
    python scripts/fix_f_esc_historico.py --out-vigencia-impacto impacto.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime

FECHA_LIMITE = datetime(2026, 7, 1).date()

MYSQL_BW = {
    "host":     os.environ.get("MYSQL_HOST_BW", "186.180.15.66"),
    "port":     int(os.environ.get("MYSQL_PORT_BW", 12539)),
    "user":     os.environ.get("MYSQL_USER_BW", "servilla_remoto"),
    "password": os.environ.get("MYSQL_PASSWORD_BW", ""),
    "database": os.environ.get("MYSQL_DB_BW", "bases_web"),
}


# ── Conexiones ───────────────────────────────────────────────────────────────

@contextmanager
def mysql_conn(cfg: dict):
    import mysql.connector
    conn = mysql.connector.connect(charset="utf8mb4", **cfg)
    cur = conn.cursor(dictionary=True, buffered=False)
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


@contextmanager
def pg_conn(dsn: str):
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(dsn)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn, cur
    finally:
        cur.close()
        conn.close()


def _parse_histo_fecha(s):
    """'YYYY.MM.DD' (formato de histo) → date, o None si vacío/no parseable."""
    if not s:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("na", "n/a", "nan"):
        return None
    try:
        return datetime.strptime(s, "%Y.%m.%d").date()
    except ValueError:
        return None


def _chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ── Paso 1: candidatos en Postgres ──────────────────────────────────────────

def cargar_candidatos_pg(cur) -> dict:
    cur.execute("""
        SELECT id, serial, f_esc, f_emi, cliente_id, tipo_envio, ambito
        FROM seriales_gestion
        WHERE f_esc >= %s AND editado_manualmente = FALSE
    """, (FECHA_LIMITE,))
    return {r["serial"]: r for r in cur.fetchall()}


# ── Paso 2: verdad en histo (con detección de ambigüedad) ───────────────────

def cargar_verdad_histo(seriales: list) -> dict:
    crudos = defaultdict(list)
    with mysql_conn(MYSQL_BW) as cur:
        for lote in _chunked(seriales, 2000):
            placeholders = ",".join(["%s"] * len(lote))
            cur.execute(
                f"SELECT serial, f_esc, f_emi FROM histo WHERE serial IN ({placeholders})",
                tuple(lote),
            )
            for r in cur.fetchall():
                crudos[str(r["serial"]).strip()].append((r["f_esc"], r["f_emi"]))

    verdad, ambiguos, sin_f_esc = {}, 0, 0
    for serial, filas in crudos.items():
        parsed = {(_parse_histo_fecha(fe), _parse_histo_fecha(fm)) for fe, fm in filas}
        if len(parsed) > 1:
            ambiguos += 1
            continue
        f_esc, f_emi = next(iter(parsed))
        if f_esc is None:
            sin_f_esc += 1
            continue
        verdad[serial] = {"f_esc": f_esc, "f_emi": f_emi}

    if ambiguos:
        print(f"  ⚠ {ambiguos:,} seriales con f_esc/f_emi ambiguo en histo (múltiples valores distintos) → omitidos")
    if sin_f_esc:
        print(f"  ⚠ {sin_f_esc:,} seriales en histo sin f_esc parseable → omitidos")
    return verdad


# ── Paso 3: comparar, separar por corregibles vs. período anterior ──────────

def comparar(pg: dict, histo: dict) -> tuple[list, int]:
    """Devuelve (candidatos_a_corregir, cuenta_periodo_anterior)."""
    corregir = []
    periodo_anterior = 0
    for serial, row in pg.items():
        v = histo.get(serial)
        if v is None:
            continue  # fuera del histo → fuera de alcance (imile/manual), no-op
        if v["f_esc"] < FECHA_LIMITE:
            periodo_anterior += 1
            continue  # el f_esc real cae antes del corte → no se toca
        if v["f_esc"] == row["f_esc"] and v["f_emi"] == row["f_emi"]:
            continue  # ya correcto
        corregir.append({
            "id": row["id"], "serial": serial,
            "f_esc_actual": row["f_esc"], "f_esc_correcto": v["f_esc"],
            "f_emi_actual": row["f_emi"], "f_emi_correcto": v["f_emi"],
            "cliente_id": row["cliente_id"], "tipo_envio": row["tipo_envio"], "ambito": row["ambito"],
        })
    return corregir, periodo_anterior


# ── Paso 4: reporte informativo de impacto en vigencia de tarifas ───────────

def vigencia_id(cur, cliente_id, tipo_envio, ambito, fecha):
    if cliente_id is None or fecha is None:
        return None
    cur.execute("""
        SELECT id FROM precios_cliente
        WHERE cliente_id = %s AND tipo_servicio = %s AND ambito = %s
          AND activo = TRUE
          AND vigencia_desde <= %s
          AND (vigencia_hasta IS NULL OR vigencia_hasta >= %s)
        ORDER BY vigencia_desde DESC
        LIMIT 1
    """, (cliente_id, tipo_envio, ambito, fecha, fecha))
    row = cur.fetchone()
    return row["id"] if row else None


def anotar_impacto_vigencia(cur, corregir: list) -> list:
    con_impacto = []
    for c in corregir:
        vig_actual = vigencia_id(cur, c["cliente_id"], c["tipo_envio"], c["ambito"], c["f_esc_actual"])
        vig_corregida = vigencia_id(cur, c["cliente_id"], c["tipo_envio"], c["ambito"], c["f_esc_correcto"])
        c["vigencia_actual"] = vig_actual
        c["vigencia_corregida"] = vig_corregida
        if vig_actual != vig_corregida:
            con_impacto.append(c)
    return con_impacto


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                     help="Aplica los UPDATE de f_esc/f_emi (por defecto solo reporta)")
    ap.add_argument("--out-vigencia-impacto", help="Ruta CSV opcional con el detalle de filas cuyo período de tarifa cambiaría")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Define DATABASE_URL antes de ejecutar")
        sys.exit(1)
    if not MYSQL_BW["password"]:
        print("ERROR: Define MYSQL_PASSWORD_BW antes de ejecutar")
        sys.exit(1)

    with pg_conn(db_url.replace("+asyncpg", "")) as (conn, cur):
        pg = cargar_candidatos_pg(cur)
        print(f"Candidatos en Postgres (f_esc >= {FECHA_LIMITE}, editado_manualmente=FALSE): {len(pg):,}")
        if not pg:
            print("Nada que revisar.")
            return

        histo = cargar_verdad_histo(list(pg.keys()))
        print(f"Con match en bases_web.histo: {len(histo):,} "
              f"(resto = origen iMile-escáner/CSV-manual, fuera de alcance, no-op)")

        corregir, periodo_anterior = comparar(pg, histo)
        print(f"\nFilas cuyo f_esc real cae ANTES de {FECHA_LIMITE} (se dejan sin tocar): {periodo_anterior:,}")
        print(f"Filas a corregir (f_esc/f_emi incorrecto, real >= {FECHA_LIMITE}): {len(corregir):,}")

        con_impacto = anotar_impacto_vigencia(cur, corregir) if corregir else []
        print(f"  De esas, con cambio de período de vigencia de tarifa (revisar precio aparte): {len(con_impacto):,}")
        for c in con_impacto[:50]:
            print(f"    serial={c['serial']} cliente_id={c['cliente_id']} "
                  f"f_esc {c['f_esc_actual']} → {c['f_esc_correcto']} "
                  f"(vigencia id {c['vigencia_actual']} → {c['vigencia_corregida']})")
        if len(con_impacto) > 50:
            print(f"    … y {len(con_impacto) - 50:,} más")

        if args.out_vigencia_impacto and con_impacto:
            with open(args.out_vigencia_impacto, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(con_impacto[0].keys()))
                w.writeheader()
                w.writerows(con_impacto)
            print(f"  Detalle completo escrito en {args.out_vigencia_impacto}")

        if not args.apply:
            print("\n(reporte only — no se aplicó ningún cambio; pasar --apply para aplicar)")
            return

        total = 0
        for c in corregir:
            cur.execute("""
                UPDATE seriales_gestion
                SET f_esc = %s, f_emi = %s
                WHERE id = %s AND editado_manualmente = FALSE
            """, (c["f_esc_correcto"], c["f_emi_correcto"], c["id"]))
            total += cur.rowcount
        conn.commit()
        print(f"\nActualizados: {total:,} seriales (f_esc/f_emi únicamente; precios NO tocados)")


if __name__ == "__main__":
    main()
