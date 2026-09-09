"""Carga masiva de devoluciones desde Excel.

Formato esperado (columnas exactas): serial, nombre, telefono, direccion, localidad.
Un registro por serial: recargar el mismo serial actualiza los datos de contacto
(nombre/telefono/direccion/localidad), pero nunca toca `estado` — el Excel de
devoluciones no trae esa columna, así que el UPSERT ni la incluye en el SET. El
estado solo cambia vía el endpoint PATCH (edición manual desde la UI).
"""

from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.devoluciones import Devolucion
from app.schemas.devoluciones import CargaMasivaDevolucionesResult
from app.services.excel_utils import construir_excel

logger = logging.getLogger(__name__)

COLUMNAS_EXCEL_REPORTE_DEVOLUCION = ["N°", "Serial", "Nombre", "Dirección", "Localidad"]

COLUMNAS_REQUERIDAS = ["serial", "nombre", "telefono", "direccion", "localidad"]

# Límites de columna en el modelo Devolucion (backend/app/models/devoluciones.py):
# validar aquí evita que un dato demasiado largo tumbe toda la carga con un
# DataError de Postgres sin capturar (500 opaco); en cambio se reporta la fila
# puntual en `errores` y se sigue con el resto del archivo.
_LIMITES = {"serial": 50, "nombre": 255, "telefono": 20, "localidad": 100}

# Variantes de texto que un Excel puede traer para representar "sin dato": el NaN
# real de pandas (celda ausente) o el texto literal "na"/"n/a"/"nan"
# (case-insensitive). Mismo criterio que ordenes_service._limpiar_texto, para
# evitar guardar el texto literal "nan" en columnas de contacto.
_TEXTOS_VACIOS = {"na", "n/a", "nan"}


def _limpiar_texto(serie: pd.Series) -> pd.Series:
    limpio = serie.fillna("").astype(str).str.strip()
    return limpio.mask(limpio.str.lower().isin(_TEXTOS_VACIOS), "")


_UPSERT = text("""
    INSERT INTO devoluciones (serial, nombre, telefono, direccion, localidad)
    VALUES (:serial, :nombre, :telefono, :direccion, :localidad)
    ON CONFLICT (serial) DO UPDATE SET
        nombre              = EXCLUDED.nombre,
        telefono            = EXCLUDED.telefono,
        direccion           = EXCLUDED.direccion,
        localidad           = EXCLUDED.localidad,
        fecha_actualizacion = CURRENT_TIMESTAMP
    RETURNING (xmax = 0) AS es_nuevo
""")


async def procesar_excel_devoluciones(
    contenido: bytes, db: AsyncSession
) -> CargaMasivaDevolucionesResult:
    try:
        df = pd.read_excel(io.BytesIO(contenido), dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo Excel: {e}")

    df.columns = [str(c).strip().lower() for c in df.columns]
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"Columnas faltantes: {', '.join(faltantes)}. "
            f"Se necesitan: {', '.join(COLUMNAS_REQUERIDAS)}."
        )

    for col in COLUMNAS_REQUERIDAS:
        df[col] = _limpiar_texto(df[col])

    total_filas = len(df)
    errores: list[str] = []
    nuevas = actualizadas = 0

    for fila in df.itertuples(index=False):
        if not fila.serial:
            errores.append("Fila sin serial, ignorada")
            continue

        excede = [
            f"{campo} ({len(getattr(fila, campo))}/{limite})"
            for campo, limite in _LIMITES.items()
            if len(getattr(fila, campo)) > limite
        ]
        if excede:
            errores.append(
                f"Serial {fila.serial}: campo(s) demasiado largo(s): {', '.join(excede)}"
            )
            continue

        params = {
            "serial": fila.serial,
            "nombre": fila.nombre or None,
            "telefono": fila.telefono or None,
            "direccion": fila.direccion or None,
            "localidad": fila.localidad or None,
        }
        try:
            await db.execute(text("SAVEPOINT sp_devolucion"))
            result = await db.execute(_UPSERT, params)
            await db.execute(text("RELEASE SAVEPOINT sp_devolucion"))
        except Exception as e:
            await db.execute(text("ROLLBACK TO SAVEPOINT sp_devolucion"))
            logger.error("Error al guardar devolución serial=%s: %s", fila.serial, e)
            errores.append(f"Serial {fila.serial}: error al guardar ({e})")
            continue

        es_nuevo = result.scalar_one()
        if es_nuevo:
            nuevas += 1
        else:
            actualizadas += 1

    await db.commit()

    return CargaMasivaDevolucionesResult(
        total_filas=total_filas,
        nuevas=nuevas,
        actualizadas=actualizadas,
        errores=errores,
    )


async def get_devoluciones_del_dia(
    db: AsyncSession, fecha: date, orden_desc: bool = False
) -> list[Devolucion]:
    """Devoluciones confirmadas ('devolucion') ese día, según fecha_escaneo
    (no fecha_actualizacion, que también se pisa al recargar el Excel).
    orden_desc=True para hidratar la pantalla de escaneo (más reciente
    primero); orden ascendente (default) para los reportes (PDF/Word/Excel)."""
    orden = Devolucion.fecha_escaneo.desc() if orden_desc else Devolucion.fecha_escaneo.asc()
    query = (
        select(Devolucion)
        .where(Devolucion.estado == "devolucion", func.date(Devolucion.fecha_escaneo) == fecha)
        .order_by(orden)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


def construir_excel_reporte_devolucion(fecha: date, devoluciones: list[Devolucion]) -> bytes:
    titulo = f"Acta de devolución - {fecha.isoformat()}"
    filas = [
        {
            "N°": i,
            "Serial": d.serial,
            "Nombre": d.nombre or "",
            "Dirección": d.direccion or "",
            "Localidad": d.localidad or "",
        }
        for i, d in enumerate(devoluciones, start=1)
    ]
    widths = [6, 20, 28, 40, 20]
    return construir_excel(titulo, COLUMNAS_EXCEL_REPORTE_DEVOLUCION, filas, widths)
