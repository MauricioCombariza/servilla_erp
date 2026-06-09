from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class OrdenCreate(BaseModel):
    numero_orden: str
    cliente_id: int
    ciudad_destino_id: int | None = None
    fecha_recepcion: date
    tipo_servicio: str
    cantidad_total: int = 0
    precio_unitario: float | None = None
    valor_total: float = 0
    observaciones: str | None = None


class OrdenUpdate(BaseModel):
    ciudad_destino_id: int | None = None
    fecha_recepcion: date | None = None
    tipo_servicio: str | None = None
    cantidad_total: int | None = None
    cantidad_recibido: int | None = None
    cantidad_en_cajoneras: int | None = None
    cantidad_en_lleva: int | None = None
    cantidad_entregados: int | None = None
    cantidad_devolucion: int | None = None
    precio_unitario: float | None = None
    valor_total: float | None = None
    costo_mensajero_total: float | None = None
    costo_alistamiento_total: float | None = None
    costo_pegado_total: float | None = None
    costo_transporte_total: float | None = None
    costo_flete_total: float | None = None
    estado: str | None = None
    facturado: bool | None = None
    observaciones: str | None = None


class ClienteResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_empresa: str
    nit: str


class CiudadResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    ambito: str


class OrdenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero_orden: str
    cliente_id: int
    cliente: ClienteResumen
    ciudad_destino_id: int | None
    ciudad_destino: CiudadResumen | None
    fecha_recepcion: date
    tipo_servicio: str
    cantidad_total: int
    cantidad_recibido: int
    cantidad_en_cajoneras: int
    cantidad_en_lleva: int
    cantidad_entregados: int
    cantidad_devolucion: int
    precio_unitario: float | None
    valor_total: float
    costo_total: float
    utilidad_total: float
    estado: str
    facturado: bool
    fecha_finalizacion: date | None
    observaciones: str | None
    fecha_creacion: datetime | None
    fecha_modificacion: datetime | None


class CargaMasivaResult(BaseModel):
    total_filas: int
    filas_ignoradas: int
    seriales_nuevos: int
    seriales_actualizados: int
    ordenes_nuevas: int
    ordenes_actualizadas: int
    errores: list[str]
