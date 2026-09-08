"""Clasificación de seriales como devolución, entrega o ninguna.

Prioridad: seriales_gestion.tipo_gestion (lo que el mensajero realmente hizo)
y, si el serial no está ahí, se cae al estado registrado en devoluciones.
"""

from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.devoluciones import Devolucion
from app.models.gestiones import SerialGestion
from app.schemas.devoluciones import SerialVerificado

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

CLASIFICACION_LABELS = {
    "entrega": "Entrega",
    "devolucion": "Devolución",
    "ninguna": "No encontrado",
}

# Mismo criterio que devoluciones_service._limpiar_texto para no confundir el
# texto literal "nan"/"na"/"n/a" de un Excel con un serial real.
_TEXTOS_VACIOS = {"na", "n/a", "nan"}


async def clasificar_seriales(seriales: list[str], db: AsyncSession) -> list[SerialVerificado]:
    """Clasifica una lista de seriales (sin duplicados) preservando su orden."""
    sg_result = await db.execute(select(SerialGestion).where(SerialGestion.serial.in_(seriales)))
    por_gestion: dict[str, SerialGestion] = {sg.serial: sg for sg in sg_result.scalars().all()}

    pendientes = [s for s in seriales if s not in por_gestion]
    por_devolucion: dict[str, Devolucion] = {}
    if pendientes:
        dev_result = await db.execute(select(Devolucion).where(Devolucion.serial.in_(pendientes)))
        por_devolucion = {d.serial: d for d in dev_result.scalars().all()}

    items: list[SerialVerificado] = []
    for serial in seriales:
        sg = por_gestion.get(serial)
        if sg is not None:
            clasificacion = "entrega" if sg.tipo_gestion == "Entrega" else "devolucion"
            items.append(
                SerialVerificado(
                    serial=serial,
                    clasificacion=clasificacion,
                    fuente="seriales_gestion",
                    estado_detalle=sg.tipo_gestion,
                    cliente=sg.cliente.nombre_empresa if sg.cliente else None,
                    planilla=sg.planilla,
                    cod_men=sg.cod_men,
                    fecha=sg.f_esc,
                )
            )
            continue

        d = por_devolucion.get(serial)
        if d is not None:
            if d.estado == "devolucion":
                clasificacion = "devolucion"
            elif d.estado == "entregado":
                clasificacion = "entrega"
            else:
                clasificacion = "ninguna"
            items.append(
                SerialVerificado(
                    serial=serial,
                    clasificacion=clasificacion,
                    fuente="devoluciones",
                    estado_detalle=d.estado,
                    cliente=d.nombre,
                    planilla=None,
                    cod_men=None,
                    fecha=d.fecha_actualizacion.date(),
                )
            )
            continue

        items.append(SerialVerificado(serial=serial, clasificacion="ninguna", fuente=None))

    return items


def _limpiar_serial(serie: pd.Series) -> pd.Series:
    limpio = serie.fillna("").astype(str).str.strip()
    return limpio.mask(limpio.str.lower().isin(_TEXTOS_VACIOS), "")


async def procesar_excel_verificacion(contenido: bytes, db: AsyncSession) -> bytes:
    """Lee un Excel con una columna 'serial', y devuelve el mismo archivo con
    dos columnas nuevas insertadas justo después: 'clasificacion' y
    'fecha_gestion'. Conserva el resto de columnas y el orden de las filas."""
    try:
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo Excel: {e}")

    columna_serial = next(
        (c for c in df.columns if str(c).strip().lower() == "serial"), None
    )
    if columna_serial is None:
        raise ValueError("El archivo debe tener una columna 'serial'")

    df[columna_serial] = _limpiar_serial(df[columna_serial])
    seriales_por_fila = df[columna_serial].tolist()

    seriales_unicos: list[str] = []
    vistos: set[str] = set()
    for s in seriales_por_fila:
        if s and s not in vistos:
            vistos.add(s)
            seriales_unicos.append(s)
    if not seriales_unicos:
        raise ValueError("No se encontró ningún serial en la columna 'serial'")

    items = await clasificar_seriales(seriales_unicos, db)
    por_serial = {item.serial: item for item in items}

    clasificaciones: list[str] = []
    fechas: list[str] = []
    for s in seriales_por_fila:
        item = por_serial.get(s) if s else None
        clasificaciones.append(CLASIFICACION_LABELS[item.clasificacion] if item else "")
        fechas.append(item.fecha.isoformat() if item and item.fecha else "")

    idx = df.columns.get_loc(columna_serial)
    df.insert(idx + 1, "clasificacion", clasificaciones)
    df.insert(idx + 2, "fecha_gestion", fechas)

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()
