from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.transporte import DetalleFacturaTransporte, FacturaTransporte
from app.schemas.transporte import (
    DetalleTransporteCreate,
    FacturaTransporteCreate,
    FacturaTransporteRead,
    FacturaTransporteUpdate,
    PagarTransporteRequest,
    PrefacturaCourier,
    ResumenClienteFlete,
    ResumenCourierReal,
)

router = APIRouter(prefix="/api/transporte", tags=["transporte"])
_auth = Depends(require_role("administrador", "contabilidad", "operaciones"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _det_dict(d: DetalleFacturaTransporte) -> dict:
    return {
        "id": d.id,
        "factura_id": d.factura_id,
        "orden_id": d.orden_id,
        "cantidad_sobres": d.cantidad_sobres,
        "costo_asignado": float(d.costo_asignado),
        "numero_orden": d.orden.numero_orden if d.orden else None,
        "cliente_nombre": d.orden.cliente.nombre_empresa if d.orden and d.orden.cliente else None,
    }


def _to_dict(ft: FacturaTransporte) -> dict:
    return {
        "id": ft.id,
        "numero_factura": ft.numero_factura,
        "fecha_factura": ft.fecha_factura,
        "courrier_id": ft.courrier_id,
        "courrier": {
            "id": ft.courrier.id,
            "codigo": ft.courrier.codigo,
            "nombre_completo": ft.courrier.nombre_completo,
        } if ft.courrier else {},
        "monto_total": float(ft.monto_total),
        "total_sobres": ft.total_sobres,
        "monto_pagado": float(ft.monto_pagado),
        "estado": ft.estado,
        "fecha_vencimiento": ft.fecha_vencimiento,
        "observaciones": ft.observaciones,
        "fecha_creacion": ft.fecha_creacion,
        "detalles": [_det_dict(d) for d in ft.detalles],
    }


async def _recalculate_detalles(
    ft: FacturaTransporte,
    new_total_sobres: int,
    new_monto: float,
    db: AsyncSession,
) -> None:
    """Recalculate detalle costs proportionally; update ordenes.costo_flete_total for deltas."""
    for det in ft.detalles:
        new_cost = new_monto * det.cantidad_sobres / new_total_sobres if new_total_sobres > 0 else 0.0
        delta = new_cost - float(det.costo_asignado)
        det.costo_asignado = new_cost
        if det.orden_id and abs(delta) > 0.001:
            await db.execute(
                text("UPDATE ordenes SET costo_flete_total = COALESCE(costo_flete_total, 0) + :d WHERE id = :id"),
                {"d": delta, "id": det.orden_id},
            )


# ── Prefacturas ───────────────────────────────────────────────────────────────

@router.get("/prefacturas", response_model=list[PrefacturaCourier])
async def prefacturas(
    mes: int,
    anio: int,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    sql = text("""
        SELECT
            sg.cod_men                              AS cod_mensajero,
            p.id                                    AS mensajero_id,
            p.nombre_completo,
            :mes                                    AS periodo_mes,
            :anio                                   AS periodo_anio,
            COUNT(DISTINCT sg.planilla)             AS total_planillas,
            COUNT(*) FILTER (WHERE sg.ambito = 'bogota')   AS total_local,
            COUNT(*) FILTER (WHERE sg.ambito = 'nacional') AS total_nacional,
            COUNT(*)                                AS total_seriales,
            ROUND(AVG(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'bogota'), 2)   AS precio_local_promedio,
            ROUND(AVG(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'nacional'), 2) AS precio_nacional_promedio,
            COALESCE(SUM(sg.precio_mensajero), 0)   AS monto_estimado
        FROM seriales_gestion sg
        LEFT JOIN personal p ON p.codigo = sg.cod_men
        WHERE EXTRACT(MONTH FROM sg.f_esc) = :mes
          AND EXTRACT(YEAR  FROM sg.f_esc) = :anio
          AND p.tipo_personal IN ('courier_externo', 'transportadora')
          AND sg.estado != 'anulado'
        GROUP BY sg.cod_men, p.id, p.nombre_completo
        ORDER BY monto_estimado DESC
    """)
    rows = (await db.execute(sql, {"mes": mes, "anio": anio})).mappings().all()
    return [PrefacturaCourier(**dict(r)) for r in rows]


# ── Resumen real por courier ──────────────────────────────────────────────────

@router.get("/resumen-real")
async def resumen_real(
    anio: int = Query(default=2026),
    mes: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    params: dict = {"anio": anio}
    mes_filter = "AND EXTRACT(MONTH FROM ft.fecha_factura) = :mes" if mes else ""
    if mes:
        params["mes"] = mes

    couriers_sql = text(f"""
        SELECT
            p.nombre_completo                         AS courrier,
            COUNT(DISTINCT ft.id)                     AS total_facturas,
            COALESCE(SUM(ft.monto_total), 0)          AS monto_total,
            COALESCE(SUM(ft.monto_pagado), 0)         AS monto_pagado,
            COALESCE(SUM(ft.monto_total - ft.monto_pagado), 0) AS pendiente,
            COALESCE(SUM(ft.total_sobres), 0)         AS total_sobres
        FROM facturas_transporte ft
        JOIN personal p ON p.id = ft.courrier_id
        WHERE ft.estado != 'anulada'
          AND EXTRACT(YEAR FROM ft.fecha_factura) = :anio
          {mes_filter}
        GROUP BY p.id, p.nombre_completo
        ORDER BY monto_total DESC
    """)

    clientes_sql = text(f"""
        SELECT
            c.nombre_empresa                          AS cliente,
            COALESCE(SUM(dft.cantidad_sobres), 0)    AS total_sobres,
            COALESCE(SUM(dft.costo_asignado), 0)     AS costo_total
        FROM detalle_facturas_transporte dft
        JOIN facturas_transporte ft ON dft.factura_id = ft.id
        JOIN ordenes o ON dft.orden_id = o.id
        JOIN clientes c ON o.cliente_id = c.id
        WHERE ft.estado != 'anulada'
          AND EXTRACT(YEAR FROM ft.fecha_factura) = :anio
          {mes_filter}
        GROUP BY c.id, c.nombre_empresa
        ORDER BY costo_total DESC
    """)

    couriers_rows = (await db.execute(couriers_sql, params)).mappings().all()
    clientes_rows = (await db.execute(clientes_sql, params)).mappings().all()

    couriers = [
        ResumenCourierReal(
            courrier=r["courrier"],
            total_facturas=r["total_facturas"],
            monto_total=float(r["monto_total"]),
            monto_pagado=float(r["monto_pagado"]),
            pendiente=float(r["pendiente"]),
            total_sobres=int(r["total_sobres"]),
            costo_por_sobre=float(r["monto_total"]) / int(r["total_sobres"]) if int(r["total_sobres"]) > 0 else 0.0,
        )
        for r in couriers_rows
    ]
    clientes = [
        ResumenClienteFlete(
            cliente=r["cliente"],
            total_sobres=int(r["total_sobres"]),
            costo_total=float(r["costo_total"]),
            costo_por_sobre=float(r["costo_total"]) / int(r["total_sobres"]) if int(r["total_sobres"]) > 0 else 0.0,
        )
        for r in clientes_rows
    ]

    return {"couriers": couriers, "clientes": clientes}


# ── CRUD Facturas ─────────────────────────────────────────────────────────────

@router.get("/", response_model=list[FacturaTransporteRead])
async def list_facturas(
    courrier_id: int | None = None,
    estado: str | None = None,
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    search: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(FacturaTransporte).order_by(FacturaTransporte.fecha_factura.desc())
    if courrier_id is not None:
        q = q.where(FacturaTransporte.courrier_id == courrier_id)
    if estado:
        q = q.where(FacturaTransporte.estado == estado)
    if fecha_desde:
        q = q.where(FacturaTransporte.fecha_factura >= fecha_desde)
    if fecha_hasta:
        q = q.where(FacturaTransporte.fecha_factura <= fecha_hasta)
    rows = (await db.execute(q)).scalars().all()

    if search:
        term = search.lower()
        rows = [
            r for r in rows
            if term in r.numero_factura.lower()
            or (r.courrier and term in r.courrier.nombre_completo.lower())
        ]

    return [_to_dict(r) for r in rows]


@router.post("/", response_model=FacturaTransporteRead, status_code=status.HTTP_201_CREATED)
async def create_factura(
    body: FacturaTransporteCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = FacturaTransporte(**body.model_dump())
    db.add(ft)
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.put("/{factura_id}", response_model=FacturaTransporteRead)
async def update_factura(
    factura_id: int,
    body: FacturaTransporteUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    old_monto = float(ft.monto_total)
    changes = body.model_dump(exclude_none=True)
    new_monto = float(changes.get("monto_total", old_monto))

    for field, val in changes.items():
        setattr(ft, field, val)

    if abs(new_monto - old_monto) > 0.001 and ft.total_sobres > 0 and ft.detalles:
        await _recalculate_detalles(ft, ft.total_sobres, new_monto, db)

    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.post("/{factura_id}/pagar", response_model=FacturaTransporteRead)
async def pagar_factura(
    factura_id: int,
    body: PagarTransporteRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ft.monto_pagado = float(ft.monto_pagado) + body.monto_pago
    ft.estado = "pagada" if float(ft.monto_pagado) >= float(ft.monto_total) else "pendiente"
    if body.observaciones:
        ft.observaciones = body.observaciones
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.delete("/{factura_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_factura(
    factura_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    if ft.estado == "pagada":
        raise HTTPException(status_code=400, detail="No se puede eliminar una factura pagada")
    await db.delete(ft)
    await db.commit()


# ── Detalles (órdenes asignadas a una factura) ────────────────────────────────

@router.post("/{factura_id}/detalles", response_model=FacturaTransporteRead, status_code=status.HTTP_201_CREATED)
async def add_detalle(
    factura_id: int,
    body: DetalleTransporteCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    if any(d.orden_id == body.orden_id for d in ft.detalles):
        raise HTTPException(status_code=400, detail="Esta orden ya está asignada a la factura")

    new_total = ft.total_sobres + body.cantidad_sobres
    monto = float(ft.monto_total)

    # Recalculate existing detalles with new total
    await _recalculate_detalles(ft, new_total, monto, db)

    # Add new detalle
    new_cost = monto * body.cantidad_sobres / new_total if new_total > 0 else 0.0
    det = DetalleFacturaTransporte(
        factura_id=factura_id,
        orden_id=body.orden_id,
        cantidad_sobres=body.cantidad_sobres,
        costo_asignado=new_cost,
    )
    db.add(det)

    # Update orden costo_flete_total
    await db.execute(
        text("UPDATE ordenes SET costo_flete_total = COALESCE(costo_flete_total, 0) + :c WHERE id = :id"),
        {"c": new_cost, "id": body.orden_id},
    )

    ft.total_sobres = new_total
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.delete("/{factura_id}/detalles/{detalle_id}", response_model=FacturaTransporteRead)
async def remove_detalle(
    factura_id: int,
    detalle_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    det = next((d for d in ft.detalles if d.id == detalle_id), None)
    if det is None:
        raise HTTPException(status_code=404, detail="Detalle no encontrado")

    old_cost = float(det.costo_asignado)
    new_total = ft.total_sobres - det.cantidad_sobres

    # Reverse cost on the order
    if det.orden_id:
        await db.execute(
            text("UPDATE ordenes SET costo_flete_total = GREATEST(0, COALESCE(costo_flete_total, 0) - :c) WHERE id = :id"),
            {"c": old_cost, "id": det.orden_id},
        )

    await db.delete(det)
    await db.flush()

    # Reload detalles and recalculate remaining ones
    await db.refresh(ft)
    if new_total > 0 and ft.detalles:
        await _recalculate_detalles(ft, new_total, float(ft.monto_total), db)

    ft.total_sobres = new_total
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)
