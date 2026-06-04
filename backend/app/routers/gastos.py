from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.gastos import GastoAdministrativo, GastoFijoMensual, PagoGastoFijo
from app.schemas.gastos import (
    GastoAdminCreate, GastoAdminRead, GastoAdminResumen, GastoAdminUpdate,
    GastoFijoCreate, GastoFijoRead, GastoFijoUpdate,
    PagoGastoFijoCreate, PagoGastoFijoRead,
)

router = APIRouter(prefix="/api/gastos", tags=["gastos"])
_auth = Depends(require_role("administrador", "contabilidad"))


# ── Gastos administrativos ────────────────────────────────────────────────────

@router.get("/", response_model=list[GastoAdminRead])
async def list_gastos(
    mes: int | None = None,
    anio: int | None = None,
    categoria: str | None = None,
    estado: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    from sqlalchemy import extract
    q = select(GastoAdministrativo).order_by(GastoAdministrativo.fecha.desc())
    if mes is not None:
        q = q.where(extract("month", GastoAdministrativo.fecha) == mes)
    if anio is not None:
        q = q.where(extract("year", GastoAdministrativo.fecha) == anio)
    if categoria:
        q = q.where(GastoAdministrativo.categoria == categoria)
    if estado:
        q = q.where(GastoAdministrativo.estado == estado)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/resumen", response_model=list[GastoAdminResumen])
async def resumen_gastos(
    mes: int | None = None,
    anio: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    from sqlalchemy import extract
    q = (
        select(
            GastoAdministrativo.categoria,
            func.sum(GastoAdministrativo.monto).label("total"),
            func.count(GastoAdministrativo.id).label("cantidad"),
        )
        .group_by(GastoAdministrativo.categoria)
        .order_by(func.sum(GastoAdministrativo.monto).desc())
    )
    if mes is not None:
        q = q.where(extract("month", GastoAdministrativo.fecha) == mes)
    if anio is not None:
        q = q.where(extract("year", GastoAdministrativo.fecha) == anio)
    rows = (await db.execute(q)).all()
    return [{"categoria": r.categoria, "total": float(r.total), "cantidad": r.cantidad} for r in rows]


@router.post("/", response_model=GastoAdminRead, status_code=status.HTTP_201_CREATED)
async def create_gasto(body: GastoAdminCreate, db: AsyncSession = Depends(get_db), _=_auth):
    g = GastoAdministrativo(**body.model_dump())
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


@router.put("/{gasto_id}", response_model=GastoAdminRead)
async def update_gasto(
    gasto_id: int, body: GastoAdminUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(
        select(GastoAdministrativo).where(GastoAdministrativo.id == gasto_id)
    )
    g = result.scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(g, field, value)
    await db.commit()
    await db.refresh(g)
    return g


@router.delete("/{gasto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gasto(gasto_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(
        select(GastoAdministrativo).where(GastoAdministrativo.id == gasto_id)
    )
    g = result.scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    await db.delete(g)
    await db.commit()


# ── Gastos fijos ──────────────────────────────────────────────────────────────

@router.get("/fijos", response_model=list[GastoFijoRead])
async def list_gastos_fijos(
    activo: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(GastoFijoMensual).order_by(GastoFijoMensual.categoria)
    if activo is not None:
        q = q.where(GastoFijoMensual.activo == activo)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/fijos", response_model=GastoFijoRead, status_code=status.HTTP_201_CREATED)
async def create_gasto_fijo(body: GastoFijoCreate, db: AsyncSession = Depends(get_db), _=_auth):
    g = GastoFijoMensual(**body.model_dump())
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return g


@router.put("/fijos/{gasto_id}", response_model=GastoFijoRead)
async def update_gasto_fijo(
    gasto_id: int, body: GastoFijoUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(
        select(GastoFijoMensual).where(GastoFijoMensual.id == gasto_id)
    )
    g = result.scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="Gasto fijo no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(g, field, value)
    await db.commit()
    await db.refresh(g)
    return g


@router.post("/fijos/{gasto_id}/pagos", response_model=PagoGastoFijoRead, status_code=201)
async def registrar_pago_fijo(
    gasto_id: int, body: PagoGastoFijoCreate, db: AsyncSession = Depends(get_db), _=_auth
):
    exists = await db.execute(
        select(GastoFijoMensual.id).where(GastoFijoMensual.id == gasto_id)
    )
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Gasto fijo no encontrado")
    p = PagoGastoFijo(gasto_fijo_id=gasto_id, **body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p
