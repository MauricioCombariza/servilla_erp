from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.schemas.pendientes_entrega import PendientesEntregaResumen
from app.services.pendientes_entrega_service import (
    construir_excel_courier,
    get_pendientes_courier_individual,
    get_pendientes_por_personal,
    nombre_archivo_excel,
)

router = APIRouter(prefix="/api/pendientes-entrega", tags=["pendientes-entrega"])
_auth = Depends(require_role("administrador", "logistica"))

TipoPersonalPendientes = Literal["courier_externo", "mensajero"]


@router.get("/resumen", response_model=PendientesEntregaResumen)
async def get_resumen(
    tipo: TipoPersonalPendientes = Query(...),
    dias_corte: int = Query(default=60, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    personas = await get_pendientes_por_personal(db, tipo, dias_corte)
    corte_desde = (date.today() - timedelta(days=dias_corte)).isoformat()
    return PendientesEntregaResumen(tipo_personal=tipo, corte_desde=corte_desde, personas=personas)


@router.get("/{codigo}/excel")
async def descargar_excel(
    codigo: str,
    tipo: TipoPersonalPendientes = Query(...),
    dias_corte: int = Query(default=60, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    resultado = await get_pendientes_courier_individual(db, codigo, tipo, dias_corte)
    if resultado is None:
        raise HTTPException(
            status_code=404,
            detail="No se encontró personal activo con ese código y tipo.",
        )
    persona, filas = resultado
    contenido = construir_excel_courier(persona.nombre_completo, filas)
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo_excel(persona)}"'},
    )
