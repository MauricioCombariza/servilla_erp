from datetime import UTC, datetime

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.pages import PAGE_CATALOG, PAGE_KEYS
from app.database import get_db
from app.models.roles import Rol, RolPagina
from app.models.usuarios import Usuario
from app.schemas.usuarios_admin import (
    PaginaRead,
    RolCreate, RolRead, RolUpdate,
    UsuarioAdminCreate, UsuarioAdminPasswordReset, UsuarioAdminRead, UsuarioAdminUpdate,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
_auth = Depends(require_role("administrador"))


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


# ── Páginas (catálogo fijo) ───────────────────────────────────────────────────

@router.get("/paginas", response_model=list[PaginaRead])
async def list_paginas(_=_auth):
    return [PaginaRead(key=p.key, label=p.label, path=p.path) for p in PAGE_CATALOG]


# ── Usuarios ─────────────────────────────────────────────────────────────────

@router.get("/usuarios", response_model=list[UsuarioAdminRead])
async def list_usuarios(db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Usuario).order_by(Usuario.username))
    return result.scalars().all()


@router.post("/usuarios", response_model=UsuarioAdminRead, status_code=status.HTTP_201_CREATED)
async def create_usuario(body: UsuarioAdminCreate, db: AsyncSession = Depends(get_db), _=_auth):
    usuario = Usuario(
        username=body.username,
        password_hash=_hash_password(body.password),
        nombre_completo=body.nombre_completo,
        email=body.email,
        rol=body.rol,
        fecha_creacion=datetime.now(UTC),
    )
    db.add(usuario)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        msg = str(e.orig)
        if "fk_usuarios_rol" in msg:
            raise HTTPException(status_code=400, detail=f"El rol '{body.rol}' no existe")
        raise HTTPException(status_code=400, detail="El username ya existe")
    await db.refresh(usuario)
    return usuario


@router.put("/usuarios/{usuario_id}", response_model=UsuarioAdminRead)
async def update_usuario(
    usuario_id: int, body: UsuarioAdminUpdate, db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("administrador")),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    data = body.model_dump(exclude_none=True)

    if usuario_id == current_user["id"] and data.get("activo") is False:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")

    era_admin_activo = usuario.rol == "administrador" and usuario.activo
    sigue_admin_activo = data.get("rol", usuario.rol) == "administrador" and data.get("activo", usuario.activo)
    if era_admin_activo and not sigue_admin_activo:
        count = await db.execute(
            select(func.count(Usuario.id)).where(
                Usuario.rol == "administrador", Usuario.activo == True, Usuario.id != usuario_id  # noqa: E712
            )
        )
        if count.scalar_one() == 0:
            raise HTTPException(status_code=400, detail="No puede quedar ningún administrador activo")

    for field, value in data.items():
        setattr(usuario, field, value)

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        msg = str(e.orig)
        if "fk_usuarios_rol" in msg:
            raise HTTPException(status_code=400, detail=f"El rol '{data.get('rol')}' no existe")
        raise HTTPException(status_code=400, detail="Error al actualizar el usuario")
    await db.refresh(usuario)
    return usuario


@router.put("/usuarios/{usuario_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    usuario_id: int, body: UsuarioAdminPasswordReset, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalar_one_or_none()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    usuario.password_hash = _hash_password(body.password)
    await db.commit()


# ── Roles ────────────────────────────────────────────────────────────────────

async def _rol_paginas(db: AsyncSession, nombre: str) -> list[str]:
    result = await db.execute(
        select(RolPagina.page_key).where(RolPagina.rol == nombre).order_by(RolPagina.page_key)
    )
    return [row[0] for row in result.all()]


def _validar_paginas(paginas: list[str]) -> None:
    desconocidas = set(paginas) - PAGE_KEYS
    if desconocidas:
        raise HTTPException(status_code=400, detail=f"Páginas desconocidas: {', '.join(sorted(desconocidas))}")


@router.get("/roles", response_model=list[RolRead])
async def list_roles(db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Rol).order_by(Rol.nombre))
    roles = result.scalars().all()
    out = []
    for rol in roles:
        paginas = await _rol_paginas(db, rol.nombre)
        out.append(RolRead(
            nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo,
            fecha_creacion=rol.fecha_creacion, paginas=paginas,
        ))
    return out


@router.post("/roles", response_model=RolRead, status_code=status.HTTP_201_CREATED)
async def create_rol(body: RolCreate, db: AsyncSession = Depends(get_db), _=_auth):
    _validar_paginas(body.paginas)

    existe = await db.execute(select(Rol.nombre).where(Rol.nombre == body.nombre))
    if existe.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Ya existe un rol con ese nombre")

    rol = Rol(nombre=body.nombre, descripcion=body.descripcion, fecha_creacion=datetime.now(UTC))
    db.add(rol)
    for page_key in body.paginas:
        db.add(RolPagina(rol=body.nombre, page_key=page_key))
    await db.commit()

    return RolRead(nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo,
                    fecha_creacion=rol.fecha_creacion, paginas=sorted(body.paginas))


@router.put("/roles/{nombre}", response_model=RolRead)
async def update_rol(nombre: str, body: RolUpdate, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(select(Rol).where(Rol.nombre == nombre))
    rol = result.scalar_one_or_none()
    if rol is None:
        raise HTTPException(status_code=404, detail="Rol no encontrado")

    paginas_actuales = await _rol_paginas(db, nombre)
    nuevas_paginas = body.paginas if body.paginas is not None else paginas_actuales

    if nombre == "administrador":
        if body.activo is False:
            raise HTTPException(status_code=400, detail="El rol 'administrador' no puede desactivarse")
        if set(nuevas_paginas) != PAGE_KEYS:
            raise HTTPException(
                status_code=400,
                detail="El rol 'administrador' debe conservar acceso a todas las páginas",
            )

    if body.paginas is not None:
        _validar_paginas(body.paginas)
        await db.execute(delete(RolPagina).where(RolPagina.rol == nombre))
        for page_key in body.paginas:
            db.add(RolPagina(rol=nombre, page_key=page_key))

    if body.descripcion is not None:
        rol.descripcion = body.descripcion
    if body.activo is not None:
        rol.activo = body.activo

    await db.commit()
    await db.refresh(rol)
    paginas = await _rol_paginas(db, nombre)
    return RolRead(nombre=rol.nombre, descripcion=rol.descripcion, activo=rol.activo,
                    fecha_creacion=rol.fecha_creacion, paginas=paginas)
