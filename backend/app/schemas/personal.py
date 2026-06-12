from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonalCiudadBase(BaseModel):
    ciudad_id: int
    tarifa_entrega: float | None = None
    tarifa_devolucion: float | None = None
    vigencia_desde: date
    vigencia_hasta: date | None = None


class PersonalCiudadCreate(PersonalCiudadBase):
    pass


class PersonalCiudadUpdate(BaseModel):
    tarifa_entrega: float | None = None
    tarifa_devolucion: float | None = None
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    activo: bool | None = None


class PersonalCiudadRead(PersonalCiudadBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    personal_id: int
    activo: bool


class PersonalBase(BaseModel):
    codigo: str = Field(min_length=4, max_length=4)
    nombre_completo: str
    identificacion: str
    telefono: str | None = None
    email: str | None = None
    tipo_personal: str = Field(
        pattern="^(mensajero|alistamiento|conductor|courier_externo|transportadora)$"
    )
    banco: str | None = None
    numero_cuenta: str | None = None
    tipo_cuenta: str | None = Field(default=None, pattern="^(ahorros|corriente)$")
    dia_pago: int = 8
    observaciones: str | None = None
    fecha_ingreso: date | None = None
    precio_local: float | None = None
    precio_nacional: float | None = None


class PersonalCreate(PersonalBase):
    pass


class PersonalUpdate(BaseModel):
    nombre_completo: str | None = None
    tipo_personal: str | None = None
    telefono: str | None = None
    email: str | None = None
    banco: str | None = None
    numero_cuenta: str | None = None
    tipo_cuenta: str | None = None
    dia_pago: int | None = None
    observaciones: str | None = None
    fecha_ingreso: date | None = None
    precio_local: float | None = None
    precio_nacional: float | None = None
    activo: bool | None = None


class PersonalRead(PersonalBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    fecha_creacion: datetime | None = None
    fecha_modificacion: datetime | None = None


class PersonalWithCiudades(PersonalRead):
    ciudades: list[PersonalCiudadRead] = []


class CiudadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    departamento: str | None = None
    codigo: str | None = None
    es_bogota: bool
    ambito: str
    activa: bool
