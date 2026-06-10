"""
Corrección de tipo_gestion usando el CSV local como fuente de verdad.

Mapeo ret_esc → tipo_gestion:
  'D'       → Devolucion
  'E', minúsculas (i, p, l, f, j…), vacío → Entrega

Uso:
    DATABASE_URL="postgresql://servilla:PASS@localhost:5441/servilla_erp" \
    python fix_tipo_gestion_csv.py /ruta/al/dashboard.csv [--dry-run]
"""

import argparse
import sys

import pandas as pd
import psycopg2
import re

DATE_RE = re.compile(r"^\d{4}[.\-/]\d{2}[.\-/]\d{2}$")


def mapear_tipo(ret_esc_val) -> str:
    ret = str(ret_esc_val).strip() if pd.notna(ret_esc_val) else ""
    if ret == "D" or (ret and DATE_RE.match(ret)):
        return "Devolucion"
    return "Entrega"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Ruta al archivo CSV (dashboard.csv)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Define DATABASE_URL antes de ejecutar")
        sys.exit(1)

    print(f"Leyendo {args.csv} …")
    df = pd.read_csv(args.csv, low_memory=False)

    if "ret_esc" not in df.columns or "serial" not in df.columns:
        print("ERROR: El CSV no tiene columnas 'serial' o 'ret_esc'")
        sys.exit(1)

    df["tipo_correcto"] = df["ret_esc"].apply(mapear_tipo)

    # Solo filas con serial válido
    df = df[df["serial"].notna()].copy()
    df["serial"] = df["serial"].astype(str).str.strip()

    batch_entrega   = df[df["tipo_correcto"] == "Entrega"]["serial"].tolist()
    batch_devolucion = df[df["tipo_correcto"] == "Devolucion"]["serial"].tolist()

    print(f"  Seriales → Entrega:    {len(batch_entrega):,}")
    print(f"  Seriales → Devolucion: {len(batch_devolucion):,}")

    if args.dry_run:
        print("(dry-run — no se aplican cambios)")
        return

    conn = psycopg2.connect(db_url.replace("+asyncpg", ""))
    cur  = conn.cursor()

    # UPDATE Entrega (solo los que están mal como Devolucion)
    if batch_entrega:
        cur.execute("""
            UPDATE seriales_gestion
            SET tipo_gestion = 'Entrega'
            WHERE serial = ANY(%s)
              AND tipo_gestion = 'Devolucion'
              AND editado_manualmente = FALSE
        """, (batch_entrega,))
        print(f"  Actualizados → Entrega:    {cur.rowcount:,}")

    # UPDATE Devolucion (solo los que están mal como Entrega)
    if batch_devolucion:
        cur.execute("""
            UPDATE seriales_gestion
            SET tipo_gestion = 'Devolucion'
            WHERE serial = ANY(%s)
              AND tipo_gestion = 'Entrega'
              AND editado_manualmente = FALSE
        """, (batch_devolucion,))
        print(f"  Actualizados → Devolucion: {cur.rowcount:,}")

    conn.commit()
    cur.close()
    conn.close()
    print("Listo.")


if __name__ == "__main__":
    main()
