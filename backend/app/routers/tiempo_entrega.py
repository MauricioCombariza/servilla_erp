from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.tiempo_entrega import TiempoEntregaResponse
from app.services import tiempo_entrega_service as svc
from app.services.excel_utils import XLSX_MEDIA_TYPE

router = APIRouter(prefix="/api/tiempo-entrega", tags=["tiempo-entrega"])
_auth = Depends(require_page("tiempo_entrega"))

_MAX_DIAS = 366


def _validar(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise HTTPException(status_code=400, detail="La fecha final es anterior a la inicial")
    if (hasta - desde).days > _MAX_DIAS:
        raise HTTPException(status_code=400, detail="El rango no puede pasar de un año")


@router.get("", response_model=TiempoEntregaResponse)
async def listar(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    _validar(desde, hasta)
    guias = await svc.listar(db, desde, hasta)
    return TiempoEntregaResponse(
        desde=desde, hasta=hasta, ans_horas=svc.ANS_HORAS, descuento_horas=svc.DESCUENTO_HORAS,
        descuento_reprogramacion_horas=svc.DESCUENTO_REPROGRAMACION_HORAS,
        resumen=svc.resumir(guias), guias=guias,
    )


@router.get("/excel")
async def excel(
    desde: date = Query(...),
    hasta: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    _validar(desde, hasta)
    guias = await svc.listar(db, desde, hasta)
    contenido = svc.construir_excel(guias, desde, hasta)
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition":
                 f'attachment; filename="tiempo_entrega_{desde.isoformat()}_{hasta.isoformat()}.xlsx"'},
    )
