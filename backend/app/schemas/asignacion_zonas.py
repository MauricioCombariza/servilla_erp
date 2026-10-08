from datetime import date

from pydantic import BaseModel, Field


class MensajeroRead(BaseModel):
    codigo: str
    nombre: str


class AsignarZonasRequest(BaseModel):
    zonas: list[str]
    fecha: date | None = None  # por defecto hoy (Bogotá)
    reasignar: bool = False


class ZonasMensajeroRead(BaseModel):
    codigo: str
    nombre: str
    fecha: date
    zonas: list[str]


class ZonaDelDiaRead(BaseModel):
    zona: str
    paquetes_leidos: int
    mensajero: MensajeroRead | None


class AsignarSerialRequest(BaseModel):
    serial: str = Field(min_length=1)
    fecha: date | None = None  # por defecto hoy (Bogotá)


class AsignacionSerialRead(BaseModel):
    serial: str
    ultimos_4: str
    zona: str | None
    mensajero_anterior: MensajeroRead | None  # a quién lo tenía (por zona o por serial)
    ya_era_suyo: bool


class SerialDelMensajeroRead(BaseModel):
    serial: str
    ultimos_4: str
    zona: str | None
    origen: str  # "zona" | "serial" (reasignado uno a uno)
