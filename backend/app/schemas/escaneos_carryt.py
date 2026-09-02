import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EscaneoCarrytCreate(BaseModel):
    serial: str = Field(min_length=1, max_length=50)
    cod_men: str = Field(min_length=4, max_length=4)
    nombre_mensajero: str

    @field_validator("serial")
    @classmethod
    def normalizar_serial(cls, v: str) -> str:
        v = v.strip()
        match = re.match(r"^(\d+)", v)
        return match.group(1) if match else v


class EscaneoCarrytRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cliente: str
    fecha: date
    cod_men: str
    nombre_mensajero: str
    serial: str
    fecha_creacion: datetime | None = None
