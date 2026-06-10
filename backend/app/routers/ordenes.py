from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.ordenes import Orden
from app.schemas.ordenes import CargaMasivaResult, OrdenCreate, OrdenRead, OrdenUpdate
from app.services.ordenes_service import procesar_csv

router = APIRouter(prefix="/api/ordenes", tags=["ordenes"])
_auth = Depends(require_role("administrador", "logistica"))


@router.get("/", response_model=list[OrdenRead])
async def list_ordenes(
    cliente_id: int | None = None,
    estado: str | None = None,
    facturado: bool | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(Orden).order_by(Orden.fecha_recepcion.desc()).limit(limit).offset(offset)
    if cliente_id is not None:
        q = q.where(Orden.cliente_id == cliente_id)
    if estado is not None:
        q = q.where(Orden.estado == estado)
    if facturado is not None:
        q = q.where(Orden.facturado == facturado)
    if fecha_desde:
        q = q.where(Orden.fecha_recepcion >= fecha_desde)
    if fecha_hasta:
        q = q.where(Orden.fecha_recepcion <= fecha_hasta)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=OrdenRead, status_code=status.HTTP_201_CREATED)
async def create_orden(body: OrdenCreate, db: AsyncSession = Depends(get_db), _=_auth):
    orden = Orden(**body.model_dump())
    orden.cantidad_recibido = body.cantidad_total
    db.add(orden)
    await db.commit()
    await db.refresh(orden)
    return orden


@router.get("/{orden_id}", response_model=OrdenRead)
async def get_orden(orden_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Orden).where(Orden.id == orden_id))
    orden = result.scalar_one_or_none()
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    return orden


@router.put("/{orden_id}", response_model=OrdenRead)
async def update_orden(
    orden_id: int, body: OrdenUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(Orden).where(Orden.id == orden_id))
    orden = result.scalar_one_or_none()
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(orden, field, value)
    await db.commit()
    await db.refresh(orden)
    return orden


@router.delete("/{orden_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_orden(orden_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Orden).where(Orden.id == orden_id))
    orden = result.scalar_one_or_none()
    if orden is None:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    orden.estado = "anulada"
    await db.commit()


@router.post("/carga-masiva", response_model=CargaMasivaResult)
async def carga_masiva(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos CSV")
    contenido = await file.read()
    if len(contenido) > 450 * 1024 * 1024:  # 450 MB max
        raise HTTPException(status_code=413, detail="Archivo demasiado grande (max 450 MB)")
    return await procesar_csv(contenido, db)
