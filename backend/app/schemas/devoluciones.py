from datetime import datetime

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
