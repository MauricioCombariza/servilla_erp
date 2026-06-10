"""
Análisis de diferencias bases_web.histo vs PostgreSQL seriales_gestion — Abril 2026
Excluye registros de imile (tienen fuente propia).

Uso:
    cd backend
    python scripts/analisis_histo_vs_pg.py

Variables de entorno requeridas:
    DATABASE_URL        URL completa de PostgreSQL
    MYSQL_PASSWORD_BW   Contraseña MySQL bases_web
"""

import os
import sys
from collections import defaultdict
from contextlib import contextmanager

DESDE_MYSQL = "2026.04.01"
HASTA_MYSQL = "2026.04.30"
DESDE_PG    = "2026-04-01"
HASTA_PG    = "2026-04-30"

MYSQL_BW = {
    "host":     os.environ.get("MYSQL_HOST_BW", "186.180.15.66"),
    "port":     int(os.environ.get("MYSQL_PORT_BW", 12539)),
    "user":     os.environ.get("MYSQL_USER_BW", "servilla_remoto"),
    "password": os.environ.get("MYSQL_PASSWORD_BW", ""),
    "database": os.environ.get("MYSQL_DB_BW", "bases_web"),
}

_db_url = os.environ.get("DATABASE_URL")
if not _db_url:
    print("ERROR: DATABASE_URL no configurada.")
    sys.exit(1)
PG_DSN = _db_url.replace("+asyncpg", "")

ALIASES = {
    "banco caja social":         "banco caja social",
    "fiduciaria caja social":    "banco caja social",
    "vehigroup sas":             "vehigrupo sas",
    "-vehigroup sas":            "vehigrupo sas",
    "leonisa":                   "leonisa",
    "pronticourrier express sa": "pronticourier express s.a.s",
    "pronticourier express sa":  "pronticourier express s.a.s",
}


