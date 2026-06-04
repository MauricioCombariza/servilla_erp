from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class GastoAdminBase(BaseModel):
    fecha: date
    categoria: str
    descripcion: str
    monto: float
    proveedor: str | None = None
    numero_factura: str | None = None
    estado: str = "pendiente"
    fecha_pago: date | None = None
    observaciones: str | None = None


class GastoAdminCreate(GastoAdminBase):
    pass


class GastoAdminUpdate(BaseModel):
    fecha: date | None = None
    categoria: str | None = None
    descripcion: str | None = None
    monto: float | None = None
    proveedor: str | None = None
    numero_factura: str | None = None
    estado: str | None = None
    fecha_pago: date | None = None
    observaciones: str | None = None


class GastoAdminRead(GastoAdminBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fecha_creacion: datetime | None = None


class GastoAdminResumen(BaseModel):
    categoria: str
    total: float
    cantidad: int


class GastoFijoBase(BaseModel):
    categoria: str
    descripcion: str
    monto: float
    dia_pago: int = 1
    observaciones: str | None = None


class GastoFijoCreate(GastoFijoBase):
    pass


class GastoFijoUpdate(BaseModel):
    categoria: str | None = None
    descripcion: str | None = None
    monto: float | None = None
    dia_pago: int | None = None
    activo: bool | None = None
    observaciones: str | None = None


class PagoGastoFijoCreate(BaseModel):
    mes: int
    anio: int
    monto_pagado: float
    fecha_pago: date
    observaciones: str | None = None


class PagoGastoFijoRead(PagoGastoFijoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    gasto_fijo_id: int
    created_at: datetime | None = None


class GastoFijoRead(GastoFijoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    created_at: datetime | None = None
    pagos: list[PagoGastoFijoRead] = []
