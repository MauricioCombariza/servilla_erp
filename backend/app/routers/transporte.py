from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.transporte import FacturaTransporte
from app.schemas.transporte import (
    FacturaTransporteCreate, FacturaTransporteRead, FacturaTransporteUpdate,
    PagarTransporteRequest, PrefacturaCourier,
)

router = APIRouter(prefix="/api/transporte", tags=["transporte"])
_auth = Depends(require_role("administrador", "contabilidad", "operaciones"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


# ── Prefacturas (resumen desde seriales_gestion) ──────────────────────────────

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


# ── CRUD Facturas Transporte ──────────────────────────────────────────────────

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
        "detalles": [
            {"id": d.id, "factura_id": d.factura_id, "orden_id": d.orden_id,
             "cantidad_sobres": d.cantidad_sobres, "costo_asignado": float(d.costo_asignado)}
            for d in ft.detalles
        ],
    }


@router.get("/", response_model=list[FacturaTransporteRead])
async def list_facturas(
    courrier_id: int | None = None,
    estado: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(FacturaTransporte).order_by(FacturaTransporte.fecha_factura.desc())
    if courrier_id is not None:
        q = q.where(FacturaTransporte.courrier_id == courrier_id)
    if estado:
        q = q.where(FacturaTransporte.estado == estado)
    rows = (await db.execute(q)).scalars().all()
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
    factura_id: int, body: FacturaTransporteUpdate,
    db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(ft, field, val)
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.post("/{factura_id}/pagar", response_model=FacturaTransporteRead)
async def pagar_factura(
    factura_id: int, body: PagarTransporteRequest,
    db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    ft = (await db.execute(
        select(FacturaTransporte).where(FacturaTransporte.id == factura_id)
    )).scalar_one_or_none()
    if ft is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    ft.monto_pagado = float(ft.monto_pagado) + body.monto_pago
    ft.estado = "pagada" if ft.monto_pagado >= float(ft.monto_total) else "pendiente"
    if body.observaciones:
        ft.observaciones = body.observaciones
    await db.commit()
    await db.refresh(ft)
    return _to_dict(ft)


@router.delete("/{factura_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_factura(
    factura_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin,
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
