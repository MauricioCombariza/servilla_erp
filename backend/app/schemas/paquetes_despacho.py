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
    devoluciones: int  # paquetes que no caen en ninguna zona específica


class CorregirDireccionRequest(BaseModel):
    direccion: str = Field(min_length=1)


class DestinoPaquete(BaseModel):
    """Lo que se muestra al escanear un paquete (Paso 2.6)."""
    serial: str
    ultimos_4: str
    en_tabla: bool
    direccion: str | None = None
    direccion_estandarizada: str | None = None  # más corta y legible en el celular
    localidad: str | None = None
    zona: str | None = None
    fuera_de_zona: bool = False
    aviso: str | None = None  # "No está en la tabla" | "Fuera de zona"