@contextmanager
def mysql_conn(cfg: dict, buffered: bool = True):
    try:
        import mysql.connector
    except ImportError:
        print("ERROR: pip install mysql-connector-python")
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
        print("ERROR: pip install psycopg2-binary")
        sys.exit(1)
    conn = psycopg2.connect(PG_DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
    finally:
        cur.close()
        conn.close()


def normalizar(nombre: str) -> str:
    n = (nombre or "").strip().lower()
    return ALIASES.get(n, n)


def cargar_histo() -> dict[str, str]:
    """Devuelve {serial: cliente_normalizado} desde bases_web.histo para abril."""
    print(f"Conectando a bases_web.histo ({DESDE_MYSQL} → {HASTA_MYSQL})…")
    with mysql_conn(MYSQL_BW, buffered=False) as cur:
        cur.execute("""
            SELECT serial, no_entidad
            FROM histo
            WHERE serial IS NOT NULL
              AND f_esc IS NOT NULL
              AND f_esc BETWEEN %s AND %s
              AND f_esc NOT LIKE '%%Entr%%'
              AND f_esc NOT LIKE '%%Devo%%'
              AND (no_entidad IS NULL OR no_entidad NOT LIKE '%%mile%%')
        """, (DESDE_MYSQL, HASTA_MYSQL))

        resultado = {}
        while True:
            rows = cur.fetchmany(2000)
            if not rows:
                break
            for r in rows:
                serial = str(r["serial"]).strip()
                resultado[serial] = normalizar(r.get("no_entidad") or "")
    print(f"  → {len(resultado)} seriales en histo (abril, excl. imile/Lecta/Prindel)")
    return resultado


def cargar_pg() -> dict[str, str]:
    """Devuelve {serial: cliente_normalizado} desde seriales_gestion para abril."""
    print(f"Consultando PostgreSQL seriales_gestion ({DESDE_PG} → {HASTA_PG})…")
    with pg_conn() as cur:
        cur.execute("""
            SELECT sg.serial, c.nombre_empresa AS cliente_nombre
            FROM seriales_gestion sg
            LEFT JOIN clientes c ON c.id = sg.cliente_id
            WHERE sg.f_esc BETWEEN %s AND %s
              AND sg.origen = 'scanner'
              AND (c.nombre_empresa IS NULL OR c.nombre_empresa NOT ILIKE '%%imile%%')
        """, (DESDE_PG, HASTA_PG))
        rows = cur.fetchall()

    resultado = {
        str(r["serial"]).strip(): normalizar(r.get("cliente_nombre") or "")
        for r in rows
    }
    print(f"  → {len(resultado)} seriales en PG (abril, excl. imile)")
    return resultado


def analizar(histo: dict[str, str], pg: dict[str, str]) -> None:
    seriales_histo = set(histo)
    seriales_pg    = set(pg)

    solo_histo = seriales_histo - seriales_pg
    solo_pg    = seriales_pg - seriales_histo
    en_ambos   = seriales_histo & seriales_pg

    print(f"\n{'='*60}")
    print(f"  RESUMEN GLOBAL — Abril 2026 (excl. imile)")
    print(f"{'='*60}")
    print(f"  Seriales en histo:          {len(seriales_histo):>7,}")
    print(f"  Seriales en PG:             {len(seriales_pg):>7,}")
    print(f"  En ambos:                   {len(en_ambos):>7,}")
    print(f"  Solo en histo (faltan PG):  {len(solo_histo):>7,}")
    print(f"  Solo en PG (no están histo):{len(solo_pg):>7,}")

    # Contar por cliente
    def contar_por_cliente(seriales_set, fuente_dict):
        cnt = defaultdict(int)
        for s in seriales_set:
            cnt[fuente_dict.get(s, "(sin cliente)")] += 1
        return cnt

    histo_total = defaultdict(int)
    for cl in histo.values():
        histo_total[cl] += 1

    pg_total = defaultdict(int)
    for cl in pg.values():
        pg_total[cl] += 1

    falta_en_pg    = contar_por_cliente(solo_histo, histo)
    sobra_en_pg    = contar_por_cliente(solo_pg, pg)

    todos_clientes = sorted(histo_total.keys() | pg_total.keys())

    print(f"\n{'─'*80}")
    print(f"{'CLIENTE':<35} {'HISTO':>8} {'PG':>8} {'FALTA_PG':>10} {'SOBRA_PG':>10}")
    print(f"{'─'*80}")
    for cl in todos_clientes:
        h  = histo_total.get(cl, 0)
        p  = pg_total.get(cl, 0)
        fp = falta_en_pg.get(cl, 0)
        sp = sobra_en_pg.get(cl, 0)
        if fp > 0 or sp > 0:
            flag = " ◄"
        else:
            flag = ""
        print(f"{cl or '(sin cliente)':<35} {h:>8,} {p:>8,} {fp:>10,} {sp:>10,}{flag}")
    print(f"{'─'*80}")

    if solo_histo:
        print(f"\n{'='*60}")
        print(f"  SERIALES EN HISTO PERO AUSENTES EN PG  ({len(solo_histo):,})")
        print(f"{'='*60}")
        por_cliente = defaultdict(list)
        for s in sorted(solo_histo):
            por_cliente[histo[s]].append(s)
        for cl in sorted(por_cliente):
            seriales = por_cliente[cl]
            print(f"\n  [{cl or '(sin cliente)'}]  ({len(seriales)} seriales)")
            for s in seriales[:50]:
                print(f"    {s}")
            if len(seriales) > 50:
                print(f"    … y {len(seriales)-50} más")

    if solo_pg:
        print(f"\n{'='*60}")
        print(f"  SERIALES EN PG PERO AUSENTES EN HISTO  ({len(solo_pg):,})")
        print(f"{'='*60}")
        por_cliente = defaultdict(list)
        for s in sorted(solo_pg):
            por_cliente[pg[s]].append(s)
        for cl in sorted(por_cliente):
            seriales = por_cliente[cl]
            print(f"\n  [{cl or '(sin cliente)'}]  ({len(seriales)} seriales)")
            for s in seriales[:50]:
                print(f"    {s}")
            if len(seriales) > 50:
                print(f"    … y {len(seriales)-50} más")


if __name__ == "__main__":
    histo = cargar_histo()
    pg    = cargar_pg()
    analizar(histo, pg)
