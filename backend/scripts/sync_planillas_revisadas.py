"""
Sincroniza planillas revisadas de MySQL VPS (gestiones_mensajero) → PostgreSQL (seriales_gestion).

Por cada planilla en logistica.planillas_revisadas:
  1. UPDATE seriales_gestion: cod_men + mensajero_id (toda la planilla)
  2. UPDATE seriales_gestion: precio_mensajero por orden

Uso:
    python sync_planillas_revisadas.py                  # dry-run
    python sync_planillas_revisadas.py --commit          # aplica cambios
    python sync_planillas_revisadas.py --planilla 351290 --commit
"""

import argparse

import pymysql
import psycopg2
import psycopg2.extras

# MySQL VPS logistica — tunnel: ssh -L 3307:127.0.0.1:3306 root@204.168.150.196
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3307
MYSQL_USER = "root"
MYSQL_PASS = "Root2024!"
MYSQL_DB   = "logistica"

# PostgreSQL VPS — tunnel: ssh -L 5440:127.0.0.1:5440 root@204.168.150.196
PG_HOST = "127.0.0.1"
PG_PORT = 5440
PG_USER = "servilla"
PG_PASS = "Vale2010"
PG_DB   = "servilla_erp"


def connect_mysql():
    return pymysql.connect(
        host=MYSQL_HOST, port=MYSQL_PORT,
        user=MYSQL_USER, password=MYSQL_PASS,
        database=MYSQL_DB, cursorclass=pymysql.cursors.DictCursor,
    )


