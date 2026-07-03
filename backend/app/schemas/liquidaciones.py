from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class LiquidacionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_liquidacion: str
    personal_id: int
    periodo_mes: int
    periodo_anio: int
    fecha_generacion: date
    fecha_pago_programada: date
    total_entregas: float
    cantidad_entregas: int
    total_horas: float
    cantidad_horas: float
    total_labores: float
    cantidad_labores: int
    total_subsidio: float
    bonificaciones: float
    descuentos: float
    total_a_pagar: float
    estado: str
    fecha_pago_real: date | None
    metodo_pago: str
    referencia_pago: str | None
    observaciones: str | None
    fecha_creacion: datetime | None


class LiquidacionUpdate(BaseModel):
    bonificaciones: float | None = None
    descuentos: float | None = None
    observaciones: str | None = None
    fecha_pago_programada: date | None = None


class PagarLiquidacionRequest(BaseModel):
    fecha_pago_real: date
    metodo_pago: str = "transferencia"
    referencia_pago: str | None = None
    observaciones: str | None = None


class GenerarLiquidacionRequest(BaseModel):
    personal_id: int
    periodo_mes: int
    periodo_anio: int
    fecha_pago_programada: date
    bonificaciones: float = 0
    descuentos: float = 0
    observaciones: str | None = None


class ResumenPendientePago(BaseModel):
    personal_id: int
    codigo: str
    nombre_completo: str
    tipo_personal: str
    total_seriales: int
    total_mensajero: float
    total_horas: float
    total_horas_monto: float
    total_labores: int
    total_labores_monto: float
    total_subsidio: float
    total_pendiente: float
    ya_liquidado: bool
