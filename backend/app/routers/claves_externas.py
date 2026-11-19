"""Registro y vencimiento de las claves de sistemas fuera del ERP: FortiGate, servidores,
bases de datos, correo… (SER-MNT-F-02-2 Registro de claves, F-02-3 Listado de claves en
bóveda, SER-MNT-PR-02 §20.3).

El ERP no cambia esas claves ni las guarda: lleva quién las custodia, en qué sobre y cofre
están, cuándo se cambiaron y cuándo vencen, y avisa a los administradores.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.claves_externas import ClaveExterna, ClaveExternaCambio
from app.schemas.claves_externas import (
    CambioCreate,
    CambioRead,
    Categoria,
    ClaveExternaCreate,
    ClaveExternaRead,
    ClaveExternaUpdate,
    Resumen,
)

router = APIRouter(prefix="/api/admin/claves-externas", tags=["admin"])
_admin = require_role("administrador")

# SER-MNT-PR-02 §20.3
CATEGORIAS: dict[str, tuple[str, int]] = {
    "dominio_admin": ("Usuarios del dominio y administradores", 45),
    "estaciones_gpa": ("Administrador de las estaciones y GPA", 90),
    "fortinet": ("Admin de Fortinet", 180),
    "correo_sql_hojas": ("Correo, hojas de cálculo y usuarios de SQL", 360),
}


def hoy() -> date:
    """Fecha de hoy en Colombia (el servidor corre en UTC)."""
    return datetime.now(ZoneInfo("America/Bogota")).date()


def _aviso_dias(periodicidad: int) -> int:
    """Con cuánta anticipación avisar: 7 días para las de 45, hasta 30 para las anuales."""
    return min(30, max(7, periodicidad // 6))


def _leer(c: ClaveExterna) -> ClaveExternaRead:
    dia = hoy()
    r = ClaveExternaRead.model_validate(c)
    r.periodicidad_efectiva = c.periodicidad_dias or CATEGORIAS[c.categoria][1]
    if c.ultimo_cambio is None:
        r.estado = "sin_registro"
        return r
    r.vence_en = c.ultimo_cambio + timedelta(days=r.periodicidad_efectiva)
    r.dias_restantes = (r.vence_en - dia).days
    if r.dias_restantes < 0:
        r.estado = "vencida"
    elif r.dias_restantes <= _aviso_dias(r.periodicidad_efectiva):
        r.estado = "por_vencer"
    else:
        r.estado = "al_dia"
    return r


def _validar_categoria(categoria: str | None) -> None:
    if categoria is not None and categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail=f"Categoría desconocida: {categoria}")


async def _obtener(db: AsyncSession, clave_id: int) -> ClaveExterna:
    c = await db.get(ClaveExterna, clave_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    return c


@router.get("/categorias", response_model=list[Categoria])
async def categorias(_=Depends(_admin)):
    return [Categoria(clave=k, nombre=n, dias=d) for k, (n, d) in CATEGORIAS.items()]


@router.get("", response_model=list[ClaveExternaRead])
async def listar(todas: bool = False, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    q = select(ClaveExterna).order_by(ClaveExterna.aplicacion, ClaveExterna.usuario)
    if not todas:
        q = q.where(ClaveExterna.activo.is_(True))
    filas = [_leer(c) for c in (await db.scalars(q)).all()]
    orden = {"vencida": 0, "sin_registro": 1, "por_vencer": 2, "al_dia": 3}
    return sorted(filas, key=lambda r: (orden[r.estado], r.dias_restantes or 0))


@router.get("/resumen", response_model=Resumen)
async def resumen(db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    filas = [_leer(c) for c in (await db.scalars(
        select(ClaveExterna).where(ClaveExterna.activo.is_(True)))).all()]
    return Resumen(
        vencidas=sum(r.estado == "vencida" for r in filas),
        por_vencer=sum(r.estado == "por_vencer" for r in filas),
        sin_registro=sum(r.estado == "sin_registro" for r in filas),
    )


@router.post("", response_model=ClaveExternaRead, status_code=status.HTTP_201_CREATED)
async def crear(body: ClaveExternaCreate, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    _validar_categoria(body.categoria)
    c = ClaveExterna(**body.model_dump())
    db.add(c)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Esa cuenta ya está registrada para esa aplicación")
    await db.refresh(c)
    return _leer(c)


@router.put("/{clave_id}", response_model=ClaveExternaRead)
async def actualizar(clave_id: int, body: ClaveExternaUpdate,
                     db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    datos = body.model_dump(exclude_unset=True)
    _validar_categoria(datos.get("categoria"))
    c = await _obtener(db, clave_id)
    for k, v in datos.items():
        setattr(c, k, v)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Esa cuenta ya está registrada para esa aplicación")
    await db.refresh(c)
    return _leer(c)


@router.get("/{clave_id}/cambios", response_model=list[CambioRead])
async def historial(clave_id: int, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    await _obtener(db, clave_id)
    return (await db.scalars(
        select(ClaveExternaCambio).where(ClaveExternaCambio.clave_id == clave_id)
        .order_by(ClaveExternaCambio.fecha.desc(), ClaveExternaCambio.id.desc())
    )).all()


@router.post("/{clave_id}/cambios", response_model=ClaveExternaRead, status_code=status.HTTP_201_CREATED)
async def registrar_cambio(clave_id: int, body: CambioCreate,
                           db: AsyncSession = Depends(get_db), user: dict = Depends(_admin)):
    """Deja constancia de que la clave se cambió (y, si cambió, del sobre nuevo)."""
    if body.fecha > hoy():
        raise HTTPException(status_code=422, detail="La fecha del cambio no puede ser futura")
    c = await _obtener(db, clave_id)
    db.add(ClaveExternaCambio(clave_id=clave_id, registrado_por=user["id"], **body.model_dump()))
    if c.ultimo_cambio is None or body.fecha >= c.ultimo_cambio:
        c.ultimo_cambio = body.fecha
        if body.sobre_no:
            c.sobre_no = body.sobre_no
    await db.commit()
    await db.refresh(c)
    return _leer(c)