def connect_pg():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        dbname=PG_DB,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit",   action="store_true")
    parser.add_argument("--planilla", help="Limitar a una planilla específica")
    args = parser.parse_args()

    dry_run = not args.commit
    if dry_run:
        print("=== DRY-RUN: use --commit para aplicar ===\n")

    my = connect_mysql()
    pg = connect_pg()

    try:
        my_cur = my.cursor()
        pg_cur = pg.cursor()

        # ── 1. Cargar todo en memoria desde MySQL ─────────────────────

        # Planillas revisadas
        if args.planilla:
            my_cur.execute(
                "SELECT lot_esc FROM planillas_revisadas WHERE lot_esc = %s",
                (args.planilla,)
            )
        else:
            my_cur.execute("SELECT lot_esc FROM planillas_revisadas")
        planillas_revisadas = {r["lot_esc"] for r in my_cur.fetchall()}
        print(f"Planillas revisadas en MySQL: {len(planillas_revisadas)}")

        # gestiones_mensajero editadas: (lot_esc, cod_mensajero, orden) → precio máximo
        if args.planilla:
            my_cur.execute("""
                SELECT lot_esc, cod_mensajero, orden, MAX(valor_unitario) AS precio
                FROM gestiones_mensajero
                WHERE lot_esc = %s AND editado_manualmente = 1
                GROUP BY lot_esc, cod_mensajero, orden
            """, (args.planilla,))
        else:
            my_cur.execute("""
                SELECT lot_esc, cod_mensajero, orden, MAX(valor_unitario) AS precio
                FROM gestiones_mensajero
                WHERE editado_manualmente = 1
                GROUP BY lot_esc, cod_mensajero, orden
            """)
        gm_rows = my_cur.fetchall()
        print(f"Filas editadas en gestiones_mensajero: {len(gm_rows)}")

        # ── 2. Construir estructuras en memoria ───────────────────────

        # Por planilla: set de cod_mensajero y mapa orden→precio
        from collections import defaultdict
        planilla_mensajeros: dict[str, set] = defaultdict(set)
        planilla_precios:    dict[str, dict] = defaultdict(dict)  # {planilla: {orden: precio}}

        for r in gm_rows:
            lot = r["lot_esc"]
            if lot not in planillas_revisadas:
                continue
            if r["cod_mensajero"]:
                planilla_mensajeros[lot].add(r["cod_mensajero"])
            orden = str(r["orden"]) if r["orden"] else None
            precio = float(r["precio"]) if r["precio"] else 0.0
            if orden and precio > 0:
                # Si ya hay precio para esta orden, tomar el mayor
                if orden not in planilla_precios[lot] or precio > planilla_precios[lot][orden]:
                    planilla_precios[lot][orden] = precio

        # ── 3. Cargar planillas existentes en PG ──────────────────────
        if args.planilla:
            pg_cur.execute(
                "SELECT DISTINCT planilla FROM seriales_gestion WHERE planilla = %s",
                (args.planilla,)
            )
        else:
            pg_cur.execute("SELECT DISTINCT planilla FROM seriales_gestion")
        planillas_en_pg = {r[0] for r in pg_cur.fetchall()}
        print(f"Planillas en seriales_gestion (PG): {len(planillas_en_pg)}\n")

        # ── 4. Cargar personal PG: codigo → id ───────────────────────
        pg_cur.execute("SELECT codigo, id FROM personal")
        personal_map = {r[0]: r[1] for r in pg_cur.fetchall()}

        # ── 5. Aplicar updates ────────────────────────────────────────
        total_procesadas      = 0
        total_skip_no_pg      = 0
        total_skip_sin_edits  = 0
        total_men_seriales    = 0
        total_precio_seriales = 0
        warnings = []

        for planilla in sorted(planillas_revisadas):
            if planilla not in planillas_en_pg:
                total_skip_no_pg += 1
                continue

            cod_men_set = planilla_mensajeros.get(planilla, set())
            precio_map  = planilla_precios.get(planilla, {})

            if not cod_men_set and not precio_map:
                total_skip_sin_edits += 1
                continue

            total_procesadas += 1

            # UPDATE mensajero
            if len(cod_men_set) == 1:
                cod_men = next(iter(cod_men_set))
                mensajero_id = personal_map.get(cod_men)
                if mensajero_id is None:
                    msg = f"[{planilla}] mensajero {cod_men} no encontrado en PG"
                    print(f"  ⚠ {msg}")
                    warnings.append(msg)
                else:
                    if dry_run:
                        pg_cur.execute(
                            "SELECT COUNT(*) FROM seriales_gestion WHERE planilla = %s",
                            (planilla,)
                        )
                        n = pg_cur.fetchone()[0]
                    else:
                        pg_cur.execute("""
                            UPDATE seriales_gestion
                            SET cod_men = %s, mensajero_id = %s
                            WHERE planilla = %s
                        """, (cod_men, mensajero_id, planilla))
                        n = pg_cur.rowcount
                    print(f"[{planilla}] mensajero → {cod_men}: {n} seriales{'  [DRY]' if dry_run else ''}")
                    total_men_seriales += n
            elif len(cod_men_set) > 1:
                msg = f"[{planilla}] múltiples mensajeros {cod_men_set} — skip mensajero"
                print(f"  ⚠ {msg}")
                warnings.append(msg)

            # UPDATE precio por orden
            for orden, precio in precio_map.items():
                if dry_run:
                    pg_cur.execute(
                        "SELECT COUNT(*) FROM seriales_gestion WHERE planilla = %s AND orden = %s",
                        (planilla, orden)
                    )
                    n = pg_cur.fetchone()[0]
                else:
                    pg_cur.execute("""
                        UPDATE seriales_gestion
                        SET precio_mensajero = %s, editado_manualmente = TRUE
                        WHERE planilla = %s AND orden = %s
                    """, (precio, planilla, orden))
                    n = pg_cur.rowcount
                if n > 0:
                    print(f"[{planilla}] orden {orden}: ${precio:,.0f} → {n} seriales{'  [DRY]' if dry_run else ''}")
                total_precio_seriales += n

        if dry_run:
            pg.rollback()
        else:
            pg.commit()

        print("\n" + "=" * 50)
        print(f"  Planillas procesadas        : {total_procesadas}")
        print(f"  Sin seriales en PG (skip)   : {total_skip_no_pg}")
        print(f"  Sin ediciones en GM (skip)  : {total_skip_sin_edits}")
        print(f"  Seriales mensajero          : {total_men_seriales}")
        print(f"  Seriales precio             : {total_precio_seriales}")
        print(f"  Advertencias                : {len(warnings)}")
        if warnings:
            print("\nAdvertencias:")
            for w in warnings:
                print(f"  ⚠ {w}")
        if dry_run:
            print("\n[DRY-RUN] Ningún cambio aplicado. Use --commit para aplicar.")
        else:
            print("\n✅ Cambios aplicados en PostgreSQL.")

    finally:
        my.close()
        pg.close()


if __name__ == "__main__":
    main()
