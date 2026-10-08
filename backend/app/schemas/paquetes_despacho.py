from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PaqueteDespachoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    nombre: str | None
    telefono: str | None
    direccion: str | None
    direccion_estandarizada: str | None
    codigo_postal: str | None
    localidad: str | None
    zona: str | None
    f_emi: date
    estado: str
    fecha_modificacion: datetime


class PaqueteSinSector(BaseModel):
    serial: str
    direccion: str | None


class CargaDespachoResult(BaseModel):
    archivo: str
    f_emi: date
    total: int
    creados: int
    reemplazados: int
    sin_sector: list[PaqueteSinSector]


class CorregirDireccionRequest(BaseModel):
    direccion: str = Field(min_length=1)
