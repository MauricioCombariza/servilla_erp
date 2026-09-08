from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DevolucionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    serial: str
    nombre: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    localidad: str | None = None
    estado: str
    fecha_carga: datetime
    fecha_actualizacion: datetime


class DevolucionCreate(BaseModel):
    serial: str = Field(min_length=1, max_length=50)
    nombre: str | None = Field(default=None, max_length=255)
    telefono: str | None = Field(default=None, max_length=20)
    direccion: str | None = None
    localidad: str | None = Field(default=None, max_length=100)
    estado: str = Field(default="transito", min_length=1, max_length=30)


class DevolucionEstadoUpdate(BaseModel):
    estado: str = Field(min_length=1, max_length=30)


class CargaMasivaDevolucionesResult(BaseModel):
    total_filas: int
    nuevas: int
    actualizadas: int
    errores: list[str]


class DevolucionDocumentoItem(BaseModel):
    serial: str
    nombre: str | None = None
    direccion: str | None = None
    localidad: str | None = None


class DevolucionDocumentoRequest(BaseModel):
    items: list[DevolucionDocumentoItem] = Field(min_length=1)


class VerificarSerialesRequest(BaseModel):
    seriales: list[str] = Field(min_length=1, max_length=500)


class SerialVerificado(BaseModel):
    serial: str
    clasificacion: Literal["entrega", "devolucion", "ninguna"]
    fuente: Literal["seriales_gestion", "devoluciones"] | None = None
    estado_detalle: str | None = None
    cliente: str | None = None
    planilla: str | None = None
    cod_men: str | None = None
    fecha: date | None = None


class VerificarSerialesResult(BaseModel):
    items: list[SerialVerificado]
    total_devoluciones: int
    total_entregas: int
    total_ninguna: int
