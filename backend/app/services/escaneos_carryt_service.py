from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escaneos_carryt import EscaneoCarryt
from app.services.excel_utils import construir_excel

COLUMNAS_EXCEL_DIA = ["serial", "cod_men", "nombre_mensajero"]
COLUMNAS_EXCEL_RUTAS_UNICAS = ["serial", "nombre_mensajero"]
COLUMNAS_EXCEL_RANGO = ["fecha", "serial", "cod_men", "nombre_mensajero"]


async def get_escaneos_del_dia(db: AsyncSession, fecha: date | None = None) -> list[EscaneoCarryt]:
    dia = fecha or date.today()
    result = await db.execute(
        select(EscaneoCarryt)
        .where(EscaneoCarryt.fecha == dia)
        .order_by(EscaneoCarryt.nombre_mensajero, EscaneoCarryt.fecha_creacion)
    )
    return list(result.scalars().all())


async def get_escaneos_rango(db: AsyncSession, desde: date, hasta: date) -> list[EscaneoCarryt]:
    result = await db.execute(
        select(EscaneoCarryt)
        .where(EscaneoCarryt.fecha.between(desde, hasta))
        .order_by(EscaneoCarryt.fecha, EscaneoCarryt.nombre_mensajero, EscaneoCarryt.fecha_creacion)
    )
    return list(result.scalars().all())


def filtrar_rutas_unicas(escaneos: list[EscaneoCarryt]) -> list[EscaneoCarryt]:
    """Mensajeros que llevan un solo paquete ese día."""
    conteo: dict[str, int] = defaultdict(int)
    for e in escaneos:
        conteo[e.cod_men] += 1
    return [e for e in escaneos if conteo[e.cod_men] == 1]


def _fila(e: EscaneoCarryt) -> dict:
    return {"serial": e.serial, "cod_men": e.cod_men, "nombre_mensajero": e.nombre_mensajero}


def _fila_con_fecha(e: EscaneoCarryt) -> dict:
    return {
        "fecha": e.fecha.isoformat(),
        "serial": e.serial,
        "cod_men": e.cod_men,
        "nombre_mensajero": e.nombre_mensajero,
    }


def construir_excel_dia(fecha: date, escaneos: list[EscaneoCarryt]) -> bytes:
    titulo = f"Carryt - Paquetes del {fecha.isoformat()}"
    filas = [_fila(e) for e in escaneos]
    widths = [20, 10, 30]
    return construir_excel(titulo, COLUMNAS_EXCEL_DIA, filas, widths)


def construir_excel_rutas_unicas(fecha: date, escaneos: list[EscaneoCarryt]) -> bytes:
    titulo = f"Carryt - Rutas únicas {fecha.isoformat()}"
    filas = [_fila(e) for e in escaneos]
    widths = [20, 30]
    return construir_excel(titulo, COLUMNAS_EXCEL_RUTAS_UNICAS, filas, widths)


def construir_excel_rango(desde: date, hasta: date, escaneos: list[EscaneoCarryt]) -> bytes:
    titulo = f"Carryt - Envíos {desde.isoformat()} a {hasta.isoformat()}"
    filas = [_fila_con_fecha(e) for e in escaneos]
    widths = [12, 20, 10, 30]
    return construir_excel(titulo, COLUMNAS_EXCEL_RANGO, filas, widths)
