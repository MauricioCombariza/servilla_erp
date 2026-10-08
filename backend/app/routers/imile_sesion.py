from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_page
from app.schemas.imile_sesion import EstadoSesionImileRead
from app.services.imile_sesion import (
    ImileCredencialesFaltantesError,
    ImileIdiomaError,
    ImileLoginError,
    imile_sesion,
)

router = APIRouter(prefix="/api/imile-sesion", tags=["imile-sesion"])
_auth = Depends(require_page("paquetes_despacho"))


@router.get("/estado", response_model=EstadoSesionImileRead)
async def estado(_=_auth):
    return asdict(await imile_sesion.estado())


@router.post("/conectar", response_model=EstadoSesionImileRead)
async def conectar(forzar: bool = False, _=_auth):
    """Abre la sesión de iMile (o la reabre con forzar=true) y la deja en español."""
    try:
        return asdict(await imile_sesion.conectar(forzar=forzar))
    except ImileCredencialesFaltantesError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (ImileLoginError, ImileIdiomaError) as e:
        raise HTTPException(status_code=502, detail=str(e))
