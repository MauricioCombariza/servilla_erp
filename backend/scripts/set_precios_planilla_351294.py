"""
Fija precio_mensajero y ambito de los seriales de la planilla 351294 desde un Excel.

Lee /mnt/c/Users/mcomb/Downloads/351294_PRECIOS.xlsx (hoja Hoja1, columnas serial/PRECIO)
y aplica sobre PostgreSQL (servilla_erp.seriales_gestion):

    PRECIO 750  -> precio_mensajero=750,  ambito='bogota'   (local)
    PRECIO 1000 -> precio_mensajero=1000, ambito='nacional' (nacional)

En ambos casos marca editado_manualmente=TRUE (para que el recálculo no lo sobrescriba)
y actualiza fecha_modificacion. El match es por serial (único global), con guard
planilla='351294'.

Uso:
    python set_precios_planilla_351294.py            # dry-run (sin cambios)
    python set_precios_planilla_351294.py --commit   # aplica cambios

Variables de entorno (túnel SSH ya abierto hacia el VPS):
    PostgreSQL — tunnel: ssh -L 5440:127.0.0.1:5440 root@204.168.150.196
        PG_HOST         (default: 127.0.0.1)
        PG_PORT         (default: 5440)
        PG_USER         (default: servilla)
        PG_PASSWORD     (requerida)
        PG_DB           (default: servilla_erp)

    Opcional:
        XLSX_PATH       (default: /mnt/c/Users/mcomb/Downloads/351294_PRECIOS.xlsx)
"""

import argparse
import os
import sys

import openpyxl
import psycopg2

PLANILLA = "351294"
XLSX_PATH = os.environ.get(
    "XLSX_PATH", "/mnt/c/Users/mcomb/Downloads/351294_PRECIOS.xlsx"
)

# Regla precio -> (ambito, etiqueta legible)
PRECIO_A_AMBITO = {
    750: ("bogota", "local"),
    1000: ("nacional", "nacional"),
}

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", 5440))
PG_USER = os.environ.get("PG_USER", "servilla")
PG_PASS = os.environ.get("PG_PASSWORD", "")
PG_DB = os.environ.get("PG_DB", "servilla_erp")


def connect_pg():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASS,
        dbname=PG_DB,
    )


def leer_excel(path):
    """Devuelve {precio: [seriales...]} agrupando por PRECIO. Aborta si hay datos raros."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Hoja1"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    if header[:2] != ("serial", "PRECIO"):
        sys.exit(f"Encabezado inesperado en {path}: {header!r} (esperaba serial/PRECIO)")

    por_precio = {p: [] for p in PRECIO_A_AMBITO}
    for i, row in enumerate(rows[1:], start=2):
        serial, precio = row[0], row[1]
        if serial is None or str(serial).strip() == "":
            sys.exit(f"Fila {i}: serial vacío.")
        if precio not in PRECIO_A_AMBITO:
            sys.exit(
                f"Fila {i}: PRECIO={precio!r} no reconocido "
                f"(solo se aceptan {sorted(PRECIO_A_AMBITO)})."
            )
        por_precio[precio].append(str(serial).strip())

    # Detectar duplicados entre el total
    todos = [s for lst in por_precio.values() for s in lst]
    if len(todos) != len(set(todos)):
        vistos, dups = set(), set()
        for s in todos:
            if s in vistos:
                dups.add(s)
            vistos.add(s)
        sys.exit(f"Seriales duplicados en el Excel: {sorted(dups)[:10]} ...")

    return por_precio


def dry_run(cur, por_precio):
    todos = [s for lst in por_precio.values() for s in lst]
    print(f"Excel: {len(todos)} seriales únicos")
    for precio, seriales in sorted(por_precio.items()):
        ambito, etiqueta = PRECIO_A_AMBITO[precio]
        print(f"  - PRECIO {precio} -> ambito='{ambito}' ({etiqueta}): {len(seriales)}")

    # Existencia y planilla actual
    cur.execute(
        """
        SELECT serial, planilla, ambito, precio_mensajero
          FROM seriales_gestion
         WHERE serial = ANY(%s)
        """,
        (todos,),
    )
    encontrados = cur.fetchall()
    por_serial = {r[0]: r for r in encontrados}

    no_encontrados = [s for s in todos if s not in por_serial]
    otra_planilla = [
        (s, por_serial[s][1]) for s in todos
        if s in por_serial and por_serial[s][1] != PLANILLA
    ]

    print(f"\nEn BD (seriales_gestion): {len(encontrados)} de {len(todos)} encontrados")
    print(f"  No encontrados: {len(no_encontrados)}")
    if no_encontrados:
        print(f"    primeros: {no_encontrados[:15]}")
    print(f"  En otra planilla (<> {PLANILLA}): {len(otra_planilla)}")
    if otra_planilla:
        print(f"    primeros: {otra_planilla[:15]}")

    # Estado actual (solo los que sí están en la planilla objetivo)
    cur.execute(
        """
        SELECT ambito, precio_mensajero, count(*)
          FROM seriales_gestion
         WHERE planilla = %s AND serial = ANY(%s)
         GROUP BY 1, 2 ORDER BY 1, 2
        """,
        (PLANILLA, todos),
    )
    print(f"\nEstado ACTUAL de esos seriales en planilla {PLANILLA} (ambito, precio, n):")
    for ambito, precio, n in cur.fetchall():
        print(f"    {ambito!s:10} {precio!s:10} {n}")

    print("\n(dry-run: no se aplicaron cambios. Usa --commit para aplicar.)")


def aplicar(conn, cur, por_precio):
    esperado_total = 0
    resultados = []
    for precio, seriales in sorted(por_precio.items()):
        ambito, etiqueta = PRECIO_A_AMBITO[precio]
        cur.execute(
            """
            UPDATE seriales_gestion
               SET precio_mensajero = %s,
                   ambito = %s,
                   editado_manualmente = TRUE,
                   fecha_modificacion = now()
             WHERE planilla = %s
               AND serial = ANY(%s)
            """,
            (precio, ambito, PLANILLA, seriales),
        )
        n = cur.rowcount
        resultados.append((precio, ambito, etiqueta, n, len(seriales)))
        esperado_total += len(seriales)
        print(
            f"  UPDATE precio={precio} ambito='{ambito}' ({etiqueta}): "
            f"{n} filas actualizadas (de {len(seriales)} seriales en el Excel)"
        )

    actualizado_total = sum(r[3] for r in resultados)
    print(f"\nTotal actualizado: {actualizado_total} / esperado (Excel): {esperado_total}")

    if actualizado_total == 0:
        conn.rollback()
        sys.exit("Nada actualizado (0 filas). Rollback. Revisa el túnel/planilla/seriales.")

    conn.commit()
    print("COMMIT aplicado.")
    if actualizado_total < esperado_total:
        faltan = esperado_total - actualizado_total
        print(
            f"AVISO: {faltan} seriales del Excel no estaban en la planilla {PLANILLA} "
            f"(no encontrados o en otra planilla). Corre el dry-run para el detalle."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", action="store_true", help="Aplica los cambios (sin esto, dry-run).")
    args = parser.parse_args()

    if not PG_PASS:
        sys.exit("Falta credencial: exporta PG_PASSWORD antes de correr este script.")
    if not os.path.exists(XLSX_PATH):
        sys.exit(f"No existe el archivo Excel: {XLSX_PATH}")

    por_precio = leer_excel(XLSX_PATH)

    conn = connect_pg()
    try:
        cur = conn.cursor()
        if args.commit:
            aplicar(conn, cur, por_precio)
        else:
            dry_run(cur, por_precio)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
