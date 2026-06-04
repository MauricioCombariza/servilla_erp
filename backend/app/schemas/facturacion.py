from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Detalle ────────────────────────────────────────────────────────────────────

class DetalleCreate(BaseModel):
    orden_id: int | None = None
    descripcion: str
    cantidad: int = 1
    precio_unitario: float
    subtotal: float


class DetalleRead(DetalleCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factura_id: int


# ── Pagos ──────────────────────────────────────────────────────────────────────

class PagoCreate(BaseModel):
    fecha_pago: date
    monto: float = Field(gt=0)
    metodo_pago: str = Field(pattern="^(efectivo|transferencia|cheque|tarjeta|otros)$")
    referencia: str | None = None
    observaciones: str | None = None


class PagoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factura_id: int
    fecha_pago: date
    monto: float
    metodo_pago: str
    referencia: str | None
    observaciones: str | None
    fecha_creacion: datetime | None


class PagoRealizadoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    factura_id: int | None
    liquidacion_id: int | None
    fecha_pago: date
    monto: float
    metodo_pago: str
    referencia: str | None
    observaciones: str | None
    fecha_creacion: datetime | None


# ── Facturas emitidas ──────────────────────────────────────────────────────────

class FacturaEmitidaCreate(BaseModel):
    numero_factura: str
    cliente_id: int
    fecha_emision: date
    fecha_vencimiento: date
    periodo_mes: int = Field(ge=1, le=12)
    periodo_anio: int = Field(ge=2020, le=2030)
    cantidad_items: int = 1
    subtotal: float
    descuento: float = 0
    total: float
    observaciones: str | None = None
    detalles: list[DetalleCreate] = []
    ordenes_ids: list[int] = []      # órdenes a vincular y marcar como facturadas


class FacturaEmitidaUpdate(BaseModel):
    fecha_vencimiento: date | None = None
    subtotal: float | None = None
    descuento: float | None = None
    total: float | None = None
    saldo_pendiente: float | None = None
    estado: str | None = None
    observaciones: str | None = None


class ClienteMin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_empresa: str
    nit: str


class FacturaEmitidaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero_factura: str
    cliente_id: int
    cliente: ClienteMin
    fecha_emision: date
    fecha_vencimiento: date
    periodo_mes: int
    periodo_anio: int
    cantidad_items: int
    subtotal: float
    descuento: float
    total: float
    saldo_pendiente: float
    estado: str
    observaciones: str | None
    fecha_creacion: datetime | None
    fecha_modificacion: datetime | None
    detalles: list[DetalleRead] = []
    pagos: list[PagoRead] = []


# ── Facturas recibidas ─────────────────────────────────────────────────────────

class FacturaRecibidaCreate(BaseModel):
    numero_factura: str
    personal_id: int
    tipo: str = Field(pattern="^(courier|transportadora|materiales|otros)$")
    fecha_recepcion: date
    fecha_vencimiento: date
    periodo_mes: int | None = None
    periodo_anio: int | None = None
    cantidad_items: int = 0
    subtotal: float
    descuento: float = 0
    total: float
    observaciones: str | None = None
    detalles: list[DetalleCreate] = []


class FacturaRecibidaUpdate(BaseModel):
    fecha_vencimiento: date | None = None
    subtotal: float | None = None
    total: float | None = None
    saldo_pendiente: float | None = None
    estado: str | None = None
    observaciones: str | None = None


class PersonalMin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre_completo: str
    tipo_personal: str


class FacturaRecibidaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero_factura: str
    personal_id: int
    personal: PersonalMin
    tipo: str
    fecha_recepcion: date
    fecha_vencimiento: date
    periodo_mes: int | None
    periodo_anio: int | None
    cantidad_items: int
    subtotal: float
    descuento: float
    total: float
    saldo_pendiente: float
    estado: str
    observaciones: str | None
    fecha_creacion: datetime | None
    fecha_modificacion: datetime | None
    detalles: list[DetalleRead] = []
    pagos: list[PagoRealizadoRead] = []


# ── Cuentas y resumen ──────────────────────────────────────────────────────────

class CuentaItem(BaseModel):
    id: int
    tipo: str
    referencia: str
    codigo: str | None
    acreedor_o_deudor: str
    fecha_vencimiento: date
    monto: float
    estado: str
    dias: int
    clasificacion: str


class ResumenFinanciero(BaseModel):
    total_por_cobrar: float
    total_vencido_cobrar: float
    vence_esta_semana_cobrar: float
    total_por_pagar: float
    total_vencido_pagar: float
    vence_esta_semana_pagar: float
    facturas_emitidas_mes: float
    facturas_recibidas_mes: float
