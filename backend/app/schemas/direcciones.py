from typing import Literal

from pydantic import BaseModel


class AjusteDireccionesResult(BaseModel):
    total_filas: int
    total_columnas: int
    col_direccion: int
    filas: list[list[str]]


class DescargarDireccionesRequest(BaseModel):
    cliente: Literal["leonisa", "vehigrupo"]
    nombre_archivo: str
    filas: list[list[str]]
