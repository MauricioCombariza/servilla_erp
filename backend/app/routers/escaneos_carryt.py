from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.models.escaneos_carryt import EscaneoCarryt
from app.schemas.escaneos_carryt import (
    EscaneoCarrytCreate,
    EscaneoCarrytRead,
    EscaneoCarrytReasignar,
    normalizar_serial,
)
from app.services.escaneos_carryt_service import (
    construir_excel_dia,
    construir_excel_rango,
    construir_excel_rutas_unicas,
    filtrar_rutas_unicas,
    get_escaneos_del_dia,
    get_escaneos_rango,
)
from app.services.excel_utils import XLSX_MEDIA_TYPE

router = APIRouter(prefix="/api/escaneos-carryt", tags=["escaneos-carryt"])
_auth = Depends(require_page("escaneo_carryt"))
_auth_reporte = Depends(require_page("escaneo_carryt"))


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


@router.get("/buscar", response_model=EscaneoCarrytRead)
async def buscar_por_serial(
    serial: str, db: AsyncSession = Depends(get_db), _=_auth
):
    serial_norm = normalizar_serial(serial)
    result = await db.execute(
        select(EscaneoCarryt).where(EscaneoCarryt.serial == serial_norm)
    )
    escaneo = result.scalar_one_or_none()
    if escaneo is None:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró ningún paquete escaneado con el serial {serial_norm}",
        )
    return escaneo


@router.patch("/{escaneo_id}", response_model=EscaneoCarrytRead)
async def reasignar_mensajero(
    escaneo_id: int,
    body: EscaneoCarrytReasignar,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(
        select(EscaneoCarryt).where(EscaneoCarryt.id == escaneo_id)
    )
    escaneo = result.scalar_one_or_none()
    if escaneo is None:
        raise HTTPException(status_code=404, detail="Escaneo no encontrado")
    escaneo.cod_men = body.cod_men
    escaneo.nombre_mensajero = body.nombre_mensajero
    await db.commit()
    await db.refresh(escaneo)
    return escaneo


@router.get("/excel-dia")
async def descargar_excel_dia(
    fecha: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth_reporte,
):
    dia = fecha or date.today()
    escaneos = await get_escaneos_del_dia(db, dia)
    if not escaneos:
        raise HTTPException(status_code=404, detail="No hay paquetes escaneados para esa fecha.")
    contenido = construir_excel_dia(dia, escaneos)
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="carryt_{dia.isoformat()}.xlsx"'},
    )


@router.get("/excel-rutas-unicas")
async def descargar_excel_rutas_unicas(
    fecha: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth_reporte,
):
    dia = fecha or date.today()
    escaneos = await get_escaneos_del_dia(db, dia)
    unicas = filtrar_rutas_unicas(escaneos)
    if not unicas:
        raise HTTPException(status_code=404, detail="No hay rutas únicas para esa fecha.")
    contenido = construir_excel_rutas_unicas(dia, unicas)
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="rutas_unicas_{dia.isoformat()}.xlsx"'},
    )


@router.get("/excel-rango")
async def descargar_excel_rango(
    fecha_desde: date,
    fecha_hasta: date,
    db: AsyncSession = Depends(get_db),
    _=_auth_reporte,
):
    if fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=400, detail="La fecha inicial debe ser anterior o igual a la final."
        )
    escaneos = await get_escaneos_rango(db, fecha_desde, fecha_hasta)
    if not escaneos:
        raise HTTPException(status_code=404, detail="No hay paquetes escaneados en ese rango de fechas.")
    contenido = construir_excel_rango(fecha_desde, fecha_hasta, escaneos)
    return Response(
        content=contenido,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f'attachment; filename="carryt_{fecha_desde.isoformat()}_a_{fecha_hasta.isoformat()}.xlsx"'
            )
        },
    )
