"""
Ingresos mes a mes de un mensajero/courier (cod_mensajero), histórico completo.

Este script alimenta una carta de certificación de ingresos por prestación de
servicios, así que prioriza trazabilidad y auditabilidad sobre velocidad:
para cada mes distingue montos ya liquidados/facturados formalmente (fuente
autorizada, incluye ajustes manuales) de montos apenas estimados a partir de
seriales/planillas aún no cerrados (nunca deben presentarse como pago cierto
en un documento legal). El ancla de período usada en todo el script es
`f_esc` (fecha de escaneo/entrega) — la misma que usa el flujo de
liquidaciones — no `f_emi`, que otros reportes del sistema usan para otros
fines.

Rama según `personal.tipo_personal`:
  - courier_externo / transportadora -> prefacturas_courier / prefactura_planillas
        / facturas_courier_cxp (igual que reporte_planillas_courier.py)
  - cualquier otro valor (interno)   -> liquidaciones / seriales_gestion
        / registro_horas / registro_labores / subsidio_transporte

La conexión se abre en modo solo-lectura (`set_session(readonly=True)`) y el
script nunca hace commit — no debe poder escribir nada en la base.

Uso:
    python certificacion_ingresos_mensajero.py                  # cod 0260
    python certificacion_ingresos_mensajero.py --cod 1006
    python certificacion_ingresos_mensajero.py --cod 0260 --hasta 2026-07-31
    python certificacion_ingresos_mensajero.py --cod 0260 --formato json

Variables de entorno (túnel SSH ya abierto hacia el VPS):
    PostgreSQL — tunnel: ssh -L 5440:127.0.0.1:5440 root@204.168.150.196
        PG_HOST         (default: 127.0.0.1)
        PG_PORT         (default: 5440)
        PG_USER         (default: servilla)
        PG_PASSWORD     (requerida)
        PG_DB           (default: servilla_erp)
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from decimal import Decimal

import psycopg2
import psycopg2.extras

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", 5440))
PG_USER = os.environ.get("PG_USER", "servilla")
PG_PASS = os.environ.get("PG_PASSWORD", "")
PG_DB = os.environ.get("PG_DB", "servilla_erp")

DOWNLOADS_DIR = "/mnt/c/Users/mcomb/Downloads"

TWO_PLACES = Decimal("0.01")

CSV_COLUMNS = [
    "anio", "mes", "fuente", "total_mes", "monto_liquidado",
    "monto_pendiente_adicional", "cantidad", "ajuste_aplicado", "notas", "detalle",
]


def D(x) -> Decimal:
    """Convierte a Decimal de forma segura (None -> 0)."""
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def connect_pg():
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASS, dbname=PG_DB)
    conn.set_session(readonly=True)
    return conn


def fetch_personal(cur, cod):
    cur.execute(
        "SELECT id, codigo, nombre_completo, identificacion, tipo_personal, fecha_ingreso, activo "
        "FROM personal WHERE codigo = %s",
        (cod,),
    )
    return cur.fetchone()


def _mes_vacio(anio, mes):
    return {
        "anio": anio, "mes": mes, "fuente": "sin actividad",
        "total_mes": Decimal("0.00"), "monto_liquidado": Decimal("0.00"),
        "monto_pendiente_adicional": Decimal("0.00"), "cantidad": 0,
        "ajuste_aplicado": False, "detalle": {}, "notas": [],
    }


# ── Rama A: mensajero interno ────────────────────────────────────────────────

def fetch_liquidaciones_mensuales(cur, pid):
    cur.execute(
        """
        SELECT periodo_anio, periodo_mes,
               COUNT(*) AS num_liquidaciones,
               SUM(cantidad_entregas) AS cantidad_entregas,
               SUM(COALESCE(valor_ajustado, total_a_pagar)) AS total_pagado,
               array_agg(numero_liquidacion ORDER BY numero_liquidacion) AS numeros_liquidacion,
               array_agg(DISTINCT estado) AS estados
        FROM liquidaciones
        WHERE personal_id = %s
        GROUP BY periodo_anio, periodo_mes
        ORDER BY periodo_anio, periodo_mes
        """,
        (pid,),
    )
    return {(r["periodo_anio"], r["periodo_mes"]): r for r in cur.fetchall()}


def fetch_pendientes_seriales(cur, pid):
    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM f_esc)::int AS anio, EXTRACT(MONTH FROM f_esc)::int AS mes,
               COUNT(*) FILTER (WHERE estado = 'pendiente') AS cant_pendiente,
               COALESCE(SUM(precio_mensajero) FILTER (WHERE estado = 'pendiente'), 0) AS monto_pendiente,
               COUNT(*) FILTER (WHERE estado = 'en_revision') AS cant_en_revision,
               COALESCE(SUM(precio_mensajero) FILTER (WHERE estado = 'en_revision'), 0) AS monto_en_revision
        FROM seriales_gestion
        WHERE mensajero_id = %s AND liquidacion_id IS NULL AND estado != 'anulado'
        GROUP BY 1, 2
        """,
        (pid,),
    )
    return {(r["anio"], r["mes"]): r for r in cur.fetchall()}


