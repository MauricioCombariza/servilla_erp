from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.gestiones import SerialGestion
from app.schemas.gestiones import (
    CambiarMensajeroRequest,
    CambiarPrecioRequest,
    PlanillaActionResult,
    PlanillaResumen,
    RecalcularRequest,
    RecalcularResult,
    SerialGestionRead,
    SerialGestionUpdate,
)
from app.services.planillas_service import (
    bloquear_planilla,
    cambiar_mensajero_planilla,
    cambiar_precio_planilla,
    desbloquear_planilla,
    recalcular_precios,
    resumen_planillas,
)

router = APIRouter(prefix="/api/gestiones", tags=["gestiones"])
_auth = Depends(require_role("administrador", "logistica"))


# ── Planillas (rutas específicas antes de /{id}) ──────────────────────────────

@router.get("/planillas/resumen", response_model=list[PlanillaResumen])
async def get_planillas_resumen(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    cod_men: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await resumen_planillas(db, fecha_desde, fecha_hasta, cod_men)


@router.patch("/planillas/{planilla}/mensajero", response_model=PlanillaActionResult)
async def patch_mensajero_planilla(
    planilla: str = Path(...),
    body: CambiarMensajeroRequest = ...,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await cambiar_mensajero_planilla(planilla, body, db)


@router.patch("/planillas/{planilla}/precio", response_model=PlanillaActionResult)
async def patch_precio_planilla(
    planilla: str = Path(...),
    body: CambiarPrecioRequest = ...,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await cambiar_precio_planilla(planilla, body.precio_mensajero, db)


@router.post("/planillas/{planilla}/bloquear", response_model=PlanillaActionResult)
async def post_bloquear_planilla(
    planilla: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await bloquear_planilla(planilla, db)


@router.delete("/planillas/{planilla}/bloquear", response_model=PlanillaActionResult)
async def delete_bloquear_planilla(
    planilla: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await desbloquear_planilla(planilla, db)


# ── Recalcular precios ────────────────────────────────────────────────────────

@router.post("/recalcular", response_model=RecalcularResult)
async def post_recalcular(
    body: RecalcularRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await recalcular_precios(body, db)


# ── Seriales individuales ─────────────────────────────────────────────────────

@router.get("/", response_model=list[SerialGestionRead])
async def list_seriales(
    planilla: str | None = None,
    cod_men: str | None = None,
    estado: str | None = None,
    cliente_id: int | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(SerialGestion).order_by(SerialGestion.f_esc.desc()).limit(limit).offset(offset)
    if planilla:
        q = q.where(SerialGestion.planilla == planilla)
    if cod_men:
        q = q.where(SerialGestion.cod_men == cod_men)
    if estado:
        q = q.where(SerialGestion.estado == estado)
    if cliente_id:
        q = q.where(SerialGestion.cliente_id == cliente_id)
    if fecha_desde:
        q = q.where(SerialGestion.f_esc >= fecha_desde)
    if fecha_hasta:
        q = q.where(SerialGestion.f_esc <= fecha_hasta)
    return (await db.execute(q)).scalars().all()


@router.get("/{serial_id}", response_model=SerialGestionRead)
async def get_serial(
    serial_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    sg = (await db.execute(select(SerialGestion).where(SerialGestion.id == serial_id))).scalar_one_or_none()
    if sg is None:
        raise HTTPException(status_code=404, detail="Serial no encontrado")
    return sg


@router.patch("/{serial_id}", response_model=SerialGestionRead)
async def patch_serial(
    serial_id: int,
    body: SerialGestionUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    sg = (await db.execute(select(SerialGestion).where(SerialGestion.id == serial_id))).scalar_one_or_none()
    if sg is None:
        raise HTTPException(status_code=404, detail="Serial no encontrado")
    changes = body.model_dump(exclude_none=True)
    if changes:
        # Cualquier edición manual marca el serial como bloqueado
        changes.setdefault("editado_manualmente", True)
        for field, value in changes.items():
            setattr(sg, field, value)
        await db.commit()
        await db.refresh(sg)
    return sg
