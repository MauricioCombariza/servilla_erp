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


class DevolucionEstadoUpdate(BaseModel):
    estado: str = Field(min_length=1, max_length=30)


class CargaMasivaDevolucionesResult(BaseModel):
    total_filas: int
    nuevas: int
    actualizadas: int
    errores: list[str]