def fetch_pendientes_horas(cur, pid):
    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM fecha)::int AS anio, EXTRACT(MONTH FROM fecha)::int AS mes,
               COALESCE(SUM(total) FILTER (WHERE aprobado), 0) AS monto_aprobado,
               COALESCE(SUM(total) FILTER (WHERE NOT aprobado), 0) AS monto_sin_aprobar
        FROM registro_horas
        WHERE personal_id = %s AND liquidado = FALSE
        GROUP BY 1, 2
        """,
        (pid,),
    )
    return {(r["anio"], r["mes"]): r for r in cur.fetchall()}


def fetch_pendientes_labores(cur, pid):
    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM fecha)::int AS anio, EXTRACT(MONTH FROM fecha)::int AS mes,
               COALESCE(SUM(total) FILTER (WHERE aprobado), 0) AS monto_aprobado,
               COALESCE(SUM(total) FILTER (WHERE NOT aprobado), 0) AS monto_sin_aprobar
        FROM registro_labores
        WHERE personal_id = %s AND liquidado = FALSE
        GROUP BY 1, 2
        """,
        (pid,),
    )
    return {(r["anio"], r["mes"]): r for r in cur.fetchall()}


def fetch_pendientes_subsidio(cur, pid):
    cur.execute(
        """
        SELECT EXTRACT(YEAR FROM fecha)::int AS anio, EXTRACT(MONTH FROM fecha)::int AS mes,
               COALESCE(SUM(total), 0) AS monto
        FROM subsidio_transporte
        WHERE personal_id = %s AND liquidado = FALSE
        GROUP BY 1, 2
        """,
        (pid,),
    )
    return {(r["anio"], r["mes"]): r for r in cur.fetchall()}


