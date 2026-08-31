"""Carga masiva de devoluciones desde Excel.

Formato esperado (columnas exactas): serial, nombre, telefono, direccion, localidad.
Un registro por serial: recargar el mismo serial actualiza los datos de contacto
(nombre/telefono/direccion/localidad), pero nunca toca `estado` — el Excel de
devoluciones no trae esa columna, así que el UPSERT ni la incluye en el SET. El
estado solo cambia vía el endpoint PATCH (edición manual desde la UI).
"""

from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.devoluciones import CargaMasivaDevolucionesResult

COLUMNAS_REQUERIDAS = ["serial", "nombre", "telefono", "direccion", "localidad"]

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

        result = await db.execute(
            _UPSERT,
            {
                "serial": fila.serial,
                "nombre": fila.nombre or None,
                "telefono": fila.telefono or None,
                "direccion": fila.direccion or None,
                "localidad": fila.localidad or None,
            },
        )
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
