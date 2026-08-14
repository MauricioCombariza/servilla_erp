from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class EscaneoCarrytCreate(BaseModel):
    serial: str = Field(min_length=1, max_length=50)
    cod_men: str = Field(min_length=4, max_length=4)
    nombre_mensajero: str


class EscaneoCarrytRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente: str
    fecha: date
    cod_men: str
    nombre_mensajero: str
    serial: str
    fecha_creacion: datetime | None = None
