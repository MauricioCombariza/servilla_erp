"""
Migra facturas de transporte de MySQL (logistica) → PostgreSQL (servilla_erp).

Por cada registro en logistica.facturas_transporte:
  1. Inserta en PostgreSQL facturas_transporte (ON CONFLICT DO NOTHING)
  2. Inserta detalles en detalle_facturas_transporte (ON CONFLICT DO NOTHING)
  3. Actualiza ordenes.costo_flete_total en PostgreSQL

Columnas sin equivalente en MySQL:
  - monto_pagado: se infiere del estado (pagada → monto_total, sino → 0)
  - fecha_vencimiento: NULL (no existe en dashboard)

Uso:
    python migrate_facturas_transporte.py            # dry-run (sin cambios)
    python migrate_facturas_transporte.py --commit   # aplica cambios

Variables de entorno (túneles SSH ya abiertos hacia el VPS):
    MySQL logistica — tunnel: ssh -L 3307:127.0.0.1:3306 root@<vps>
        MYSQL_HOST      (default: 127.0.0.1)
        MYSQL_PORT      (default: 3307)
        MYSQL_USER      (default: root)
        MYSQL_PASSWORD  (requerida)
        MYSQL_DB_LOGISTICA (default: logistica)

    PostgreSQL — tunnel: ssh -L 5440:127.0.0.1:5440 root@<vps>
        PG_HOST         (default: 127.0.0.1)
        PG_PORT         (default: 5440)
        PG_USER         (default: servilla)
        PG_PASSWORD     (requerida)
        PG_DB           (default: servilla_erp)
"""

import argparse
import os
import sys

import pymysql
import psycopg2
import psycopg2.extras

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3307))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASS = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB   = os.environ.get("MYSQL_DB_LOGISTICA", "logistica")

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", 5440))
PG_USER = os.environ.get("PG_USER", "servilla")
PG_PASS = os.environ.get("PG_PASSWORD", "")
PG_DB   = os.environ.get("PG_DB", "servilla_erp")

if not MYSQL_PASS or not PG_PASS:
    sys.exit(
        "Faltan credenciales: exporta MYSQL_PASSWORD y PG_PASSWORD "
        "antes de correr este script."
    )


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


def build_personal_map(my_cur, pg_cur):
    """
    Retorna {mysql_personal_id: pg_personal_id} mapeando por nombre_completo.
    Si los IDs coinciden directamente, también los incluye.
    """
    my_cur.execute(
        "SELECT id, nombre_completo FROM personal "
        "WHERE tipo_personal IN ('courier_externo','transportadora')"
    )
    mysql_personal = {r["id"]: r["nombre_completo"] for r in my_cur.fetchall()}

    pg_cur.execute(
        "SELECT id, nombre_completo FROM personal "
        "WHERE tipo_personal IN ('courier_externo','transportadora')"
    )
    pg_personal_by_nombre = {r[1]: r[0] for r in pg_cur.fetchall()}
    pg_personal_by_id     = {r[0]: r[1] for r in pg_cur.fetchall()} if False else {}

    # reconstruir pg_personal_by_id desde el cursor ya consumido
    pg_cur.execute(
        "SELECT id, nombre_completo FROM personal "
        "WHERE tipo_personal IN ('courier_externo','transportadora')"
    )
    pg_personal_by_id = {r[0]: r[1] for r in pg_cur.fetchall()}

    personal_map = {}
    warnings = []
    for my_id, nombre in mysql_personal.items():
        if nombre in pg_personal_by_nombre:
            personal_map[my_id] = pg_personal_by_nombre[nombre]
        else:
            warnings.append(f"Personal no encontrado en PG: id={my_id} nombre='{nombre}'")

    return personal_map, warnings


