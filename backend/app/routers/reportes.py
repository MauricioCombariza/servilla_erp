from calendar import monthrange
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import BigInteger, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.schemas.reportes import (
    FacturacionClienteRow,
    OrdenReporteRow,
    ResumenClienteRow,
    ResumenMensajeroRow,
    TendenciaMesRow,
)

router = APIRouter(prefix="/api/reportes", tags=["reportes"])
_auth = Depends(require_role("administrador", "logistica"))


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
        mar = ing - cos
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


# ── 2. Gestiones por mensajero ────────────────────────────────────────────────

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
                COALESCE(m.cod_men, p.codigo)              AS cod_men,
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
