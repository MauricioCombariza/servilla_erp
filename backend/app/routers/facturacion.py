from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.facturacion import FacturaEmitida, FacturaRecibida
from app.schemas.facturacion import (
    CuentaItem,
    FacturaEmitidaCreate,
    FacturaEmitidaRead,
    FacturaEmitidaUpdate,
    FacturaRecibidaCreate,
    FacturaRecibidaRead,
    FacturaRecibidaUpdate,
    PagoCreate,
    PagoRead,
    PagoRealizadoRead,
    ResumenFinanciero,
)
from app.services.facturacion_service import (
    anular_factura_emitida,
    crear_factura_emitida,
    crear_factura_recibida,
    get_resumen_financiero,
    registrar_pago_realizado,
    registrar_pago_recibido,
)

router = APIRouter(prefix="/api/facturacion", tags=["facturacion"])
_auth = Depends(require_role("administrador", "logistica"))


# ── Resumen financiero ─────────────────────────────────────────────────────────

@router.get("/resumen", response_model=ResumenFinanciero)
async def resumen(db: AsyncSession = Depends(get_db), _=_auth):
    return await get_resumen_financiero(db)


# ── Cuentas por cobrar / pagar (vistas PostgreSQL) ────────────────────────────

@router.get("/cuentas-por-cobrar", response_model=list[CuentaItem])
async def cuentas_por_cobrar(db: AsyncSession = Depends(get_db), _=_auth):
    rows = (await db.execute(text("SELECT * FROM vista_cuentas_por_cobrar"))).mappings().all()
    return [
        CuentaItem(
            id=r["id"], tipo="factura_emitida",
            referencia=r["numero_factura"],
            codigo=None,
            acreedor_o_deudor=r["cliente"],
            fecha_vencimiento=r["fecha_vencimiento"],
            monto=float(r["saldo_pendiente"]),
            estado=r["estado"],
            dias=int(r["dias_vencidos"]),
            clasificacion=r["clasificacion"],
        )
        for r in rows
    ]


@router.get("/cuentas-por-pagar", response_model=list[CuentaItem])
async def cuentas_por_pagar(db: AsyncSession = Depends(get_db), _=_auth):
    rows = (await db.execute(text("SELECT * FROM vista_cuentas_por_pagar"))).mappings().all()
    return [
        CuentaItem(
            id=r["id"], tipo=r["tipo"],
            referencia=r["referencia"],
            codigo=r["codigo"],
            acreedor_o_deudor=r["acreedor"],
            fecha_vencimiento=r["fecha_vencimiento"],
            monto=float(r["monto"]),
            estado=r["estado"],
            dias=int(r["dias_hasta_vencimiento"]),
            clasificacion=r["clasificacion"],
        )
        for r in rows
    ]


# ── Facturas emitidas ──────────────────────────────────────────────────────────

@router.get("/emitidas", response_model=list[FacturaEmitidaRead])
async def list_emitidas(
    cliente_id: int | None = None,
    estado: str | None = None,
    periodo_mes: int | None = None,
    periodo_anio: int | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = (
        select(FacturaEmitida)
        .order_by(FacturaEmitida.fecha_emision.desc())
        .limit(limit).offset(offset)
    )
    if cliente_id:
        q = q.where(FacturaEmitida.cliente_id == cliente_id)
    if estado:
        q = q.where(FacturaEmitida.estado == estado)
    if periodo_mes:
        q = q.where(FacturaEmitida.periodo_mes == periodo_mes)
    if periodo_anio:
        q = q.where(FacturaEmitida.periodo_anio == periodo_anio)
    return (await db.execute(q)).scalars().all()


@router.post("/emitidas", response_model=FacturaEmitidaRead, status_code=201)
async def create_emitida(
    body: FacturaEmitidaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        return await crear_factura_emitida(body, db, current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/emitidas/{factura_id}", response_model=FacturaEmitidaRead)
async def get_emitida(factura_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    f = (await db.execute(select(FacturaEmitida).where(FacturaEmitida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    return f


@router.put("/emitidas/{factura_id}", response_model=FacturaEmitidaRead)
async def update_emitida(
    factura_id: int, body: FacturaEmitidaUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    f = (await db.execute(select(FacturaEmitida).where(FacturaEmitida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    if f.estado == "anulada":
        raise HTTPException(409, "No se puede editar una factura anulada")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(f, field, val)
    await db.commit()
    await db.refresh(f)
    return f


@router.delete("/emitidas/{factura_id}", status_code=204)
async def anular_emitida(factura_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    f = (await db.execute(select(FacturaEmitida).where(FacturaEmitida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    await anular_factura_emitida(f, db)


@router.post("/emitidas/{factura_id}/pagos", response_model=PagoRead, status_code=201)
async def pago_emitida(
    factura_id: int,
    body: PagoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    f = (await db.execute(select(FacturaEmitida).where(FacturaEmitida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    if f.estado in ("anulada", "pagada"):
        raise HTTPException(409, f"Factura en estado '{f.estado}', no acepta más pagos")
    pago, _ = await registrar_pago_recibido(f, body, db, current_user["id"])
    return pago


@router.get("/emitidas/{factura_id}/pagos", response_model=list[PagoRead])
async def list_pagos_emitida(factura_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    f = (await db.execute(select(FacturaEmitida).where(FacturaEmitida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    return f.pagos


# ── Facturas recibidas ─────────────────────────────────────────────────────────

@router.get("/recibidas", response_model=list[FacturaRecibidaRead])
async def list_recibidas(
    personal_id: int | None = None,
    tipo: str | None = None,
    estado: str | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(FacturaRecibida).order_by(FacturaRecibida.fecha_vencimiento).limit(limit)
    if personal_id:
        q = q.where(FacturaRecibida.personal_id == personal_id)
    if tipo:
        q = q.where(FacturaRecibida.tipo == tipo)
    if estado:
        q = q.where(FacturaRecibida.estado == estado)
    return (await db.execute(q)).scalars().all()


@router.post("/recibidas", response_model=FacturaRecibidaRead, status_code=201)
async def create_recibida(body: FacturaRecibidaCreate, db: AsyncSession = Depends(get_db), _=_auth):
    return await crear_factura_recibida(body, db)


@router.get("/recibidas/{factura_id}", response_model=FacturaRecibidaRead)
async def get_recibida(factura_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    f = (await db.execute(select(FacturaRecibida).where(FacturaRecibida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    return f


@router.put("/recibidas/{factura_id}", response_model=FacturaRecibidaRead)
async def update_recibida(
    factura_id: int, body: FacturaRecibidaUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    f = (await db.execute(select(FacturaRecibida).where(FacturaRecibida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(f, field, val)
    await db.commit()
    await db.refresh(f)
    return f


@router.post("/recibidas/{factura_id}/pagos", response_model=PagoRealizadoRead, status_code=201)
async def pago_recibida(
    factura_id: int,
    body: PagoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    f = (await db.execute(select(FacturaRecibida).where(FacturaRecibida.id == factura_id))).scalar_one_or_none()
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    if f.estado in ("anulada", "pagada"):
        raise HTTPException(409, f"Factura en estado '{f.estado}', no acepta más pagos")
    pago, _ = await registrar_pago_realizado(f, body, db, current_user["id"])
    return pago