def calcular_rama_a(cur, pid):
    advertencias = []
    formal = fetch_liquidaciones_mensuales(cur, pid)
    pend_seriales = fetch_pendientes_seriales(cur, pid)
    pend_horas = fetch_pendientes_horas(cur, pid)
    pend_labores = fetch_pendientes_labores(cur, pid)
    pend_subsidio = fetch_pendientes_subsidio(cur, pid)

    claves = set(formal) | set(pend_seriales) | set(pend_horas) | set(pend_labores) | set(pend_subsidio)
    mapa = {}
    total_en_revision = Decimal("0")
    total_sin_aprobar = Decimal("0")

    for key in claves:
        f = formal.get(key)
        ps = pend_seriales.get(key, {})
        ph = pend_horas.get(key, {})
        pl = pend_labores.get(key, {})
        psub = pend_subsidio.get(key, {})

        monto_formal = D(f["total_pagado"]) if f else Decimal("0")
        monto_pend = (
            D(ps.get("monto_pendiente")) + D(ph.get("monto_aprobado"))
            + D(pl.get("monto_aprobado")) + D(psub.get("monto"))
        )
        monto_en_revision = D(ps.get("monto_en_revision"))
        monto_sin_aprobar = D(ph.get("monto_sin_aprobar")) + D(pl.get("monto_sin_aprobar"))
        total_en_revision += monto_en_revision
        total_sin_aprobar += monto_sin_aprobar

        notas = []
        if monto_en_revision > 0:
            notas.append(
                f"{ps.get('cant_en_revision', 0)} ítem(s) en revisión por ${monto_en_revision} "
                "excluidos del total de este mes"
            )
        if monto_sin_aprobar > 0:
            notas.append(f"${monto_sin_aprobar} en horas/labores sin aprobar excluidos del total de este mes")

        if monto_formal > 0 and monto_pend > 0:
            fuente = "parcial: liquidado + pendiente adicional"
        elif monto_formal > 0:
            fuente = "liquidado formalmente"
        elif monto_pend > 0:
            fuente = "estimado, no liquidado formalmente"
        else:
            fuente = "sin actividad"

        mapa[key] = {
            "anio": key[0], "mes": key[1], "fuente": fuente,
            "total_mes": (monto_formal + monto_pend).quantize(TWO_PLACES),
            "monto_liquidado": monto_formal.quantize(TWO_PLACES),
            "monto_pendiente_adicional": monto_pend.quantize(TWO_PLACES),
            "cantidad": int(f["cantidad_entregas"]) if f and f["cantidad_entregas"] else int(ps.get("cant_pendiente") or 0),
            "ajuste_aplicado": False,
            "detalle": {
                "numeros_liquidacion": list(f["numeros_liquidacion"]) if f else [],
                "estados_liquidacion": list(f["estados"]) if f else [],
            },
            "notas": notas,
        }

    # Chequeo de integridad: todo serial no anulado debe estar liquidado o pendiente, no perdido.
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE estado != 'anulado') AS total_no_anulado,
          COUNT(*) FILTER (WHERE estado != 'anulado' AND liquidacion_id IS NOT NULL) AS con_liquidacion,
          COUNT(*) FILTER (WHERE estado != 'anulado' AND liquidacion_id IS NULL) AS sin_liquidacion
        FROM seriales_gestion WHERE mensajero_id = %s
        """,
        (pid,),
    )
    chk = cur.fetchone()
    cur.execute("SELECT COALESCE(SUM(cantidad_entregas), 0) AS total FROM liquidaciones WHERE personal_id = %s", (pid,))
    suma_liq = cur.fetchone()["total"]
    if int(chk["con_liquidacion"] or 0) != int(suma_liq or 0):
        advertencias.append(
            f"Descuadre de integridad: seriales con liquidacion_id asignado = {chk['con_liquidacion']}, "
            f"pero suma de cantidad_entregas en liquidaciones = {suma_liq}. Revisar antes de certificar estas cifras."
        )
    if total_en_revision > 0:
        advertencias.append(f"${total_en_revision} en ítems 'en_revision' excluidos de todos los totales (histórico completo).")
    if total_sin_aprobar > 0:
        advertencias.append(f"${total_sin_aprobar} en horas/labores sin aprobar excluidos de todos los totales (histórico completo).")

    return mapa, advertencias


# ── Rama B: courier externo / transportadora ─────────────────────────────────

def fetch_todas_planillas(cur, cod):
    cur.execute(
        """
        SELECT DISTINCT sg.planilla
        FROM seriales_gestion sg
        JOIN personal p ON p.codigo = sg.cod_men
        WHERE sg.cod_men = %s
          AND p.tipo_personal IN ('courier_externo', 'transportadora')
          AND sg.estado != 'anulado'
        """,
        (cod,),
    )
    return [r["planilla"] for r in cur.fetchall()]


def fetch_planillas_incluidas(cur, cod):
    cur.execute(
        """
        SELECT pp.planilla, pp.fecha_escaner, pp.valor_total AS planilla_valor_total,
               pf.id AS prefactura_id, pf.valor_total AS prefactura_valor_total,
               pf.valor_ajustado AS prefactura_valor_ajustado, pf.estado AS prefactura_estado,
               cxp.numero_factura, cxp.estado AS cxp_estado, cxp.fecha_pago
        FROM prefactura_planillas pp
        JOIN prefacturas_courier pf ON pf.id = pp.prefactura_id
        LEFT JOIN facturas_courier_cxp cxp ON cxp.prefactura_id = pf.id
        WHERE pf.cod_mensajero = %s
        ORDER BY pp.fecha_escaner
        """,
        (cod,),
    )
    return cur.fetchall()


def fetch_planillas_sin_prefactura(cur, cod, faltantes):
    if not faltantes:
        return []
    cur.execute(
        """
        SELECT sg.planilla, MIN(sg.f_esc) AS fecha_escaner,
               COALESCE(SUM(sg.precio_mensajero), 0) AS valor_total
        FROM seriales_gestion sg
        JOIN personal p ON p.codigo = sg.cod_men
        WHERE sg.cod_men = %s
          AND p.tipo_personal IN ('courier_externo', 'transportadora')
          AND sg.estado != 'anulado'
          AND sg.planilla = ANY(%s)
        GROUP BY sg.planilla
        """,
        (cod, faltantes),
    )
    return cur.fetchall()


def calcular_rama_b(cur, cod):
    advertencias = []
    todas = fetch_todas_planillas(cur, cod)
    incluidas_rows = fetch_planillas_incluidas(cur, cod)
    planillas_incluidas = {r["planilla"] for r in incluidas_rows}
    faltantes = [p for p in todas if p not in planillas_incluidas]
    sin_prefactura_rows = fetch_planillas_sin_prefactura(cur, cod, faltantes)

    if len(todas) != len(planillas_incluidas) + len(sin_prefactura_rows):
        advertencias.append(
            f"Descuadre de integridad: {len(todas)} planillas descubiertas, "
            f"{len(planillas_incluidas)} facturadas + {len(sin_prefactura_rows)} sin facturar no cuadran."
        )

    mapa: dict = {}
    sin_fecha = 0

    def _bucket(key):
        if key not in mapa:
            mapa[key] = {
                "anio": key[0], "mes": key[1], "fuente": "sin actividad",
                "total_mes": Decimal("0.00"), "monto_liquidado": Decimal("0.00"),
                "monto_pendiente_adicional": Decimal("0.00"), "cantidad": 0,
                "ajuste_aplicado": False, "detalle": {"planillas": []}, "notas": [],
            }
        return mapa[key]

    por_prefactura: dict = {}
    for r in incluidas_rows:
        por_prefactura.setdefault(r["prefactura_id"], []).append(r)

    for pid_pf, filas in por_prefactura.items():
        pf_valor_total = D(filas[0]["prefactura_valor_total"])
        pf_valor_ajustado = filas[0]["prefactura_valor_ajustado"]
        delta = (D(pf_valor_ajustado) - pf_valor_total) if pf_valor_ajustado is not None else Decimal("0")
        numero_factura = filas[0]["numero_factura"]
        cxp_estado = filas[0]["cxp_estado"]

        for r in filas:
            fecha = r["fecha_escaner"]
            if fecha is None:
                sin_fecha += 1
                continue
            key = (fecha.year, fecha.month)
            valor_planilla = D(r["planilla_valor_total"])
            if pf_valor_total > 0:
                share = valor_planilla / pf_valor_total
            else:
                share = Decimal("1") / len(filas)
            asignado = delta * share
            monto = (valor_planilla + asignado).quantize(TWO_PLACES)

            d = _bucket(key)
            d["monto_liquidado"] += monto
            d["cantidad"] += 1
            d["detalle"]["planillas"].append({
                "planilla": r["planilla"], "prefactura_id": pid_pf,
                "numero_factura": numero_factura, "cxp_estado": cxp_estado,
            })
            if asignado != 0:
                d["ajuste_aplicado"] = True
                d["notas"].append(f"Ajuste de prefactura #{pid_pf} prorrateado a planilla {r['planilla']}: ${asignado.quantize(TWO_PLACES)}")

    for r in sin_prefactura_rows:
        fecha = r["fecha_escaner"]
        if fecha is None:
            sin_fecha += 1
            continue
        key = (fecha.year, fecha.month)
        monto = D(r["valor_total"]).quantize(TWO_PLACES)
        d = _bucket(key)
        d["monto_pendiente_adicional"] += monto
        d["cantidad"] += 1
        d["detalle"]["planillas"].append({"planilla": r["planilla"], "prefactura_id": None})

    for d in mapa.values():
        d["total_mes"] = (d["monto_liquidado"] + d["monto_pendiente_adicional"]).quantize(TWO_PLACES)
        if d["monto_liquidado"] > 0 and d["monto_pendiente_adicional"] > 0:
            d["fuente"] = "parcial: facturado + pendiente sin facturar"
        elif d["monto_liquidado"] > 0:
            d["fuente"] = "liquidado (prefactura) + ajuste prorrateado" if d["ajuste_aplicado"] else "liquidado (prefactura)"
        elif d["monto_pendiente_adicional"] > 0:
            d["fuente"] = "estimado, no facturado"

    if sin_fecha:
        advertencias.append(f"{sin_fecha} planilla(s) sin fecha_escaner no se pudieron ubicar en ningún mes y quedaron fuera del cálculo.")

    return mapa, advertencias


# ── Serie mensual continua ────────────────────────────────────────────────────

def construir_serie_continua(mapa_meses, hasta, incluir_vacios):
    if not mapa_meses:
        return []
    claves = sorted(mapa_meses.keys())
    inicio = claves[0]
    fin = (hasta.year, hasta.month)
    if fin < inicio:
        fin = claves[-1]

    serie = []
    anio, mes = inicio
    while (anio, mes) <= fin:
        dato = mapa_meses.get((anio, mes))
        if dato is not None:
            serie.append(dato)
        elif incluir_vacios:
            serie.append(_mes_vacio(anio, mes))
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    return serie


def totales_por_anio(serie):
    totales = {}
    for m in serie:
        totales.setdefault(m["anio"], Decimal("0.00"))
        totales[m["anio"]] += m["total_mes"]
    return {str(a): str(v.quantize(TWO_PLACES)) for a, v in sorted(totales.items())}


# ── Salida ────────────────────────────────────────────────────────────────────

def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(f"No serializable: {o!r}")


def write_json(path, resultado):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(resultado, fh, ensure_ascii=False, indent=2, default=_json_default)


def write_csv(path, serie):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, quoting=csv.QUOTE_ALL)
        w.writerow(CSV_COLUMNS)
        for m in serie:
            w.writerow([
                m["anio"], m["mes"], m["fuente"], m["total_mes"], m["monto_liquidado"],
                m["monto_pendiente_adicional"], m["cantidad"], m["ajuste_aplicado"],
                "; ".join(m["notas"]), json.dumps(m["detalle"], ensure_ascii=False, default=_json_default),
            ])


def imprimir_resumen(resultado):
    men = resultado["mensajero"]
    print(f"\nMensajero {men['codigo']} - {men['nombre_completo']} ({men['tipo_personal']})")
    print(f"Ancla de período: {resultado['metodologia']['ancla_periodo']}")
    print(f"Rango cubierto: {resultado['rango_cubierto']['desde']} a {resultado['rango_cubierto']['hasta']}\n")

    no_confirmados = [m for m in resultado["meses"] if "estimado" in m["fuente"] or "parcial" in m["fuente"]]
    for anio, total in resultado["totales_por_anio"].items():
        print(f"  {anio}: ${total}")
    print(f"\n  GRAN TOTAL: ${resultado['gran_total']}\n")

    if no_confirmados:
        print(f"  {len(no_confirmados)} mes(es) con montos no liquidados/facturados formalmente en su totalidad:")
        for m in no_confirmados:
            print(f"    {m['anio']}-{m['mes']:02d}: {m['fuente']} (${m['total_mes']})")
        print()

    if resultado["advertencias_integridad"]:
        print("  ADVERTENCIAS DE INTEGRIDAD:")
        for a in resultado["advertencias_integridad"]:
            print(f"    - {a}")
        print()
    else:
        print("  Chequeo de integridad: sin descuadres detectados.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cod", default="0260", help="Código de mensajero/courier (default: 0260)")
    parser.add_argument("--output-dir", default=None, help="Directorio de salida (default: Downloads)")
    parser.add_argument("--formato", choices=["csv", "json", "both"], default="both")
    parser.add_argument("--hasta", default=None, help="Fecha de corte YYYY-MM-DD (default: hoy)")
    parser.add_argument(
        "--excluir-meses-sin-actividad", dest="incluir_vacios", action="store_false", default=True,
        help="No incluir meses en 0 dentro del rango histórico",
    )
    args = parser.parse_args()

    if not PG_PASS:
        sys.exit("Falta credencial: exporta PG_PASSWORD antes de correr este script.")

    hasta = date.fromisoformat(args.hasta) if args.hasta else date.today()
    output_dir = args.output_dir or DOWNLOADS_DIR

    conn = connect_pg()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        personal = fetch_personal(cur, args.cod)
        if personal is None:
            sys.exit(f"No existe personal con codigo={args.cod!r}.")
        print(f"Mensajero: {args.cod} - {personal['nombre_completo']} ({personal['tipo_personal']})")

        if personal["tipo_personal"] in ("courier_externo", "transportadora"):
            mapa, advertencias = calcular_rama_b(cur, args.cod)
        else:
            mapa, advertencias = calcular_rama_a(cur, personal["id"])

        if not mapa:
            sys.exit(f"No se encontró actividad histórica para el código {args.cod!r}.")

        serie = construir_serie_continua(mapa, hasta, args.incluir_vacios)
        gran_total = sum((m["total_mes"] for m in serie), Decimal("0.00"))

        resultado = {
            "mensajero": {
                "codigo": personal["codigo"],
                "nombre_completo": personal["nombre_completo"],
                "identificacion": personal["identificacion"],
                "tipo_personal": personal["tipo_personal"],
                "fecha_ingreso": personal["fecha_ingreso"],
            },
            "metodologia": {
                "ancla_periodo": "f_esc (fecha de escaneo/entrega)",
                "fecha_generacion": date.today(),
                "notas": [
                    "Ítems 'en_revision' y horas/labores sin aprobar quedan excluidos de todos los totales.",
                    "Meses marcados como 'estimado' o 'parcial' no corresponden a un pago formalmente liquidado/facturado en su totalidad.",
                    "Ajustes manuales sobre prefacturas que cubren varios meses se prorratean proporcionalmente entre esos meses (ver 'ajuste_aplicado').",
                ],
            },
            "meses": serie,
            "totales_por_anio": totales_por_anio(serie),
            "gran_total": str(gran_total),
            "rango_cubierto": {
                "desde": f"{serie[0]['anio']}-{serie[0]['mes']:02d}",
                "hasta": f"{serie[-1]['anio']}-{serie[-1]['mes']:02d}",
            },
            "advertencias_integridad": advertencias,
        }

        imprimir_resumen(resultado)

        fecha_str = date.today().isoformat()
        if args.formato in ("json", "both"):
            path = os.path.join(output_dir, f"certificacion_ingresos_{args.cod}_{fecha_str}.json")
            write_json(path, resultado)
            print(f"JSON generado en: {path}")
        if args.formato in ("csv", "both"):
            path = os.path.join(output_dir, f"certificacion_ingresos_{args.cod}_{fecha_str}.csv")
            write_csv(path, serie)
            print(f"CSV generado en: {path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
