from datetime import date

from pydantic import BaseModel


class ResumenClienteRow(BaseModel):
    cliente: str
    cliente_id: int | None
    entregas: int
    devoluciones: int
    total_seriales: int
    ingreso_cliente: float
    costo_mensajero: float
    margen: float
    margen_pct: float | None   # None cuando ingreso_cliente = 0


class ResumenMensajeroRow(BaseModel):
    cod_men: str
    nombre: str | None
    planillas: int
    total_seriales: int
    entregas: int
    devoluciones: int
    total_mensajero: float


class OrdenReporteRow(BaseModel):
    numero_orden: str
    cliente: str
    fecha_recepcion: date
    cantidad_total: int
    cantidad_entregados: int
    cantidad_devolucion: int
    pendientes: int
    valor_total: float
    estado: str
    pct_gestionado: float


class FacturacionClienteRow(BaseModel):
    cliente: str
    num_facturas: int
    total_facturado: float
    total_cobrado: float
    pendiente: float


class TendenciaMesRow(BaseModel):
    mes: str            # "2026-01"
    total_seriales: int
    entregas: int
    devoluciones: int
    ingreso_estimado: float
    costo_mensajero: float
