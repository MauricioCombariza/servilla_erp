from typing import Literal

from pydantic import BaseModel


class AjusteDireccionesResult(BaseModel):
    total_filas: int
    total_columnas: int
    col_direccion: int
    col_nombre: int | None = None
    direcciones_originales: list[str]
    filas: list[list[str]]


class DescargarDireccionesRequest(BaseModel):
    cliente: Literal["leonisa", "vehigrupo"]
    nombre_archivo: str
    filas: list[list[str]]


class FilaDirNum(BaseModel):
    serial: str
    direccion: str
    direccion_ajustada: str
    dir_num: str


class AjusteDirNumResult(BaseModel):
    total_filas: int
    sin_dir_num: int
    filas: list[FilaDirNum]


class DescargarDirNumRequest(BaseModel):
    nombre_archivo: str
    filas: list[FilaDirNum]
