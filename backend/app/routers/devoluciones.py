from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.models.devoluciones import Devolucion
from app.schemas.devoluciones import (
    CargaMasivaDevolucionesResult,
    DevolucionCreate,
    DevolucionDocumentoItem,
    DevolucionDocumentoRequest,
    DevolucionEstadoUpdate,
    DevolucionRead,
)
from app.services.devoluciones_docx import DOCX_MEDIA_TYPE, construir_docx_devolucion
from app.services.devoluciones_pdf import PDF_MEDIA_TYPE, construir_pdf_devolucion
from app.services.devoluciones_service import procesar_excel_devoluciones

router = APIRouter(prefix="/api/devoluciones", tags=["devoluciones"])
_auth = Depends(require_page("devoluciones"))
_auth_scan = Depends(require_page("devoluciones_scan"))

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


@router.post("/", response_model=DevolucionRead, status_code=status.HTTP_201_CREATED)
async def crear_devolucion(body: DevolucionCreate, db: AsyncSession = Depends(get_db), _=_auth):
    devolucion = Devolucion(
        serial=body.serial.strip(),
        nombre=body.nombre or None,
        telefono=body.telefono or None,
        direccion=body.direccion or None,
        localidad=body.localidad or None,
        estado=body.estado,
    )
    db.add(devolucion)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail=f"Ya existe una devolución con el serial '{body.serial}'"
        )
    await db.refresh(devolucion)
    return devolucion


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


@router.patch("/serial/{serial}", response_model=DevolucionRead)
async def actualizar_estado_por_serial(
    serial: str,
    body: DevolucionEstadoUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth_scan,
):
    result = await db.execute(select(Devolucion).where(Devolucion.serial == serial))
    devolucion = result.scalar_one_or_none()
    if devolucion is None:
        raise HTTPException(status_code=404, detail="Serial no encontrado en devoluciones")

    devolucion.estado = body.estado
    await db.commit()
    await db.refresh(devolucion)
    return devolucion


@router.post("/documento")
async def generar_documento(body: DevolucionDocumentoRequest, _=_auth_scan):
    contenido = construir_docx_devolucion(body.items)
    nombre_archivo = f"acta_devolucion_{date.today().isoformat()}.docx"
    return Response(
        content=contenido,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/reporte-dia")
async def reporte_dia(
    fecha: date = Query(default_factory=date.today),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    query = (
        select(Devolucion)
        .where(
            Devolucion.estado == "devolucion",
            func.date(Devolucion.fecha_actualizacion) == fecha,
        )
        .order_by(Devolucion.fecha_actualizacion)
    )
    result = await db.execute(query)
    devoluciones = result.scalars().all()
    if not devoluciones:
        raise HTTPException(
            status_code=404,
            detail=f"No hay devoluciones marcadas como 'devolucion' el {fecha.isoformat()}.",
        )

    items = [
        DevolucionDocumentoItem(
            serial=d.serial, nombre=d.nombre, direccion=d.direccion, localidad=d.localidad
        )
        for d in devoluciones
    ]
    contenido = construir_pdf_devolucion(items, fecha)
    nombre_archivo = f"acta_devolucion_{fecha.isoformat()}.pdf"
    return Response(
        content=contenido,
        media_type=PDF_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
