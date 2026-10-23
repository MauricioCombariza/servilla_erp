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
    nombre_imile: str | None = None  # si en iMile aparece con otro nombre (Paso 3.3)


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
    imile_estado: str | None = None  # Paso 3.3: ok | repetido | bloqueado | error | sin_confirmar; None = sin mandar
    imile_mensaje: str | None = None


class TotalMensajeroRead(BaseModel):
    codigo: str
    nombre: str
    zonas: list[str]
    paquetes: int  # paquetes del día: sus zonas + reasignados a él
    reasignados: int


class NombreImileRequest(BaseModel):
    nombre_imile: str | None = None  # vacío: se busca en iMile con el nombre del ERP


class EnvioImileRead(BaseModel):
    nombre_imile: str  # con el que se busca en iMile
    total: int
    hechos: int
    asignados: int
    fallidos: int
    en_curso: bool
    error: str | None
