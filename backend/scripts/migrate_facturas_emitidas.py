"""
Migra facturas emitidas a clientes de MySQL (logistica) → PostgreSQL (servilla_erp).

Por cada registro en logistica.facturas_emitidas:
  1. Inserta en PostgreSQL facturas_emitidas (ON CONFLICT DO NOTHING)
  2. Inserta detalles en detalle_facturas_emitidas (ON CONFLICT DO NOTHING)
  3. Inserta pagos en pagos_recibidos (ON CONFLICT DO NOTHING)

Notas:
  - Clientes se mapean por `nit` (clave única en ambas bases), no por nombre_empresa.
  - Si un detalle referencia una orden_id que no existe en PG, se inserta con
    orden_id = NULL (la línea de facturación se conserva; solo se pierde el enlace
    a la orden).
  - pagos_recibidos.usuario_registro_id siempre queda NULL: el dashboard nunca
    lo puebla en el origen.

Uso:
    python migrate_facturas_emitidas.py            # dry-run (sin cambios)
    python migrate_facturas_emitidas.py --commit   # aplica cambios

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


def build_cliente_map(my_cur, pg_cur):
    """
    Retorna {mysql_cliente_id: pg_cliente_id} mapeando por nit.
    """
    my_cur.execute("SELECT id, nit FROM clientes")
    mysql_clientes = {r["id"]: r["nit"] for r in my_cur.fetchall()}

    pg_cur.execute("SELECT id, nit FROM clientes")
    pg_clientes_by_nit = {r[1]: r[0] for r in pg_cur.fetchall()}

    cliente_map = {}
    warnings = []
    for my_id, nit in mysql_clientes.items():
        if nit in pg_clientes_by_nit:
            cliente_map[my_id] = pg_clientes_by_nit[nit]
        else:
            warnings.append(f"Cliente no encontrado en PG: id={my_id} nit='{nit}'")

    return cliente_map, warnings


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

        my_cur.execute("SELECT COUNT(*) AS n FROM facturas_emitidas")
        n_facturas_mysql = my_cur.fetchone()["n"]
        my_cur.execute("SELECT COUNT(*) AS n FROM detalle_facturas_emitidas")
        n_detalles_mysql = my_cur.fetchone()["n"]
        my_cur.execute("SELECT COUNT(*) AS n FROM pagos_recibidos")
        n_pagos_mysql = my_cur.fetchone()["n"]

        pg_cur.execute("SELECT COUNT(*) FROM facturas_emitidas")
        n_facturas_pg = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM detalle_facturas_emitidas")
        n_detalles_pg = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM pagos_recibidos")
        n_pagos_pg = pg_cur.fetchone()[0]

        print(f"MySQL  — facturas: {n_facturas_mysql:4d} | detalles: {n_detalles_mysql:4d} | pagos: {n_pagos_mysql:4d}")
        print(f"PG     — facturas: {n_facturas_pg:4d} | detalles: {n_detalles_pg:4d} | pagos: {n_pagos_pg:4d}\n")

        # ── 2. Mappings ────────────────────────────────────────────────

        cliente_map, cliente_warns = build_cliente_map(my_cur, pg_cur)
        print(f"Clientes mapeados: {len(cliente_map)}")
        for w in cliente_warns:
            print(f"  ⚠ {w}")

        orden_map, orden_warns = build_orden_map(my_cur, pg_cur)
        print(f"Órdenes mapeadas: {len(orden_map)}")
        if orden_warns:
            print(f"  ⚠ {len(orden_warns)} órdenes MySQL sin equivalente en PG (sus detalles quedarán con orden_id NULL)")

        print()

        # ── 3. Cargar facturas de MySQL ────────────────────────────────

        my_cur.execute("""
            SELECT fe.id, fe.numero_factura, fe.cliente_id, fe.fecha_emision,
                   fe.fecha_vencimiento, fe.periodo_mes, fe.periodo_anio,
                   fe.cantidad_items, fe.subtotal, fe.descuento, fe.total,
                   fe.saldo_pendiente, fe.estado, fe.observaciones, fe.fecha_creacion
            FROM facturas_emitidas fe
            ORDER BY fe.fecha_emision, fe.id
        """)
        facturas = my_cur.fetchall()

        # ── 4. Cargar detalles de MySQL ────────────────────────────────

        my_cur.execute("""
            SELECT id, factura_id, orden_id, descripcion, cantidad, precio_unitario, subtotal
            FROM detalle_facturas_emitidas
            ORDER BY factura_id, id
        """)
        detalles = my_cur.fetchall()

        # ── 5. Cargar pagos de MySQL ─────────────────────────────────────

        my_cur.execute("""
            SELECT id, factura_id, fecha_pago, monto, metodo_pago, referencia,
                   observaciones, fecha_creacion
            FROM pagos_recibidos
            ORDER BY factura_id, id
        """)
        pagos = my_cur.fetchall()

        # ── 6. Migrar facturas ─────────────────────────────────────────

        # mysql_factura_id → pg_factura_id (para mapear detalles y pagos)
        factura_id_map = {}
        n_insertadas = 0
        n_omitidas   = 0
        n_sin_cliente = 0
        warnings = []

        for f in facturas:
            pg_cliente_id = cliente_map.get(f["cliente_id"])
            if pg_cliente_id is None:
                n_sin_cliente += 1
                warnings.append(
                    f"Factura id={f['id']} ({f['numero_factura']}): "
                    f"cliente_id={f['cliente_id']} no mapeado → omitida"
                )
                continue

            if dry_run:
                # Simular: buscar si ya existe
                pg_cur.execute(
                    "SELECT id FROM facturas_emitidas WHERE numero_factura = %s",
                    (f["numero_factura"],)
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
                    f"({f['fecha_emision']}) cliente_pg={pg_cliente_id} "
                    f"total={f['total']:,.0f} estado={f['estado']}"
                )
            else:
                pg_cur.execute("""
                    INSERT INTO facturas_emitidas
                        (numero_factura, cliente_id, fecha_emision, fecha_vencimiento,
                         periodo_mes, periodo_anio, cantidad_items, subtotal, descuento,
                         total, saldo_pendiente, estado, observaciones, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (numero_factura) DO NOTHING
                    RETURNING id
                """, (
                    f["numero_factura"], pg_cliente_id, f["fecha_emision"], f["fecha_vencimiento"],
                    f["periodo_mes"], f["periodo_anio"], f["cantidad_items"], f["subtotal"], f["descuento"],
                    f["total"], f["saldo_pendiente"], f["estado"], f["observaciones"], f["fecha_creacion"],
                ))
                row = pg_cur.fetchone()
                if row:
                    factura_id_map[f["id"]] = row[0]
                    n_insertadas += 1
                    print(f"  [INSERT] factura {f['numero_factura']} → pg_id={row[0]}")
                else:
                    # ya existía — recuperar su id para mapear detalles y pagos
                    pg_cur.execute(
                        "SELECT id FROM facturas_emitidas WHERE numero_factura = %s",
                        (f["numero_factura"],)
                    )
                    existing = pg_cur.fetchone()
                    if existing:
                        factura_id_map[f["id"]] = existing[0]
                    n_omitidas += 1

        # ── 7. Migrar detalles ─────────────────────────────────────────

        n_det_insertados = 0
        n_det_omitidos   = 0
        n_det_sin_factura = 0
        n_det_sin_orden_null = 0

        for d in detalles:
            pg_factura_id = factura_id_map.get(d["factura_id"])
            if pg_factura_id is None or isinstance(pg_factura_id, str):
                n_det_sin_factura += 1
                continue

            pg_orden_id = orden_map.get(d["orden_id"])
            if d["orden_id"] is not None and pg_orden_id is None:
                n_det_sin_orden_null += 1

            # Verificar si ya existe (no hay UNIQUE constraint en PG, se controla manualmente)
            pg_cur.execute(
                "SELECT id FROM detalle_facturas_emitidas "
                "WHERE factura_id = %s AND descripcion = %s AND cantidad = %s AND precio_unitario = %s",
                (pg_factura_id, d["descripcion"], d["cantidad"], d["precio_unitario"])
            )
            existing = pg_cur.fetchone()
            if existing:
                n_det_omitidos += 1
                continue

            if dry_run:
                n_det_insertados += 1
            else:
                pg_cur.execute("""
                    INSERT INTO detalle_facturas_emitidas
                        (factura_id, orden_id, descripcion, cantidad, precio_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pg_factura_id, pg_orden_id, d["descripcion"], d["cantidad"], d["precio_unitario"], d["subtotal"]))
                n_det_insertados += 1

        # ── 8. Migrar pagos ────────────────────────────────────────────

        n_pago_insertados = 0
        n_pago_omitidos   = 0
        n_pago_sin_factura = 0

        for p in pagos:
            pg_factura_id = factura_id_map.get(p["factura_id"])
            if pg_factura_id is None or isinstance(pg_factura_id, str):
                n_pago_sin_factura += 1
                continue

            pg_cur.execute(
                "SELECT id FROM pagos_recibidos "
                "WHERE factura_id = %s AND fecha_pago = %s AND monto = %s "
                "AND COALESCE(referencia,'') = COALESCE(%s,'')",
                (pg_factura_id, p["fecha_pago"], p["monto"], p["referencia"])
            )
            existing = pg_cur.fetchone()
            if existing:
                n_pago_omitidos += 1
                continue

            if dry_run:
                n_pago_insertados += 1
            else:
                pg_cur.execute("""
                    INSERT INTO pagos_recibidos
                        (factura_id, fecha_pago, monto, metodo_pago, referencia,
                         observaciones, usuario_registro_id, fecha_creacion)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s)
                """, (
                    pg_factura_id, p["fecha_pago"], p["monto"], p["metodo_pago"],
                    p["referencia"], p["observaciones"], p["fecha_creacion"],
                ))
                n_pago_insertados += 1

        # ── 9. Commit / rollback ───────────────────────────────────────

        if dry_run:
            pg.rollback()
        else:
            pg.commit()

        # ── 10. Resumen ────────────────────────────────────────────────

        print("\n" + "=" * 55)
        print(f"  Facturas insertadas             : {n_insertadas}")
        print(f"  Facturas omitidas (ya existían)  : {n_omitidas}")
        print(f"  Facturas sin cliente (omitidas)  : {n_sin_cliente}")
        print(f"  Detalles insertados              : {n_det_insertados}")
        print(f"  Detalles omitidos                : {n_det_omitidos}")
        print(f"  Detalles sin factura mapeada     : {n_det_sin_factura}")
        print(f"  Detalles con orden_id → NULL     : {n_det_sin_orden_null}")
        print(f"  Pagos insertados                 : {n_pago_insertados}")
        print(f"  Pagos omitidos                   : {n_pago_omitidos}")
        print(f"  Pagos sin factura mapeada        : {n_pago_sin_factura}")
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
