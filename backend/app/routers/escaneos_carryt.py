from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.escaneos_carryt import EscaneoCarryt
from app.schemas.escaneos_carryt import EscaneoCarrytCreate, EscaneoCarrytRead

router = APIRouter(prefix="/api/escaneos-carryt", tags=["escaneos-carryt"])
_auth = Depends(require_role("administrador", "logistica"))


@router.get("/", response_model=list[EscaneoCarrytRead])
async def list_escaneos(
    cod_men: str,
    fecha: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(EscaneoCarryt).where(EscaneoCarryt.cod_men == cod_men)
    q = q.where(EscaneoCarryt.fecha == (fecha or date.today()))
    q = q.order_by(EscaneoCarryt.fecha_creacion.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=EscaneoCarrytRead, status_code=201)
async def registrar_escaneo(
    body: EscaneoCarrytCreate, db: AsyncSession = Depends(get_db), _=_auth
):
    existente = await db.execute(
        select(EscaneoCarryt).where(EscaneoCarryt.serial == body.serial)
    )
    e = existente.scalar_one_or_none()
    if e is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Serial ya registrado el {e.fecha} para {e.nombre_mensajero} ({e.cod_men})",
        )

    escaneo = EscaneoCarryt(
        cliente="Carryt",
        fecha=date.today(),
        cod_men=body.cod_men,
        nombre_mensajero=body.nombre_mensajero,
        serial=body.serial,
    )
    db.add(escaneo)
    await db.commit()
    await db.refresh(escaneo)
    return escaneo
