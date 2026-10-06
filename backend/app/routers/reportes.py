from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.reportes import (
    FacturacionClienteRow,
    GastoCategoriaMes,
    OrdenReporteRow,
    PLCompletoResponse,
    PLCompletoRow,
    PLMensualRow,
    ResumenClienteRow,
    ResumenMensajeroRow,
    TendenciaMesRow,
)
from app.services.excel_utils import XLSX_MEDIA_TYPE, construir_excel_multi

router = APIRouter(prefix="/api/reportes", tags=["reportes"])
_auth = Depends(require_page("reportes"))

_MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _rango_anio_mes(anio: int, mes: int | None) -> tuple[date, date]:
    if mes:
        _, ultimo = monthrange(anio, mes)
        return date(anio, mes, 1), date(anio, mes, ultimo)
    return date(anio, 1, 1), date(anio, 12, 31)


# ── 1. Resumen operacional por cliente ────────────────────────────────────────

@router.get("/operacional", response_model=list[ResumenClienteRow])
async def get_operacional(
    anio: int = Query(default=2026),
    mes: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    desde, hasta = _rango_anio_mes(anio, mes)
    rows = (await db.execute(
        text("""
            WITH flete_cliente AS (
                SELECT cliente_id,
                       COALESCE(SUM(costo_flete_total),     0)
                     + COALESCE(SUM(costo_transporte_total), 0) AS costo_flete
                FROM ordenes
                WHERE fecha_recepcion BETWEEN :desde AND :hasta
                GROUP BY cliente_id
            )
            SELECT
                COALESCE(c.nombre_empresa, 'Sin cliente') AS cliente,
                c.id                                       AS cliente_id,
                COUNT(*)::int                              AS total_seriales,
                COALESCE(SUM(sg.precio_cliente),   0)     AS ingreso_cliente,
                COALESCE(SUM(sg.precio_mensajero), 0)     AS costo_mensajero,
                COALESCE(fc.costo_flete,           0)     AS costo_flete
            FROM seriales_gestion sg
            LEFT JOIN clientes c ON sg.cliente_id = c.id
            LEFT JOIN flete_cliente fc ON fc.cliente_id = c.id
            WHERE sg.f_emi BETWEEN :desde AND :hasta
            GROUP BY c.id, c.nombre_empresa, fc.costo_flete
            ORDER BY ingreso_cliente DESC
        """),
        {"desde": desde, "hasta": hasta},
    )).mappings().all()

    result = []
    for r in rows:
        ing = float(r["ingreso_cliente"])
        cos = float(r["costo_mensajero"])
        fle = float(r["costo_flete"])
        mar = ing - cos - fle
        result.append(ResumenClienteRow(
            cliente=r["cliente"],
            cliente_id=r["cliente_id"],
            total_seriales=r["total_seriales"],
            ingreso_cliente=round(ing, 2),
            costo_mensajero=round(cos, 2),
            costo_flete=round(fle, 2),
            margen=round(mar, 2),
            margen_pct=round(mar / ing * 100, 1) if ing else None,
        ))
    return result


# ── 2. P&L mensual (margen clientes − gasto nómina) ──────────────────────────

@router.get("/pl-mensual", response_model=list[PLMensualRow])
async def get_pl_mensual(
    anio: int = Query(default=2026),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    margen_rows = (await db.execute(
        text("""
            SELECT
                EXTRACT(MONTH FROM f_emi)::int AS mes,
                COALESCE(SUM(precio_cliente - precio_mensajero), 0) AS margen_clientes
            FROM seriales_gestion
            WHERE f_emi BETWEEN :desde AND :hasta
            GROUP BY EXTRACT(MONTH FROM f_emi)
        """),
        {"desde": date(anio, 1, 1), "hasta": date(anio, 12, 31)},
    )).mappings().all()

    nomina_rows = (await db.execute(
        text("""
            SELECT
                periodo_mes AS mes,
                COALESCE(SUM(
                    COALESCE(salario_base, 0) + COALESCE(auxilio_transporte, 0) +
                    COALESCE(auxilio_no_salarial, 0) + COALESCE(arl, 0) +
                    COALESCE(eps, 0) + COALESCE(afp, 0) +
                    COALESCE(caja_compensacion, 0) + COALESCE(prima, 0) +
                    COALESCE(cesantias, 0) + COALESCE(int_cesantias, 0) +
                    COALESCE(vacaciones, 0)
                ), 0) AS gasto_nomina
            FROM nomina_provisiones
            WHERE periodo_anio = :anio
            GROUP BY periodo_mes
        """),
        {"anio": anio},
    )).mappings().all()

    margen_by_mes = {int(r["mes"]): float(r["margen_clientes"]) for r in margen_rows}
    nomina_by_mes = {int(r["mes"]): float(r["gasto_nomina"]) for r in nomina_rows}

    return [
        PLMensualRow(
            mes=m,
            margen_clientes=round(margen_by_mes.get(m, 0.0), 2),
            gasto_nomina=round(nomina_by_mes.get(m, 0.0), 2),
            utilidad_neta=round(margen_by_mes.get(m, 0.0) - nomina_by_mes.get(m, 0.0), 2),
        )
        for m in range(1, 13)
    ]


# ── 2b. P&L completo (estado de resultados con todos los gastos) ─────────────
#
# Fuentes y criterio de mes (causado, no caja):
#   ingresos            seriales_gestion.precio_cliente        por f_emi
#   costo_mensajeros    seriales_gestion.precio_mensajero      por f_esc (como liquidaciones)
#   alistamiento        registro_horas.total + registro_labores.total   por fecha
#   subsidio            subsidio_transporte.total              por fecha
#   ajustes_liquidacion liquidaciones: bonificaciones − descuentos + (valor_ajustado − total_a_pagar)
#                       por periodo
#   fletes              facturas_transporte.monto_total        por fecha_factura
#   nomina              nomina_provisiones (11 componentes)    por periodo
#   gastos_admin        gastos_administrativos.monto           por fecha
#   gastos_fijos        pago registrado del mes; si no hay, monto del fijo activo
#                       (desde el mes en que se creó y hasta el mes actual)
#   facturas_proveedores facturas_recibidas tipo materiales/otros, no anuladas, por fecha_recepcion
#
# Para no contar dos veces:
#   - ajustes_liquidacion (tabla) ya entra en liquidaciones.bonificaciones/descuentos.
#   - prefacturas/facturas_courier_cxp y facturas_recibidas tipo courier/transportadora
#     ya están en precio_mensajero / fletes.
#   - horas/labores/subsidio se toman de sus registros, no de liquidaciones.total_*.

_SQL_POR_MES = {
    "ingresos": """
        SELECT EXTRACT(MONTH FROM f_emi)::int AS mes, SUM(precio_cliente) AS v
        FROM seriales_gestion
        WHERE f_emi BETWEEN :desde AND :hasta AND estado != 'anulado'
        GROUP BY 1
    """,
    "costo_mensajeros": """
        SELECT EXTRACT(MONTH FROM f_esc)::int AS mes, SUM(precio_mensajero) AS v
        FROM seriales_gestion
        WHERE f_esc BETWEEN :desde AND :hasta AND estado != 'anulado'
        GROUP BY 1
    """,
    "alistamiento": """
        SELECT EXTRACT(MONTH FROM fecha)::int AS mes, SUM(total) AS v
        FROM (
            SELECT fecha, total FROM registro_horas   WHERE fecha BETWEEN :desde AND :hasta
            UNION ALL
            SELECT fecha, total FROM registro_labores WHERE fecha BETWEEN :desde AND :hasta
        ) sub
        GROUP BY 1
    """,
    "subsidio": """
        SELECT EXTRACT(MONTH FROM fecha)::int AS mes, SUM(total) AS v
        FROM subsidio_transporte
        WHERE fecha BETWEEN :desde AND :hasta
        GROUP BY 1
    """,
    "ajustes_liquidacion": """
        SELECT periodo_mes AS mes,
               SUM(COALESCE(bonificaciones, 0) - COALESCE(descuentos, 0)
                   + COALESCE(valor_ajustado - total_a_pagar, 0)) AS v
        FROM liquidaciones
        WHERE periodo_anio = :anio
        GROUP BY 1
    """,
    "fletes": """
        SELECT EXTRACT(MONTH FROM fecha_factura)::int AS mes, SUM(monto_total) AS v
        FROM facturas_transporte
        WHERE fecha_factura BETWEEN :desde AND :hasta AND estado != 'anulada'
        GROUP BY 1
    """,
    "nomina": """
        SELECT periodo_mes AS mes,
               SUM(
                   COALESCE(salario_base, 0) + COALESCE(auxilio_transporte, 0) +
                   COALESCE(auxilio_no_salarial, 0) + COALESCE(arl, 0) +
                   COALESCE(eps, 0) + COALESCE(afp, 0) +
                   COALESCE(caja_compensacion, 0) + COALESCE(prima, 0) +
                   COALESCE(cesantias, 0) + COALESCE(int_cesantias, 0) +
                   COALESCE(vacaciones, 0)
               ) AS v
        FROM nomina_provisiones
        WHERE periodo_anio = :anio
        GROUP BY 1
    """,
    "gastos_admin": """
        SELECT EXTRACT(MONTH FROM fecha)::int AS mes, SUM(monto) AS v
        FROM gastos_administrativos
        WHERE fecha BETWEEN :desde AND :hasta
        GROUP BY 1
    """,
    "facturas_proveedores": """
        SELECT EXTRACT(MONTH FROM fecha_recepcion)::int AS mes, SUM(total) AS v
        FROM facturas_recibidas
        WHERE fecha_recepcion BETWEEN :desde AND :hasta
          AND tipo IN ('materiales', 'otros') AND estado != 'anulada'
        GROUP BY 1
    """,
}

# Una fila por (gasto fijo, mes): pago registrado si existe; si no, el monto del
# fijo activo para los meses entre su creación y el mes actual (causado).
_SQL_GASTOS_FIJOS = """
    WITH meses AS (SELECT generate_series(1, 12) AS mes),
    causado AS (
        SELECT gf.id, m.mes, gf.monto
        FROM gastos_fijos_mensuales gf
        CROSS JOIN meses m
        WHERE gf.activo
          AND make_date(:anio, m.mes, 1) >= date_trunc('month', COALESCE(gf.created_at, make_date(:anio, 1, 1)))::date
          AND make_date(:anio, m.mes, 1) <= date_trunc('month', CURRENT_DATE)::date
    ),
    pagos AS (
        SELECT gasto_fijo_id AS id, mes, SUM(monto_pagado) AS monto
        FROM pagos_gastos_fijos
        WHERE anio = :anio
        GROUP BY 1, 2
    )
    SELECT COALESCE(p.mes, c.mes) AS mes,
           SUM(COALESCE(p.monto, c.monto)) AS v,
           COUNT(*) FILTER (WHERE p.id IS NULL)::int AS sin_pago
    FROM causado c
    FULL OUTER JOIN pagos p ON p.id = c.id AND p.mes = c.mes
    GROUP BY 1
"""

_CAMPOS_COSTO_OPERATIVO = ("costo_mensajeros", "alistamiento", "subsidio", "ajustes_liquidacion", "fletes")
_CAMPOS_GASTO_FIJO = ("nomina", "gastos_admin", "gastos_fijos", "facturas_proveedores")


def _fila_pl(mes: int, v: dict[str, float], advertencias: list[str]) -> PLCompletoRow:
    costos_op = sum(v[c] for c in _CAMPOS_COSTO_OPERATIVO)
    margen_op = v["ingresos"] - costos_op
    total_gastos = costos_op + sum(v[c] for c in _CAMPOS_GASTO_FIJO)
    utilidad = v["ingresos"] - total_gastos
    return PLCompletoRow(
        mes=mes,
        **{k: round(x, 2) for k, x in v.items()},
        margen_operacional=round(margen_op, 2),
        total_gastos=round(total_gastos, 2),
        utilidad_neta=round(utilidad, 2),
        margen_pct=round(utilidad / v["ingresos"] * 100, 2) if v["ingresos"] else None,
        advertencias=advertencias,
    )


async def calcular_pl_completo(db: AsyncSession, anio: int) -> PLCompletoResponse:
    params = {"anio": anio, "desde": date(anio, 1, 1), "hasta": date(anio, 12, 31)}

    por_campo: dict[str, dict[int, float]] = {}
    for campo, sql in _SQL_POR_MES.items():
        rows = (await db.execute(text(sql), params)).mappings().all()
        por_campo[campo] = {int(r["mes"]): float(r["v"] or 0) for r in rows}

    fijos_rows = (await db.execute(text(_SQL_GASTOS_FIJOS), params)).mappings().all()
    por_campo["gastos_fijos"] = {int(r["mes"]): float(r["v"] or 0) for r in fijos_rows}
    fijos_sin_pago = {int(r["mes"]): r["sin_pago"] for r in fijos_rows}

    categorias = (await db.execute(
        text("""
            SELECT categoria, EXTRACT(MONTH FROM fecha)::int AS mes, SUM(monto) AS monto
            FROM gastos_administrativos
            WHERE fecha BETWEEN :desde AND :hasta
            GROUP BY 1, 2
            ORDER BY 1, 2
        """),
        params,
    )).mappings().all()

    campos = ["ingresos", *_CAMPOS_COSTO_OPERATIVO, *_CAMPOS_GASTO_FIJO]
    meses: list[PLCompletoRow] = []
    for m in range(1, 13):
        v = {c: por_campo[c].get(m, 0.0) for c in campos}
        advertencias = []
        hay_actividad = v["ingresos"] or v["costo_mensajeros"]
        if hay_actividad and not v["nomina"]:
            advertencias.append("Sin provisiones de nómina")
        if fijos_sin_pago.get(m):
            advertencias.append(f"{fijos_sin_pago[m]} gasto(s) fijo(s) sin pago registrado (se usa el monto)")
        if hay_actividad and not v["gastos_admin"]:
            advertencias.append("Sin gastos administrativos registrados")
        meses.append(_fila_pl(m, v, advertencias))

    total = _fila_pl(0, {c: sum(getattr(f, c) for f in meses) for c in campos}, [])

    return PLCompletoResponse(
        anio=anio,
        meses=meses,
        total=total,
        gastos_admin_por_categoria=[
            GastoCategoriaMes(categoria=r["categoria"], mes=int(r["mes"]), monto=round(float(r["monto"]), 2))
            for r in categorias
        ],
    )


@router.get("/pl-completo", response_model=PLCompletoResponse)
async def get_pl_completo(
    anio: int = Query(default_factory=lambda: date.today().year),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await calcular_pl_completo(db, anio)


_LINEAS_PL = [
    ("Ingresos clientes", "ingresos"),
    ("(−) Pago mensajeros", "costo_mensajeros"),
    ("(−) Alistamiento (horas + labores)", "alistamiento"),
    ("(−) Subsidio transporte", "subsidio"),
    ("(−) Ajustes liquidaciones", "ajustes_liquidacion"),
    ("(−) Fletes / transporte", "fletes"),
    ("= Margen operacional", "margen_operacional"),
    ("(−) Nómina", "nomina"),
    ("(−) Gastos administrativos", "gastos_admin"),
    ("(−) Gastos fijos", "gastos_fijos"),
    ("(−) Facturas proveedores", "facturas_proveedores"),
    ("Total gastos", "total_gastos"),
    ("= Utilidad neta", "utilidad_neta"),
    ("Margen %", "margen_pct"),
]


@router.get("/pl-completo/excel")
async def get_pl_completo_excel(
    anio: int = Query(default_factory=lambda: date.today().year),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    pl = await calcular_pl_completo(db, anio)

    col_meses = [_MESES_CORTOS[m - 1] for m in range(1, 13)]
    columnas = ["Concepto", *col_meses, "Total"]
    filas = []
    for etiqueta, campo in _LINEAS_PL:
        fila = {"Concepto": etiqueta, "Total": getattr(pl.total, campo)}
        for nombre_mes, row in zip(col_meses, pl.meses):
            fila[nombre_mes] = getattr(row, campo)
        filas.append(fila)

    cat_cols = ["Categoría", *col_meses, "Total"]
    cat_filas: dict[str, dict] = {}
    for g in pl.gastos_admin_por_categoria:
        fila = cat_filas.setdefault(g.categoria, {"Categoría": g.categoria, "Total": 0.0})
        fila[col_meses[g.mes - 1]] = g.monto
        fila["Total"] += g.monto

    adv_filas = [
        {"Mes": col_meses[r.mes - 1], "Advertencia": a}
        for r in pl.meses for a in r.advertencias
    ]

    contenido = construir_excel_multi(
        [
            ("Estado de resultados", f"Estado de resultados {anio}", columnas, filas,
             [36, *[13] * 12, 15]),
            ("Gastos admin", f"Gastos administrativos por categoría {anio}", cat_cols,
             list(cat_filas.values()), [24, *[13] * 12, 15]),
            ("Advertencias", f"Datos incompletos {anio}", ["Mes", "Advertencia"], adv_filas,
             [10, 70]),
        ],
        formatos={c: "#,##0" for c in [*col_meses, "Total"]},
    )
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="estado_resultados_{anio}.xlsx"'},
    )


# ── 3. Gestiones por mensajero ────────────────────────────────────────────────

@router.get("/mensajeros", response_model=list[ResumenMensajeroRow])
async def get_mensajeros(
    fecha_desde: date = Query(default_factory=lambda: date.today().replace(day=1)),
    fecha_hasta: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    rows = (await db.execute(
        text("""
            WITH mensajeros_agg AS (
                SELECT
                    sg.mensajero_id,
                    MAX(sg.cod_men)                                    AS cod_men,
                    COUNT(DISTINCT NULLIF(sg.planilla,''))::int        AS planillas,
                    COUNT(*)::int                                      AS total_seriales,
                    COUNT(CASE WHEN sg.tipo_gestion = 'Entrega'   THEN 1 END)::int AS entregas,
                    COUNT(CASE WHEN sg.tipo_gestion = 'Devolucion' THEN 1 END)::int AS devoluciones,
                    COALESCE(SUM(sg.precio_mensajero), 0)             AS total_mensajero
                FROM seriales_gestion sg
                WHERE sg.f_emi BETWEEN :desde AND :hasta
                GROUP BY sg.mensajero_id
            ),
            alist_agg AS (
                SELECT personal_id,
                       COALESCE(SUM(total), 0) AS costo_alistamiento
                FROM (
                    SELECT personal_id, total FROM registro_horas
                    WHERE fecha BETWEEN :desde AND :hasta
                    UNION ALL
                    SELECT personal_id, total FROM registro_labores
                    WHERE fecha BETWEEN :desde AND :hasta
                ) sub
                GROUP BY personal_id
            )
            SELECT
                COALESCE(m.mensajero_id, a.personal_id)   AS personal_id,
                COALESCE(p.codigo, m.cod_men)              AS cod_men,
                p.nombre_completo                          AS nombre,
                COALESCE(m.planillas,       0)             AS planillas,
                COALESCE(m.total_seriales,  0)             AS total_seriales,
                COALESCE(m.entregas,        0)             AS entregas,
                COALESCE(m.devoluciones,    0)             AS devoluciones,
                COALESCE(m.total_mensajero, 0)             AS total_mensajero,
                COALESCE(a.costo_alistamiento, 0)          AS costo_alistamiento
            FROM mensajeros_agg m
            FULL OUTER JOIN alist_agg a ON a.personal_id = m.mensajero_id
            LEFT JOIN personal p ON p.id = COALESCE(m.mensajero_id, a.personal_id)
            ORDER BY (COALESCE(m.total_mensajero, 0) + COALESCE(a.costo_alistamiento, 0)) DESC
        """),
        {"desde": fecha_desde, "hasta": fecha_hasta},
    )).mappings().all()

    return [
        ResumenMensajeroRow(
            cod_men=r["cod_men"] or "???",
            nombre=r["nombre"],
            planillas=r["planillas"],
            total_seriales=r["total_seriales"],
            entregas=r["entregas"],
            devoluciones=r["devoluciones"],
            total_mensajero=round(float(r["total_mensajero"]), 2),
            costo_alistamiento=round(float(r["costo_alistamiento"]), 2),
        )
        for r in rows
    ]


# ── 3. Órdenes ────────────────────────────────────────────────────────────────

@router.get("/ordenes", response_model=list[OrdenReporteRow])
async def get_ordenes(
    fecha_desde: date = Query(default_factory=lambda: date.today().replace(day=1)),
    fecha_hasta: date = Query(default_factory=date.today),
    cliente_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    _ordenes_q = text("""
            SELECT
                o.numero_orden,
                c.nombre_empresa  AS cliente,
                o.fecha_recepcion,
                o.cantidad_total,
                o.cantidad_entregados,
                o.cantidad_devolucion,
                o.valor_total,
                o.estado
            FROM ordenes o
            JOIN clientes c ON o.cliente_id = c.id
            WHERE o.fecha_recepcion BETWEEN :desde AND :hasta
              AND (:cliente_id IS NULL OR o.cliente_id = :cliente_id)
            ORDER BY o.fecha_recepcion DESC
    """).bindparams(bindparam("cliente_id", type_=BigInteger))

    rows = (await db.execute(
        _ordenes_q,
        {"desde": fecha_desde, "hasta": fecha_hasta, "cliente_id": cliente_id},
    )).mappings().all()

    result = []
    for r in rows:
        total = int(r["cantidad_total"])
        ent = int(r["cantidad_entregados"])
        dev = int(r["cantidad_devolucion"])
        pct = round((ent + dev) / total * 100, 1) if total else 0.0
        result.append(OrdenReporteRow(
            numero_orden=r["numero_orden"],
            cliente=r["cliente"],
            fecha_recepcion=r["fecha_recepcion"],
            cantidad_total=total,
            cantidad_entregados=ent,
            cantidad_devolucion=dev,
            pendientes=max(0, total - ent - dev),
            valor_total=float(r["valor_total"]),
            estado=r["estado"],
            pct_gestionado=pct,
        ))
    return result


# ── 4. Facturación por cliente ────────────────────────────────────────────────

@router.get("/facturacion", response_model=list[FacturacionClienteRow])
async def get_facturacion(
    fecha_desde: date = Query(default_factory=lambda: date.today().replace(day=1)),
    fecha_hasta: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    rows = (await db.execute(
        text("""
            SELECT
                c.nombre_empresa                            AS cliente,
                COUNT(fe.id)::int                           AS num_facturas,
                COALESCE(SUM(fe.total), 0)                  AS total_facturado,
                COALESCE(SUM(fe.total - fe.saldo_pendiente), 0) AS total_cobrado,
                COALESCE(SUM(fe.saldo_pendiente), 0)        AS pendiente
            FROM facturas_emitidas fe
            JOIN clientes c ON fe.cliente_id = c.id
            WHERE fe.fecha_emision BETWEEN :desde AND :hasta
              AND fe.estado != 'anulada'
            GROUP BY c.id, c.nombre_empresa
            ORDER BY total_facturado DESC
        """),
        {"desde": fecha_desde, "hasta": fecha_hasta},
    )).mappings().all()

    return [
        FacturacionClienteRow(
            cliente=r["cliente"],
            num_facturas=r["num_facturas"],
            total_facturado=round(float(r["total_facturado"]), 2),
            total_cobrado=round(float(r["total_cobrado"]), 2),
            pendiente=round(float(r["pendiente"]), 2),
        )
        for r in rows
    ]


# ── 5. Tendencias mensuales ───────────────────────────────────────────────────

@router.get("/tendencias", response_model=list[TendenciaMesRow])
async def get_tendencias(
    meses: int = Query(default=12, ge=1, le=36),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    rows = (await db.execute(
        text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', sg.f_emi), 'YYYY-MM') AS mes,
                COUNT(*)::int                                       AS total_seriales,
                COUNT(CASE WHEN sg.tipo_gestion = 'Entrega'   THEN 1 END)::int AS entregas,
                COUNT(CASE WHEN sg.tipo_gestion = 'Devolucion' THEN 1 END)::int AS devoluciones,
                COALESCE(SUM(sg.precio_cliente),   0)              AS ingreso_estimado,
                COALESCE(SUM(sg.precio_mensajero), 0)              AS costo_mensajero
            FROM seriales_gestion sg
            WHERE sg.f_emi >= DATE_TRUNC('month', CURRENT_DATE) - (:meses - 1) * INTERVAL '1 month'
            GROUP BY DATE_TRUNC('month', sg.f_emi)
            ORDER BY mes
        """),
        {"meses": meses},
    )).mappings().all()

    return [
        TendenciaMesRow(
            mes=r["mes"],
            total_seriales=r["total_seriales"],
            entregas=r["entregas"],
            devoluciones=r["devoluciones"],
            ingreso_estimado=round(float(r["ingreso_estimado"]), 2),
            costo_mensajero=round(float(r["costo_mensajero"]), 2),
        )
        for r in rows
    ]
