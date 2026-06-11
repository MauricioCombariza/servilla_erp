from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DetalleTransporteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factura_id: int
    orden_id: int | None
    cantidad_sobres: int
    costo_asignado: float
    numero_orden: str | None = None
    cliente_nombre: str | None = None


class DetalleTransporteCreate(BaseModel):
    orden_id: int
    cantidad_sobres: int


class FacturaTransporteCreate(BaseModel):
    numero_factura: str
    fecha_factura: date
    courrier_id: int
    monto_total: float
    total_sobres: int = 0
    fecha_vencimiento: date | None = None
    observaciones: str | None = None


class FacturaTransporteUpdate(BaseModel):
    numero_factura: str | None = None
    fecha_factura: date | None = None
    courrier_id: int | None = None
    monto_total: float | None = None
    total_sobres: int | None = None
    fecha_vencimiento: date | None = None
    estado: str | None = None
    monto_pagado: float | None = None
    observaciones: str | None = None


class FacturaTransporteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero_factura: str
    fecha_factura: date
    courrier_id: int
    courrier: dict
    monto_total: float
    total_sobres: int
    monto_pagado: float
    estado: str
    fecha_vencimiento: date | None
    observaciones: str | None
    fecha_creacion: datetime | None
    detalles: list[DetalleTransporteRead]


class PagarTransporteRequest(BaseModel):
    monto_pago: float
    referencia: str | None = None
    observaciones: str | None = None


class PrefacturaCourier(BaseModel):
    cod_mensajero: str
    mensajero_id: int | None
    nombre_completo: str | None
    periodo_mes: int
    periodo_anio: int
    total_planillas: int
    total_local: int
    total_nacional: int
    total_seriales: int
    precio_local_promedio: float
    precio_nacional_promedio: float
    monto_estimado: float


class ResumenCourierReal(BaseModel):
    courrier: str
    total_facturas: int
    monto_total: float
    monto_pagado: float
    pendiente: float
    total_sobres: int
    costo_por_sobre: float


class ResumenClienteFlete(BaseModel):
    cliente: str
    total_sobres: int
    costo_total: float
    costo_por_sobre: float
