"""
One-time: libera (vuelve a estado='pendiente') los seriales que quedaron
archivados bajo una liquidación de junio ya PAGADA, cuyo f_esc corregido
resultó ser de julio, para que puedan incluirse en una liquidación de julio.

Decisión de negocio explícita (confirmada 2026-08-04): el total_a_pagar de la
liquidación de junio original NO se toca — el dinero ya transferido en esas
17 liquidaciones se queda como está. Estos seriales, al liberarse, volverán a
sumar en la siguiente liquidación de julio que se genere para cada mensajero,
lo que significa que ese trabajo se paga una segunda vez (en algunos casos a
un precio distinto al original, porque precio_mensajero pudo cambiar desde el
pago). Este es un efecto conocido y aceptado, no un descuido del script.

Alcance: solo seriales con estado='liquidado', f_esc >= 2026-07-01, cuya
liquidación actual tiene periodo_mes=6 y periodo_anio=2026 y estado='pagada'.
No toca seriales de liquidaciones 'generada' (esas ya están correctamente
archivadas en julio, no pagadas todavía — no hay nada que liberar ahí).

Uso:
    DATABASE_URL="postgresql://servilla:PASS@localhost:5440/servilla_erp" \
    python scripts/liberar_seriales_julio_de_liquidacion_junio.py           # solo reporta
    python scripts/liberar_seriales_julio_de_liquidacion_junio.py --apply    # aplica
"""

import argparse
import os
import sys
from contextlib import contextmanager
from datetime import date

FECHA_LIMITE = date(2026, 7, 1)


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                     help="Aplica la liberación (por defecto solo reporta)")
    args = ap.parse_args()

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: Define DATABASE_URL antes de ejecutar")
        sys.exit(1)

    with pg_conn(db_url.replace("+asyncpg", "")) as (conn, cur):
        cur.execute("""
            SELECT sg.id, sg.serial, sg.precio_mensajero, l.numero_liquidacion, l.personal_id
            FROM seriales_gestion sg
            JOIN liquidaciones l ON l.id = sg.liquidacion_id
            WHERE sg.estado = 'liquidado' AND sg.f_esc >= %s
              AND l.periodo_mes = 6 AND l.periodo_anio = 2026 AND l.estado = 'pagada'
        """, (FECHA_LIMITE,))
        rows = cur.fetchall()

        por_liq: dict = {}
        for r in rows:
            k = r["numero_liquidacion"]
            por_liq.setdefault(k, {"n": 0, "monto": 0.0})
            por_liq[k]["n"] += 1
            por_liq[k]["monto"] += float(r["precio_mensajero"])

        total_monto = sum(v["monto"] for v in por_liq.values())
        print(f"Seriales a liberar: {len(rows):,} en {len(por_liq)} liquidaciones de junio (ya pagadas)")
        for numero, v in sorted(por_liq.items()):
            print(f"  {numero}: {v['n']} seriales, ${v['monto']:,.2f} (precio actual)")
        print(f"\nTotal a precio actual: ${total_monto:,.2f}")
        print("Las liquidaciones de junio NO se modifican (su total_a_pagar queda igual).")
        print("Estos seriales quedarán disponibles para una liquidación de julio nueva.")

        if not args.apply:
            print("\n(reporte only — no se aplicó ningún cambio; pasar --apply para aplicar)")
            return

        ids = [r["id"] for r in rows]
        cur.execute("""
            UPDATE seriales_gestion
            SET estado = 'pendiente', liquidacion_id = NULL
            WHERE id = ANY(%s)
        """, (ids,))
        conn.commit()
        print(f"\nLiberados: {cur.rowcount:,} seriales (estado='pendiente', liquidacion_id=NULL)")


if __name__ == "__main__":
    main()
