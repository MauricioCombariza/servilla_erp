from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.paquetes_estancados import PaquetesEstancadosResponse
from app.services import paquetes_estancados_service as svc
from app.services.excel_utils import XLSX_MEDIA_TYPE

router = APIRouter(prefix="/api/paquetes-estancados", tags=["paquetes-estancados"])
_auth = Depends(require_page("paquetes_estancados"))


@router.get("", response_model=PaquetesEstancadosResponse)
async def listar(
    dias_min: int = Query(default=2, ge=0, le=60),
    zona: str | None = Query(default=None),
    codigo: str | None = Query(default=None, description="Código del mensajero; vacío = sin asignar"),
    incluir_devoluciones: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    hoy = svc.hoy_bogota()
    listado = await svc.listar_estancados(db, dias_min, zona, codigo, hoy, incluir_devoluciones)
    paquetes = listado.paquetes
    return PaquetesEstancadosResponse(
        corte=hoy,
        dias_min=dias_min,
        total=len(paquetes),
        devoluciones_ocultas=listado.devoluciones_ocultas,
        paquetes=paquetes,
        por_mensajero=svc.por_mensajero(paquetes),
        por_zona=svc.por_zona(paquetes),
    )


@router.get("/excel")
async def excel(
    dias_min: int = Query(default=2, ge=0, le=60),
    zona: str | None = Query(default=None),
    codigo: str | None = Query(default=None),
    incluir_devoluciones: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    hoy = svc.hoy_bogota()
    paquetes = (await svc.listar_estancados(db, dias_min, zona, codigo, hoy, incluir_devoluciones)).paquetes
    contenido = svc.construir_excel(paquetes, dias_min, hoy)
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="paquetes_estancados_{hoy.isoformat()}.xlsx"'},
    )
