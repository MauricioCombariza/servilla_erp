"""
Reconcilia subsidio_transporte con todo el histórico de registro_horas.

Por cada (personal_id, fecha) en registro_horas con horas trabajadas > 0,
asegura que exista una fila en subsidio_transporte con tipo_subsidio =
'transporte_completo' y la tarifa vigente (plana, $8.333/día trabajado,
sin importar cuántas horas) — sin importar si el registro ya existía con
otro tipo/tarifa (ej. 'medio_transporte' del esquema escalonado anterior)
o si nunca existió (ej. horas migradas desde MySQL vía migrate_mysql.py).

No toca filas ya liquidadas (liquidado = TRUE).

Uso:
    python backfill_subsidio_transporte.py            # dry-run (sin cambios)
    python backfill_subsidio_transporte.py --commit   # aplica cambios
"""

import argparse
import asyncio

from sqlalchemy import text

from app.database import AsyncSessionLocal

_RECONCILE_SQL = """
    INSERT INTO subsidio_transporte (personal_id, fecha, horas_totales, tipo_subsidio, tarifa, origen)
    SELECT
        rh.personal_id,
        rh.fecha,
        SUM(rh.horas_trabajadas) AS horas_totales,
        'transporte_completo',
        (SELECT tarifa FROM tarifas_servicios
         WHERE tipo_servicio = 'transporte_completo' AND activo = TRUE
         ORDER BY vigencia_desde DESC LIMIT 1),
        'recalculado'
    FROM registro_horas rh
    GROUP BY rh.personal_id, rh.fecha
    HAVING SUM(rh.horas_trabajadas) > 0
    ON CONFLICT (personal_id, fecha) DO UPDATE SET
        horas_totales = EXCLUDED.horas_totales,
        tipo_subsidio = EXCLUDED.tipo_subsidio,
        tarifa        = EXCLUDED.tarifa,
        origen        = 'recalculado'
    WHERE subsidio_transporte.liquidado = FALSE
      AND (subsidio_transporte.tipo_subsidio != EXCLUDED.tipo_subsidio
           OR subsidio_transporte.tarifa != EXCLUDED.tarifa
           OR subsidio_transporte.horas_totales != EXCLUDED.horas_totales)
"""

_DRY_RUN_SQL = """
    SELECT
        rh.personal_id, rh.fecha, SUM(rh.horas_trabajadas) AS horas_totales,
        st.tipo_subsidio AS tipo_actual, st.tarifa AS tarifa_actual, st.liquidado
    FROM registro_horas rh
    LEFT JOIN subsidio_transporte st
        ON st.personal_id = rh.personal_id AND st.fecha = rh.fecha
    GROUP BY rh.personal_id, rh.fecha, st.tipo_subsidio, st.tarifa, st.liquidado
    HAVING SUM(rh.horas_trabajadas) > 0
       AND (st.tipo_subsidio IS DISTINCT FROM 'transporte_completo'
            OR st.tarifa IS NULL
            OR st.tarifa != (SELECT tarifa FROM tarifas_servicios
                              WHERE tipo_servicio = 'transporte_completo' AND activo = TRUE
                              ORDER BY vigencia_desde DESC LIMIT 1))
"""


async def main(commit: bool) -> None:
    async with AsyncSessionLocal() as db:
        if not commit:
            print("=== DRY-RUN: use --commit para aplicar ===\n")
            rows = (await db.execute(text(_DRY_RUN_SQL))).mappings().all()
            ya_liquidadas = [r for r in rows if r["liquidado"]]
            pendientes = [r for r in rows if not r["liquidado"]]
            print(f"Filas a crear/corregir: {len(pendientes)}")
            for r in pendientes[:20]:
                print(f"  personal_id={r['personal_id']} fecha={r['fecha']} "
                      f"horas={r['horas_totales']} tipo_actual={r['tipo_actual']} tarifa_actual={r['tarifa_actual']}")
            if len(pendientes) > 20:
                print(f"  ... y {len(pendientes) - 20} más")
            if ya_liquidadas:
                print(f"\n⚠ {len(ya_liquidadas)} filas están desactualizadas pero ya liquidadas — no se tocan.")
            print("\n[DRY-RUN] Sin cambios aplicados. Use --commit para aplicar.")
        else:
            result = await db.execute(text(_RECONCILE_SQL))
            await db.commit()
            print(f"✅ subsidio_transporte reconciliado — {result.rowcount} filas creadas/actualizadas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Aplicar cambios (sin esto es dry-run)")
    args = parser.parse_args()
    asyncio.run(main(args.commit))
