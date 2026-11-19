import re
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Guarda contra pegar una clave en un campo de texto ("clave: xxx", "password=xxx")
_PARECE_CLAVE = re.compile(r"(clave|contrase[ñn]a|password|passwd|pwd)\s*[:=]", re.IGNORECASE)


def _sin_claves(v: str | None) -> str | None:
    if v and _PARECE_CLAVE.search(v):
        raise ValueError("No escribas claves aquí: la clave va solo en el sobre sellado de la bóveda")
    return v


class ClaveExternaBase(BaseModel):
    aplicacion: str = Field(min_length=1, max_length=100)
    sistema: str | None = Field(default=None, max_length=100)
    usuario: str = Field(min_length=1, max_length=100)
    categoria: str
    periodicidad_dias: int | None = Field(default=None, ge=1, le=730)
    custodio_1: str | None = Field(default=None, max_length=100)
    custodio_2: str | None = Field(default=None, max_length=100)
    sobre_no: str | None = Field(default=None, max_length=20)
    cofre_no: str | None = Field(default=None, max_length=20)
    ambiente: str | None = Field(default=None, max_length=100)
    notas: str | None = Field(default=None, max_length=500)

    @field_validator("notas")
    @classmethod
    def validar_sin_claves_notas(cls, v: str | None) -> str | None:
        return _sin_claves(v)


class ClaveExternaCreate(ClaveExternaBase):
    ultimo_cambio: date | None = None


class ClaveExternaUpdate(BaseModel):
    aplicacion: str | None = Field(default=None, min_length=1, max_length=100)
    sistema: str | None = Field(default=None, max_length=100)
    usuario: str | None = Field(default=None, min_length=1, max_length=100)
    categoria: str | None = None
    periodicidad_dias: int | None = Field(default=None, ge=1, le=730)
    custodio_1: str | None = Field(default=None, max_length=100)
    custodio_2: str | None = Field(default=None, max_length=100)
    sobre_no: str | None = Field(default=None, max_length=20)
    cofre_no: str | None = Field(default=None, max_length=20)
    ambiente: str | None = Field(default=None, max_length=100)
    notas: str | None = Field(default=None, max_length=500)
    activo: bool | None = None

    @field_validator("notas")
    @classmethod
    def validar_sin_claves_notas(cls, v: str | None) -> str | None:
        return _sin_claves(v)


class ClaveExternaRead(ClaveExternaBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ultimo_cambio: date | None
    activo: bool
    # Calculados (app/routers/claves_externas.py)
    periodicidad_efectiva: int = 0
    vence_en: date | None = None
    dias_restantes: int | None = None
    estado: str = "sin_registro"  # al_dia | por_vencer | vencida | sin_registro


class CambioCreate(BaseModel):
    fecha: date
    responsable: str = Field(min_length=1, max_length=100)
    sobre_no: str | None = Field(default=None, max_length=20)
    observacion: str | None = Field(default=None, max_length=500)

    @field_validator("observacion")
    @classmethod
    def validar_sin_claves_observacion(cls, v: str | None) -> str | None:
        return _sin_claves(v)


class CambioRead(CambioCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clave_id: int


class Categoria(BaseModel):
    clave: str
    nombre: str
    dias: int


class Resumen(BaseModel):
    vencidas: int
    por_vencer: int
    sin_registro: int
