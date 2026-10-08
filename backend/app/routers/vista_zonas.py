from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.vista_zonas import EnlaceVistaRead, PaquetesNuevosRead
from app.services.vista_zonas_service import (
    EnlaceInvalidoError,
    obtener_o_crear_enlace,
    paquetes_nuevos,
    validar_enlace,
    zonas_disponibles,
)

router = APIRouter(prefix="/api/escaneo-vista", tags=["escaneo-vista"])
_auth = Depends(require_page("escaneo_tulas"))


@router.post("/enlace", response_model=EnlaceVistaRead)
async def enlace(db: AsyncSession = Depends(get_db), usuario: dict = _auth):
    """Quien escanea obtiene el enlace del día para compartir (se crea la primera vez)."""
    e = await obtener_o_crear_enlace(db, usuario["username"])
    return EnlaceVistaRead(token=e.token, fecha=e.fecha, expira=e.expira, ruta=f"/ver-zonas/{e.token}")


# ── Sin sesión: solo con el enlace del día ────────────────────────────────────

async def _enlace_valido(token: str, db: AsyncSession):
    try:
        return await validar_enlace(db, token)
    except EnlaceInvalidoError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{token}/zonas", response_model=list[str])
async def zonas(token: str, db: AsyncSession = Depends(get_db)):
    await _enlace_valido(token, db)
    return await zonas_disponibles(db)


@router.get("/{token}/paquetes", response_model=PaquetesNuevosRead)
async def paquetes(
    token: str,
    zonas: str = Query("", description="Zonas elegidas separadas por coma, ej. 60_1,60_2"),
    desde: int = Query(0, ge=0, description="ultimo_id de la consulta anterior"),
    db: AsyncSession = Depends(get_db),
):
    e = await _enlace_valido(token, db)
    elegidas = {z.strip() for z in zonas.split(",") if z.strip()}
    r = await paquetes_nuevos(db, e, elegidas, desde)
    return PaquetesNuevosRead(paquetes=[asdict(p) for p in r.paquetes], ultimo_id=r.ultimo_id)
