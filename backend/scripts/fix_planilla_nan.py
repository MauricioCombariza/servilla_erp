"""
Corrección one-time de seriales con planilla='nan' (o '') usando el CSV como fuente.

Origen del bug: en cargas anteriores, una celda de planilla ausente se leía como NaN
(dtype=str) y — al ser NaN *truthy* — se serializaba como el literal 'nan' en
seriales_gestion.planilla. Además el upsert de carga masiva solo re-etiqueta planilla
cuando estado='pendiente', así que los seriales ya liquidados quedaron congelados en 'nan'.

Este script toma la planilla correcta del CSV por serial y corrige SOLO la columna
planilla de las filas actualmente en 'nan'/'' (no toca precios, estado ni tipo_gestion),
independientemente del estado, porque es corrección de un error de datos.

Uso:
    DATABASE_URL="postgresql://servilla:PASS@localhost:5441/servilla_erp" \
    python fix_planilla_nan.py /ruta/al/dashboard.csv [--dry-run]
"""

import argparse
import os
import sys
from collections import defaultdict

import pandas as pd
import psycopg2

# Valores que consideramos "planilla rota" en la BD (a corregir)
BROKEN = ("nan", "")


def _clean(val) -> str:
    """Normaliza una celda a string strip; NaN/None → ''."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Ruta al archivo CSV (dashboard.csv)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Define DATABASE_URL antes de ejecutar")
        sys.exit(1)

    print(f"Leyendo {args.csv} …")
    df = pd.read_csv(args.csv, dtype=str, low_memory=False)

    if "serial" not in df.columns or "planilla" not in df.columns:
        print("ERROR: El CSV no tiene columnas 'serial' o 'planilla'")
        sys.exit(1)

    df["serial"] = df["serial"].map(_clean)
    df["planilla"] = df["planilla"].map(_clean)
    df = df[(df["serial"] != "") & (df["planilla"] != "")]

    # serial → planilla correcta. Si un serial aparece con varias planillas reales
    # en el CSV, se reporta el conflicto y se omite (no adivinamos).
    seen: dict[str, str] = {}
    conflicts: set[str] = set()
    for serial, planilla in zip(df["serial"], df["planilla"]):
        prev = seen.get(serial)
        if prev is None:
            seen[serial] = planilla
        elif prev != planilla:
            conflicts.add(serial)
    for s in conflicts:
        seen.pop(s, None)

    if conflicts:
        print(f"  ⚠ {len(conflicts):,} seriales con planilla ambigua en el CSV → omitidos")

    # Agrupar por planilla destino para UPDATEs en lote
    por_planilla: dict[str, list[str]] = defaultdict(list)
    for serial, planilla in seen.items():
        por_planilla[planilla].append(serial)

    print(f"  Seriales con planilla única en el CSV: {len(seen):,} "
          f"({len(por_planilla):,} planillas)")

    conn = psycopg2.connect(db_url.replace("+asyncpg", ""))
    cur = conn.cursor()

    all_serials = list(seen.keys())
    cur.execute(
        "SELECT count(*) FROM seriales_gestion "
        "WHERE serial = ANY(%s) AND planilla = ANY(%s)",
        (all_serials, list(BROKEN)),
    )
    afectables = cur.fetchone()[0]
    print(f"  Filas en BD con planilla rota ('nan'/'') que se corregirían: {afectables:,}")

    if args.dry_run:
        print("(dry-run — no se aplican cambios)")
        cur.close()
        conn.close()
        return

    total = 0
    for planilla, serials in por_planilla.items():
        cur.execute(
            "UPDATE seriales_gestion SET planilla = %s "
            "WHERE serial = ANY(%s) AND planilla = ANY(%s)",
            (planilla, serials, list(BROKEN)),
        )
        total += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()
    print(f"  Actualizados: {total:,} seriales")
    print("Listo.")


if __name__ == "__main__":
    main()