def build_orden_map(my_cur, pg_cur):
    """
    Retorna {mysql_orden_id: pg_orden_id} mapeando por numero_orden.
    """
    my_cur.execute("SELECT id, numero_orden FROM ordenes")
    mysql_ordenes = {r["id"]: r["numero_orden"] for r in my_cur.fetchall()}

    pg_cur.execute("SELECT id, numero_orden FROM ordenes")
    pg_ordenes_by_numero = {r[1]: r[0] for r in pg_cur.fetchall()}

    orden_map = {}
    warnings = []
    for my_id, numero in mysql_ordenes.items():
        if numero in pg_ordenes_by_numero:
            orden_map[my_id] = pg_ordenes_by_numero[numero]
        else:
            warnings.append(f"Orden no encontrada en PG: id={my_id} numero='{numero}'")

    return orden_map, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Aplicar cambios (sin esto es dry-run)")
    args = parser.parse_args()

    dry_run = not args.commit
    if dry_run:
        print("=== DRY-RUN: use --commit para aplicar ===\n")

    my = connect_mysql()
    pg = connect_pg()

    try:
        my_cur = my.cursor()
        pg_cur = pg.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # ── 1. Diagnóstico inicial ─────────────────────────────────────

        my_cur.execute("SELECT COUNT(*) AS n FROM facturas_transporte")
        n_facturas_mysql = my_cur.fetchone()["n"]
        my_cur.execute("SELECT COUNT(*) AS n FROM detalle_facturas_transporte")
        n_detalles_mysql = my_cur.fetchone()["n"]

        pg_cur.execute("SELECT COUNT(*) FROM facturas_transporte")
        n_facturas_pg = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM detalle_facturas_transporte")
        n_detalles_pg = pg_cur.fetchone()[0]

        print(f"MySQL  — facturas: {n_facturas_mysql:4d} | detalles: {n_detalles_mysql:4d}")
        print(f"PG     — facturas: {n_facturas_pg:4d} | detalles: {n_detalles_pg:4d}\n")

        # ── 2. Mappings ────────────────────────────────────────────────

        personal_map, personal_warns = build_personal_map(my_cur, pg_cur)
        print(f"Personal mapeados: {len(personal_map)}")
        for w in personal_warns:
            print(f"  ⚠ {w}")

        orden_map, orden_warns = build_orden_map(my_cur, pg_cur)
        print(f"Órdenes mapeadas: {len(orden_map)}")
        if orden_warns:
            print(f"  ⚠ {len(orden_warns)} órdenes MySQL sin equivalente en PG (se omitirán sus detalles)")

        print()

        # ── 3. Cargar facturas de MySQL ────────────────────────────────

        my_cur.execute("""
            SELECT ft.id, ft.numero_factura, ft.fecha_factura,
                   ft.courrier_id, ft.monto_total, ft.total_sobres,
                   ft.estado, ft.observaciones, ft.fecha_creacion
            FROM facturas_transporte ft
            ORDER BY ft.fecha_factura, ft.id
        """)
        facturas = my_cur.fetchall()

        # ── 4. Cargar detalles de MySQL ────────────────────────────────

        my_cur.execute("""
            SELECT id, factura_id, orden_id, cantidad_sobres, costo_asignado
            FROM detalle_facturas_transporte
            ORDER BY factura_id, id
        """)
        detalles = my_cur.fetchall()

        # ── 5. Migrar facturas ─────────────────────────────────────────

        # mysql_factura_id → pg_factura_id (para mapear detalles)
        factura_id_map = {}
        n_insertadas = 0
        n_omitidas   = 0
        n_sin_courrier = 0
        warnings = []

        for f in facturas:
            pg_courrier_id = personal_map.get(f["courrier_id"])
            if pg_courrier_id is None:
                n_sin_courrier += 1
                warnings.append(
                    f"Factura id={f['id']} ({f['numero_factura']}): "
                    f"courrier_id={f['courrier_id']} no mapeado → omitida"
                )
                continue

            monto_pagado = f["monto_total"] if f["estado"] == "pagada" else 0

            if dry_run:
                # Simular: buscar si ya existe
                pg_cur.execute(
                    "SELECT id FROM facturas_transporte WHERE numero_factura = %s AND courrier_id = %s",
                    (f["numero_factura"], pg_courrier_id)
                )
                existing = pg_cur.fetchone()
                if existing:
                    factura_id_map[f["id"]] = existing[0]
                    n_omitidas += 1
                else:
                    factura_id_map[f["id"]] = f"[NEW:{f['id']}]"
                    n_insertadas += 1
                print(
                    f"  {'[SKIP]' if existing else '[INSERT]'} factura {f['numero_factura']} "
                    f"({f['fecha_factura']}) courrier_pg={pg_courrier_id} "
                    f"monto={f['monto_total']:,.0f} estado={f['estado']}"
                )
            else:
                pg_cur.execute("""
                    INSERT INTO facturas_transporte
                        (numero_factura, fecha_factura, courrier_id,
                         monto_total, total_sobres, estado,
                         observaciones, monto_pagado, fecha_vencimiento, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s)
                    ON CONFLICT (numero_factura, courrier_id) DO NOTHING
                    RETURNING id
                """, (
                    f["numero_factura"], f["fecha_factura"], pg_courrier_id,
                    f["monto_total"], f["total_sobres"], f["estado"],
                    f["observaciones"], monto_pagado, f["fecha_creacion"],
                ))
                row = pg_cur.fetchone()
                if row:
                    factura_id_map[f["id"]] = row[0]
                    n_insertadas += 1
                    print(f"  [INSERT] factura {f['numero_factura']} → pg_id={row[0]}")
                else:
                    # ya existía — recuperar su id para mapear detalles
                    pg_cur.execute(
                        "SELECT id FROM facturas_transporte WHERE numero_factura = %s AND courrier_id = %s",
                        (f["numero_factura"], pg_courrier_id)
                    )
                    existing = pg_cur.fetchone()
                    if existing:
                        factura_id_map[f["id"]] = existing[0]
                    n_omitidas += 1

        # ── 6. Migrar detalles ─────────────────────────────────────────

        n_det_insertados = 0
        n_det_omitidos   = 0
        n_det_sin_factura = 0
        n_det_sin_orden   = 0

        # IDs de órdenes a actualizar
        ordenes_a_actualizar = set()

        for d in detalles:
            pg_factura_id = factura_id_map.get(d["factura_id"])
            if pg_factura_id is None or isinstance(pg_factura_id, str):
                n_det_sin_factura += 1
                continue

            pg_orden_id = orden_map.get(d["orden_id"])
            if pg_orden_id is None:
                n_det_sin_orden += 1
                continue

            # Verificar si ya existe (no hay UNIQUE constraint en PG, se controla manualmente)
            pg_cur.execute(
                "SELECT id FROM detalle_facturas_transporte WHERE factura_id = %s AND orden_id = %s",
                (pg_factura_id, pg_orden_id)
            )
            existing = pg_cur.fetchone()
            if existing:
                n_det_omitidos += 1
                continue

            if dry_run:
                n_det_insertados += 1
                ordenes_a_actualizar.add(pg_orden_id)
            else:
                pg_cur.execute("""
                    INSERT INTO detalle_facturas_transporte
                        (factura_id, orden_id, cantidad_sobres, costo_asignado)
                    VALUES (%s, %s, %s, %s)
                """, (pg_factura_id, pg_orden_id, d["cantidad_sobres"], d["costo_asignado"]))
                n_det_insertados += 1
                ordenes_a_actualizar.add(pg_orden_id)

        # ── 7. Actualizar costo_flete_total en ordenes ─────────────────

        n_ordenes_actualizadas = 0
        for pg_orden_id in ordenes_a_actualizar:
            if dry_run:
                pg_cur.execute("""
                    SELECT COALESCE(SUM(costo_asignado), 0)
                    FROM detalle_facturas_transporte
                    WHERE orden_id = %s
                """, (pg_orden_id,))
                costo = pg_cur.fetchone()[0]
                print(f"  [DRY] ordenes id={pg_orden_id} costo_flete_total → {float(costo):,.0f}")
                n_ordenes_actualizadas += 1
            else:
                pg_cur.execute("""
                    UPDATE ordenes
                    SET costo_flete_total = (
                        SELECT COALESCE(SUM(costo_asignado), 0)
                        FROM detalle_facturas_transporte
                        WHERE orden_id = %s
                    )
                    WHERE id = %s
                """, (pg_orden_id, pg_orden_id))
                if pg_cur.rowcount > 0:
                    n_ordenes_actualizadas += 1

        # ── 8. Commit / rollback ───────────────────────────────────────

        if dry_run:
            pg.rollback()
        else:
            pg.commit()

        # ── 9. Resumen ─────────────────────────────────────────────────

        print("\n" + "=" * 55)
        print(f"  Facturas insertadas           : {n_insertadas}")
        print(f"  Facturas omitidas (ya existían): {n_omitidas}")
        print(f"  Facturas sin courrier (omitidas): {n_sin_courrier}")
        print(f"  Detalles insertados           : {n_det_insertados}")
        print(f"  Detalles omitidos             : {n_det_omitidos}")
        print(f"  Detalles sin factura mapeada  : {n_det_sin_factura}")
        print(f"  Detalles sin orden mapeada    : {n_det_sin_orden}")
        print(f"  Órdenes actualizadas (flete)  : {n_ordenes_actualizadas}")
        if warnings:
            print("\n  Advertencias:")
            for w in warnings:
                print(f"    ⚠ {w}")
        if dry_run:
            print("\n[DRY-RUN] Sin cambios aplicados. Use --commit para migrar.")
        else:
            print("\n✅ Migración completada en PostgreSQL.")

    finally:
        my.close()
        pg.close()


if __name__ == "__main__":
    main()
