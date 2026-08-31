from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.models.devoluciones import Devolucion
from app.schemas.devoluciones import (
    CargaMasivaDevolucionesResult,
    DevolucionEstadoUpdate,
    DevolucionRead,
)
from app.services.devoluciones_service import procesar_excel_devoluciones

router = APIRouter(prefix="/api/devoluciones", tags=["devoluciones"])
_auth = Depends(require_page("devoluciones"))

# Los archivos de devoluciones son cargues manuales chicos (decenas de filas), no
# dashboards completos: se leen enteros en memoria (sin streaming a disco).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.get("/", response_model=list[DevolucionRead])
async def list_devoluciones(
    estado: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    query = select(Devolucion).order_by(Devolucion.fecha_actualizacion.desc())
    if estado is not None:
        query = query.where(Devolucion.estado == estado)
    if q:
        patron = f"%{q}%"
        query = query.where(or_(Devolucion.serial.ilike(patron), Devolucion.nombre.ilike(patron)))
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/carga-masiva", response_model=CargaMasivaDevolucionesResult)
async def carga_masiva(file: UploadFile, db: AsyncSession = Depends(get_db), _=_auth):
    fname = (file.filename or "").lower()
    if not fname.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos Excel (.xlsx)")

    contenido = await file.read()
    if len(contenido) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máximo {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    try:
        return await procesar_excel_devoluciones(contenido, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{devolucion_id}", response_model=DevolucionRead)
async def actualizar_estado(
    devolucion_id: int,
    body: DevolucionEstadoUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(select(Devolucion).where(Devolucion.id == devolucion_id))
    devolucion = result.scalar_one_or_none()
    if devolucion is None:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")

    devolucion.estado = body.estado
    await db.commit()
    await db.refresh(devolucion)
    return devolucion
