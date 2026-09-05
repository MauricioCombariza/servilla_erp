from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_page
from app.database import get_db
from app.models.geocercas import Geocerca
from app.schemas.geocercas import GeocercaCreate, GeocercaRead, GeocercaUpdate
from app.services.geocercas_service import calcular_area_m2

router = APIRouter(prefix="/api/geocercas", tags=["geocercas"])
_auth = Depends(require_page("geocercas"))


@router.get("/", response_model=list[GeocercaRead])
async def list_geocercas(
    activo: bool | None = True,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    query = select(Geocerca).order_by(Geocerca.fecha_creacion.desc())
    if activo is not None:
        query = query.where(Geocerca.activo == activo)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=GeocercaRead, status_code=status.HTTP_201_CREATED)
async def crear_geocerca(
    body: GeocercaCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _=_auth,
):
    area_m2 = calcular_area_m2(body.poligono)
    geocerca = Geocerca(
        nombre=body.nombre.strip(),
        poligono=body.poligono,
        area_m2=area_m2,
        creado_por=current_user["username"],
    )
    db.add(geocerca)
    await db.commit()
    await db.refresh(geocerca)
    return geocerca


@router.get("/{geocerca_id}", response_model=GeocercaRead)
async def obtener_geocerca(geocerca_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Geocerca).where(Geocerca.id == geocerca_id))
    geocerca = result.scalar_one_or_none()
    if geocerca is None:
        raise HTTPException(status_code=404, detail="Geocerca no encontrada")
    return geocerca


@router.patch("/{geocerca_id}", response_model=GeocercaRead)
async def actualizar_geocerca(
    geocerca_id: int,
    body: GeocercaUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(select(Geocerca).where(Geocerca.id == geocerca_id))
    geocerca = result.scalar_one_or_none()
    if geocerca is None:
        raise HTTPException(status_code=404, detail="Geocerca no encontrada")

    if body.nombre is not None:
        geocerca.nombre = body.nombre.strip()
    if body.activo is not None:
        geocerca.activo = body.activo

    await db.commit()
    await db.refresh(geocerca)
    return geocerca


@router.delete("/{geocerca_id}", response_model=GeocercaRead)
async def eliminar_geocerca(geocerca_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Geocerca).where(Geocerca.id == geocerca_id))
    geocerca = result.scalar_one_or_none()
    if geocerca is None:
        raise HTTPException(status_code=404, detail="Geocerca no encontrada")

    geocerca.activo = False
    await db.commit()
    await db.refresh(geocerca)
    return geocerca
