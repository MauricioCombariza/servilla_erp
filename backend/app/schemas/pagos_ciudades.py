from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PlanillaCalculada(BaseModel):
    planilla: str
    cod_mensajero: str
    fecha_escaner: date | None
    cantidad_local: int
    cantidad_nacional: int
    precio_local_promedio: float
    precio_nac_promedio: float
    valor_local: float
    valor_nac: float
    valor_total: float
    ya_incluida: bool
    prefactura_id: int | None = None


class PrefacturaCourierCreate(BaseModel):
    cod_mensajero: str
    periodo_desde: date
    periodo_hasta: date
    planillas: list[str]
    notas: str | None = None
    valor_ajustado: float | None = None
    notas_ajuste: str | None = None


class PrefacturaPlanillaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    planilla: str
    fecha_escaner: date | None
    cantidad_local: int
    cantidad_nacional: int
    precio_local: float
    precio_nac: float
    valor_local: float
    valor_nac: float
    valor_total: float


class PrefacturaCourierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cod_mensajero: str
    mensajero_nombre: str | None = None
    fecha_generacion: date
    periodo_desde: date | None
    periodo_hasta: date | None
    cantidad_planillas: int
    cantidad_local: int
    cantidad_nacional: int
    valor_local: float
    valor_nacional: float
    valor_total: float
    estado: str
    notas: str | None
    valor_ajustado: float | None = None
    notas_ajuste: str | None = None
    valor_a_pagar: float
    created_at: datetime | None
    planillas: list[PrefacturaPlanillaRead] = []


class AjustarMontoRequest(BaseModel):
    valor_ajustado: float | None = None
    notas_ajuste: str | None = None


class RegistrarFacturaRequest(BaseModel):
    numero_factura: str
    fecha_emision: date | None = None
    fecha_vencimiento: date
    valor_total: float
    notas: str | None = None


class FacturaCourierCxpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    prefactura_id: int
    cod_mensajero: str
    mensajero_nombre: str | None = None
    numero_factura: str
    fecha_emision: date | None
    fecha_vencimiento: date
    valor_total: float
    estado: str
    notas: str | None
    fecha_pago: date | None
    created_at: datetime | None


class FacturaCourierCxpUpdate(BaseModel):
    numero_factura: str | None = None
    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None
    valor_total: float | None = None
    notas: str | None = None
    estado: str | None = None


class PagarCxpRequest(BaseModel):
    fecha_pago: date
    notas: str | None = None
