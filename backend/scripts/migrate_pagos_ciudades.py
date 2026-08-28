"""
Migra "Facturación Ciudades" de MySQL (logistica) → PostgreSQL (servilla_erp).

Trae la data histórica de prefacturas y cuentas por pagar de couriers/transportadoras
externos, creada en el dashboard Streamlit (pestaña 🏙️ Facturación Ciudades), hacia el
módulo /pagos-ciudades del ERP. Migra tres tablas con esquema idéntico:

    prefacturas_courier   →  prefacturas_courier
    prefactura_planillas  →  prefactura_planillas   (FK prefactura_id remapeada)
    facturas_courier_cxp  →  facturas_courier_cxp   (FK prefactura_id remapeada)

Estrategia (migración histórica única + cutover):
  - PG ya tiene prefacturas creadas desde el ERP → NO se preservan los IDs de MySQL.
    Cada prefactura se inserta con RETURNING id y se guarda pref_id_map[mysql_id] = pg_id
    para remapear las tablas hijas.
  - Deduplicación por planilla: el ERP garantiza que una planilla vive en UNA sola
    prefactura. Si alguna planilla de una prefactura MySQL ya existe en PG, esa prefactura
    ya fue migrada/creada → se omite y se mapea al prefactura_id existente. Esto hace el
    script idempotente (re-ejecutar no duplica).
  - CxP: el ERP permite una sola factura por prefactura → se omite si ya existe una CxP
    para el prefactura_id destino.

Columnas sin equivalente en MySQL (quedan en su default):
  - valor_ajustado / notas_ajuste (migración 014) → NULL.

Notas de tipos:
  - estado: strings idénticos entre el ENUM de MySQL y el VARCHAR+CHECK de PG.
  - created_at: MySQL TIMESTAMP (naive) → columna PG timestamptz; psycopg2 lo acepta
    (se asume la tz del servidor).

Uso:
    python migrate_pagos_ciudades.py            # dry-run (sin cambios)
    python migrate_pagos_ciudades.py --commit   # aplica cambios

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
from collections import defaultdict

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


# Columnas de prefacturas_courier a migrar (mismo orden en el INSERT).
_PREF_COLS = [
    "cod_mensajero", "fecha_generacion", "periodo_desde", "periodo_hasta",
    "cantidad_planillas", "cantidad_local", "cantidad_nacional",
    "valor_local", "valor_nacional", "valor_total", "estado", "notas", "created_at",
]
_PLAN_COLS = [
    "prefactura_id", "planilla", "fecha_escaner", "cantidad_local", "cantidad_nacional",
    "precio_local", "precio_nac", "valor_local", "valor_nac", "valor_total",
]
_CXP_COLS = [
    "prefactura_id", "cod_mensajero", "numero_factura", "fecha_emision",
    "fecha_vencimiento", "valor_total", "estado", "notas", "fecha_pago", "created_at",
]


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
        my_cur.execute("SELECT COUNT(*) AS n FROM prefacturas_courier")
        n_pref_my = my_cur.fetchone()["n"]
        my_cur.execute("SELECT COUNT(*) AS n FROM prefactura_planillas")
        n_plan_my = my_cur.fetchone()["n"]
        my_cur.execute("SELECT COUNT(*) AS n FROM facturas_courier_cxp")
        n_cxp_my = my_cur.fetchone()["n"]

        pg_cur.execute("SELECT COUNT(*) FROM prefacturas_courier")
        n_pref_pg = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM prefactura_planillas")
        n_plan_pg = pg_cur.fetchone()[0]
        pg_cur.execute("SELECT COUNT(*) FROM facturas_courier_cxp")
        n_cxp_pg = pg_cur.fetchone()[0]

        print(f"MySQL — prefacturas: {n_pref_my:4d} | planillas: {n_plan_my:4d} | cxp: {n_cxp_my:4d}")
        print(f"PG    — prefacturas: {n_pref_pg:4d} | planillas: {n_plan_pg:4d} | cxp: {n_cxp_pg:4d}\n")

        # ── 2. Cargar data de MySQL ────────────────────────────────────
        my_cur.execute("SELECT * FROM prefacturas_courier ORDER BY id")
        prefacturas = my_cur.fetchall()

        my_cur.execute("SELECT * FROM prefactura_planillas ORDER BY prefactura_id, id")
        planillas_por_pref = defaultdict(list)
        for row in my_cur.fetchall():
            planillas_por_pref[row["prefactura_id"]].append(row)

        my_cur.execute("SELECT * FROM facturas_courier_cxp ORDER BY id")
        cxps = my_cur.fetchall()

        # ── 3. Migrar prefacturas (+ planillas hijas) ──────────────────
        pref_id_map = {}          # mysql_pref_id → pg_pref_id
        n_pref_ins = n_pref_skip = 0
        n_plan_ins = 0
        warnings = []

        for pf in prefacturas:
            my_id = pf["id"]
            hijas = planillas_por_pref.get(my_id, [])
            nombres_planilla = [str(h["planilla"]) for h in hijas]

            # Dedup por planilla: ¿alguna planilla ya está en PG?
            existentes = {}
            if nombres_planilla:
                pg_cur.execute(
                    "SELECT planilla, prefactura_id FROM prefactura_planillas "
                    "WHERE planilla = ANY(%s)",
                    (nombres_planilla,),
                )
                existentes = {r["planilla"]: r["prefactura_id"] for r in pg_cur.fetchall()}

            if existentes:
                # Ya migrada / creada nativamente en el ERP. Mapear al prefactura_id existente.
                pg_ids = set(existentes.values())
                pref_id_map[my_id] = next(iter(pg_ids))
                n_pref_skip += 1
                if len(pg_ids) > 1:
                    warnings.append(
                        f"Prefactura MySQL id={my_id}: sus planillas apuntan a varias "
                        f"prefacturas PG {sorted(pg_ids)} — mapeada a {pref_id_map[my_id]}"
                    )
                print(f"  [SKIP] prefactura my_id={my_id} ({pf['cod_mensajero']}, "
                      f"${float(pf['valor_total']):,.0f}) → pg_id={pref_id_map[my_id]}")
                continue

            if dry_run:
                pref_id_map[my_id] = f"[NEW:{my_id}]"
                n_pref_ins += 1
                n_plan_ins += len(hijas)
                print(f"  [INSERT] prefactura my_id={my_id} ({pf['cod_mensajero']}, "
                      f"${float(pf['valor_total']):,.0f}) + {len(hijas)} planilla(s)")
                continue

            pg_cur.execute(
                "INSERT INTO prefacturas_courier "
                "(cod_mensajero, fecha_generacion, periodo_desde, periodo_hasta, "
                " cantidad_planillas, cantidad_local, cantidad_nacional, "
                " valor_local, valor_nacional, valor_total, estado, notas, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                tuple(pf[c] for c in _PREF_COLS),
            )
            pg_id = pg_cur.fetchone()[0]
            pref_id_map[my_id] = pg_id
            n_pref_ins += 1

            for h in hijas:
                vals = dict(h)
                vals["prefactura_id"] = pg_id
                pg_cur.execute(
                    "INSERT INTO prefactura_planillas "
                    "(prefactura_id, planilla, fecha_escaner, cantidad_local, cantidad_nacional, "
                    " precio_local, precio_nac, valor_local, valor_nac, valor_total) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    tuple(vals[c] for c in _PLAN_COLS),
                )
                n_plan_ins += 1
            print(f"  [INSERT] prefactura my_id={my_id} → pg_id={pg_id} + {len(hijas)} planilla(s)")

        # ── 4. Migrar CxP ──────────────────────────────────────────────
        n_cxp_ins = n_cxp_skip = n_cxp_sin_pref = 0

        for cx in cxps:
            pg_pref_id = pref_id_map.get(cx["prefactura_id"])
            if pg_pref_id is None:
                n_cxp_sin_pref += 1
                warnings.append(
                    f"CxP MySQL id={cx['id']} ({cx['numero_factura']}): prefactura_id="
                    f"{cx['prefactura_id']} no mapeada → omitida"
                )
                continue

            if dry_run:
                if isinstance(pg_pref_id, str):
                    # Prefactura recién insertada en dry-run (no existe en PG aún) → sería nueva.
                    n_cxp_ins += 1
                    print(f"  [INSERT] cxp {cx['numero_factura']} → prefactura {pg_pref_id}")
                    continue
                pg_cur.execute(
                    "SELECT id FROM facturas_courier_cxp WHERE prefactura_id = %s",
                    (pg_pref_id,),
                )
                if pg_cur.fetchone():
                    n_cxp_skip += 1
                    print(f"  [SKIP] cxp {cx['numero_factura']} (ya existe para prefactura {pg_pref_id})")
                else:
                    n_cxp_ins += 1
                    print(f"  [INSERT] cxp {cx['numero_factura']} → prefactura {pg_pref_id}")
                continue

            pg_cur.execute(
                "SELECT id FROM facturas_courier_cxp WHERE prefactura_id = %s",
                (pg_pref_id,),
            )
            if pg_cur.fetchone():
                n_cxp_skip += 1
                continue

            vals = dict(cx)
            vals["prefactura_id"] = pg_pref_id
            pg_cur.execute(
                "INSERT INTO facturas_courier_cxp "
                "(prefactura_id, cod_mensajero, numero_factura, fecha_emision, "
                " fecha_vencimiento, valor_total, estado, notas, fecha_pago, created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                tuple(vals[c] for c in _CXP_COLS),
            )
            n_cxp_ins += 1
            print(f"  [INSERT] cxp {cx['numero_factura']} → prefactura {pg_pref_id}")

        # ── 5. Ajustar secuencias (evita colisiones de PK futuras) ──────
        if not dry_run:
            for tabla in ("prefacturas_courier", "prefactura_planillas", "facturas_courier_cxp"):
                pg_cur.execute(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 1) FROM " + tabla + "), 1))",
                    (tabla,),
                )

        # ── 6. Commit / rollback ───────────────────────────────────────
        if dry_run:
            pg.rollback()
        else:
            pg.commit()

        # ── 7. Resumen ─────────────────────────────────────────────────
        print("\n" + "=" * 55)
        print(f"  Prefacturas insertadas          : {n_pref_ins}")
        print(f"  Prefacturas omitidas (ya en PG) : {n_pref_skip}")
        print(f"  Planillas insertadas            : {n_plan_ins}")
        print(f"  CxP insertadas                  : {n_cxp_ins}")
        print(f"  CxP omitidas (ya existían)      : {n_cxp_skip}")
        print(f"  CxP sin prefactura mapeada      : {n_cxp_sin_pref}")
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
