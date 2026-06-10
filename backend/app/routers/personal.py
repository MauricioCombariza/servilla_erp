from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.ciudades import Ciudad
from app.models.personal import Personal, PersonalCiudad
from app.schemas.personal import (
    CiudadRead,
    PersonalCiudadCreate, PersonalCiudadRead, PersonalCiudadUpdate,
    PersonalCreate, PersonalRead, PersonalUpdate, PersonalWithCiudades,
)

router = APIRouter(prefix="/api/personal", tags=["personal"])
_auth = Depends(require_role("administrador", "logistica"))


# ── Ciudades (reference endpoint) ────────────────────────────────────────────

@router.get("/ciudades", response_model=list[CiudadRead])
async def list_ciudades(db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(
        select(Ciudad).where(Ciudad.activa == True).order_by(Ciudad.nombre)  # noqa: E712
    )
    return result.scalars().all()


# ── Personal ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[PersonalRead])
async def list_personal(
    tipo: str | None = None,
    activo: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(Personal).order_by(Personal.nombre_completo)
    if tipo is not None:
        q = q.where(Personal.tipo_personal == tipo)
    if activo is not None:
        q = q.where(Personal.activo == activo)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=PersonalRead, status_code=status.HTTP_201_CREATED)
async def create_personal(body: PersonalCreate, db: AsyncSession = Depends(get_db), _=_auth):
    personal = Personal(**body.model_dump())
    db.add(personal)
    await db.commit()
    await db.refresh(personal)
    return personal


@router.get("/by-code/{codigo}", response_model=PersonalRead)
async def get_personal_by_codigo(codigo: str, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(
        select(Personal).where(Personal.codigo == codigo, Personal.activo == True)  # noqa: E712
    )
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")
    return p


@router.get("/{personal_id}", response_model=PersonalWithCiudades)
async def get_personal(personal_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Personal).where(Personal.id == personal_id))
    personal = result.scalar_one_or_none()
    if personal is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")
    return personal


@router.put("/{personal_id}", response_model=PersonalRead)
async def update_personal(
    personal_id: int, body: PersonalUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(Personal).where(Personal.id == personal_id))
    personal = result.scalar_one_or_none()
    if personal is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(personal, field, value)
    await db.commit()
    await db.refresh(personal)
    return personal


@router.delete("/{personal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personal(personal_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Personal).where(Personal.id == personal_id))
    personal = result.scalar_one_or_none()
    if personal is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")
    personal.activo = False
    await db.commit()


# ── Tarifas por ciudad ────────────────────────────────────────────────────────

@router.get("/{personal_id}/ciudades", response_model=list[PersonalCiudadRead])
async def list_ciudades_personal(
    personal_id: int, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(
        select(PersonalCiudad)
        .where(PersonalCiudad.personal_id == personal_id)
        .order_by(PersonalCiudad.ciudad_id)
    )
    return result.scalars().all()


@router.post("/{personal_id}/ciudades", response_model=PersonalCiudadRead, status_code=201)
async def create_ciudad_personal(
    personal_id: int,
    body: PersonalCiudadCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    exists = await db.execute(select(Personal.id).where(Personal.id == personal_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")

    pc = PersonalCiudad(personal_id=personal_id, **body.model_dump())
    db.add(pc)
    await db.commit()
    await db.refresh(pc)
    return pc


@router.put("/{personal_id}/ciudades/{ciudad_id}", response_model=PersonalCiudadRead)
async def update_ciudad_personal(
    personal_id: int,
    ciudad_id: int,
    body: PersonalCiudadUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(
        select(PersonalCiudad).where(
            PersonalCiudad.personal_id == personal_id,
            PersonalCiudad.ciudad_id == ciudad_id,
        )
    )
    pc = result.scalar_one_or_none()
    if pc is None:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(pc, field, value)
    await db.commit()
    await db.refresh(pc)
    return pc


@router.delete("/{personal_id}/ciudades/{ciudad_id}", status_code=204)
async def delete_ciudad_personal(
    personal_id: int, ciudad_id: int, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(
        select(PersonalCiudad).where(
            PersonalCiudad.personal_id == personal_id,
            PersonalCiudad.ciudad_id == ciudad_id,
        )
    )
    pc = result.scalar_one_or_none()
    if pc is None:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    pc.activo = False
    await db.commit()
