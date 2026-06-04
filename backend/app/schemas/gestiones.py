from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PersonalMin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre_completo: str


class ClienteMin(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_empresa: str


class SerialGestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    serial: str
    f_emi: date | None
    f_esc: date
    planilla: str
    cod_men: str
    mensajero_id: int | None
    mensajero: PersonalMin | None
    cliente_id: int | None
    cliente: ClienteMin | None
    tipo_gestion: str
    tipo_envio: str
    ambito: str
    precio_cliente: float
    precio_mensajero: float
    estado: str
    liquidacion_id: int | None
    factura_id: int | None
    editado_manualmente: bool
    observaciones: str | None
    fecha_creacion: datetime | None
    fecha_modificacion: datetime | None


class SerialGestionUpdate(BaseModel):
    mensajero_id: int | None = None
    cod_men: str | None = None
    precio_cliente: float | None = None
    precio_mensajero: float | None = None
    estado: str | None = None
    tipo_gestion: str | None = None
    tipo_envio: str | None = None
    ambito: str | None = None
    editado_manualmente: bool | None = None
    observaciones: str | None = None


class PlanillaResumen(BaseModel):
    """Agrupación de seriales por (planilla, cod_men)."""
    planilla: str
    cod_men: str
    mensajero_nombre: str | None
    mensajero_id: int | None
    fecha_escaner: date | None
    entregas: int
    devoluciones: int
    total_seriales: int
    total_cliente: float
    total_mensajero: float
    precio_promedio_mensajero: float
    estados: dict[str, int]
    bloqueada: bool          # todos los seriales tienen editado_manualmente = True
    con_precio_cero: int


class CambiarMensajeroRequest(BaseModel):
    cod_men: str
    mensajero_id: int | None = None


class CambiarPrecioRequest(BaseModel):
    precio_mensajero: float


class PlanillaActionResult(BaseModel):
    planilla: str
    seriales_actualizados: int


class RecalcularRequest(BaseModel):
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    cliente_id: int | None = None
    cod_men: str | None = None
    solo_precio_cero: bool = False


class RecalcularResult(BaseModel):
    seriales_actualizados: int
    seriales_sin_precio: int
    errores: list[str]
