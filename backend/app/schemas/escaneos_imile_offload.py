from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EscaneoImileOffloadCreate(BaseModel):
    serial: str = Field(min_length=1, max_length=50)
    cod_men: str = Field(min_length=4, max_length=4)
    nombre_mensajero: str


class EscaneoImileOffloadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha: date
    cod_men: str
    nombre_mensajero: str
    serial: str
    resultado: str
    detalle: str | None = None
    fecha_creacion: datetime | None = None


class ImileStatus(BaseModel):
    sesion_configurada: bool
    conectado: bool
    detalle: str | None = None
