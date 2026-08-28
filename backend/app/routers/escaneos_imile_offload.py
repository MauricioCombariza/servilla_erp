from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.escaneos_imile_offload import EscaneoImileOffload
from app.schemas.escaneos_imile_offload import (
    EscaneoImileOffloadCreate,
    EscaneoImileOffloadRead,
    ImileStatus,
)
from app.services.imile_automation import (
    ImileSessionExpiredError,
    ScanResultado,
    imile_automation,
)

router = APIRouter(prefix="/api/escaneos-imile-offload", tags=["escaneos-imile-offload"])
_auth = Depends(require_role("administrador", "logistica", "mensajero"))


@router.get("/", response_model=list[EscaneoImileOffloadRead])
async def list_escaneos(
    cod_men: str,
    fecha: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(EscaneoImileOffload).where(EscaneoImileOffload.cod_men == cod_men)
    q = q.where(EscaneoImileOffload.fecha == (fecha or date.today()))
    q = q.order_by(EscaneoImileOffload.fecha_creacion.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/status", response_model=ImileStatus)
async def status(_=_auth):
    if not imile_automation.session_file_exists():
        return ImileStatus(
            sesion_configurada=False,
            conectado=False,
            detalle="No se ha configurado la sesión de iMile (ejecutar imile_login_setup.py)",
        )
    return ImileStatus(sesion_configurada=True, conectado=True)


@router.post("/", response_model=EscaneoImileOffloadRead, status_code=201)
async def registrar_escaneo(
    body: EscaneoImileOffloadCreate, db: AsyncSession = Depends(get_db), _=_auth
):
    try:
        resultado = await imile_automation.scan(body.serial)
    except ImileSessionExpiredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    escaneo = EscaneoImileOffload(
        fecha=date.today(),
        cod_men=body.cod_men,
        nombre_mensajero=body.nombre_mensajero,
        serial=body.serial,
        resultado=resultado.resultado.value,
        detalle=resultado.detalle,
    )
    db.add(escaneo)
    await db.commit()
    await db.refresh(escaneo)

    if resultado.resultado == ScanResultado.ERROR:
        raise HTTPException(
            status_code=422,
            detail=resultado.detalle or "iMile rechazó el serial",
        )

    return escaneo
