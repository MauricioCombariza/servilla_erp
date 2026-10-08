"""Prueba rápida de la sectorización con direcciones sueltas o con un Excel de despacho.

No necesita la BD: usa el mismo CSV con el que la migración 031 carga
`sectorizacion_limites`.

Uso (desde backend/):
    uv run python scripts/probar_sectorizacion.py "calle 95 # 49-22" "CR 56A # 79-15"
    uv run python scripts/probar_sectorizacion.py --excel ruta/al/despacho.xlsx [--columna Address2]
"""
import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# El servicio importa la config de la app, que exige estas variables aunque aquí no se use la BD
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sin:bd@localhost:1/sin_bd")
os.environ.setdefault("JWT_SECRET", "no-se-usa")

from app.services.sectorizacion_service import (
    LimiteSector,
    construir_indice,
    sectorizar,
)

SEMILLA = Path(__file__).resolve().parents[1] / "app" / "assets" / "sectorizacion_limites.csv"
COLUMNAS_DIRECCION = ["Address2", "Dirección detallada del destinatario"]


def _indice():
    with SEMILLA.open(encoding="utf-8", newline="") as f:
        return construir_indice(
            LimiteSector(**{**{k: (v or None) for k, v in fila.items()}, "orden": int(fila["orden"])})
            for fila in csv.DictReader(f)
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("direcciones", nargs="*")
    parser.add_argument("--excel")
    parser.add_argument("--columna")
    args = parser.parse_args()

    direcciones = list(args.direcciones)
    if args.excel:
        import pandas as pd

        df = pd.read_excel(args.excel)
        columna = args.columna or next((c for c in COLUMNAS_DIRECCION if c in df.columns), None)
        if columna is None:
            sys.exit(f"No encontré la columna de dirección. Columnas del archivo: {list(df.columns)}")
        direcciones += df[columna].astype(str).tolist()

    indice = _indice()
    sin_sector = con_zona = 0
    for d in direcciones:
        r = sectorizar(d, indice)
        sin_sector += r.localidad is None
        con_zona += r.zona is not None
        print(f"{d[:60]:<60} | {r.direccion_estandarizada or '-':<22} | "
              f"{r.localidad or 'SIN SECTOR':<16} | {r.zona or '-'}")

    print(f"\nTotal: {len(direcciones)} · con zona: {con_zona} · sin sector: {sin_sector}")


if __name__ == "__main__":
    main()
