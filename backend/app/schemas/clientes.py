from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class PrecioClienteBase(BaseModel):
    tipo_servicio: str = Field(pattern="^(sobre|paquete)$")
    ambito: str = Field(pattern="^(bogota|nacional)$")
    precio_entrega: float = 0
    precio_devolucion: float = 0
    costo_mensajero_entrega: float = 0
    costo_mensajero_devolucion: float = 0
    vigencia_desde: date
    vigencia_hasta: date | None = None
    notas: str | None = None


class PrecioClienteCreate(PrecioClienteBase):
    pass


class PrecioClienteUpdate(BaseModel):
    precio_entrega: float | None = None
    precio_devolucion: float | None = None
    costo_mensajero_entrega: float | None = None
    costo_mensajero_devolucion: float | None = None
    vigencia_desde: date | None = None
    vigencia_hasta: date | None = None
    activo: bool | None = None
    notas: str | None = None


class PrecioClienteRead(PrecioClienteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cliente_id: int
    activo: bool
    fecha_creacion: datetime | None = None


class ClienteBase(BaseModel):
    nombre_empresa: str
    nit: str
    contacto_nombre: str | None = None
    contacto_telefono: str | None = None
    contacto_email: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    plazo_pago_dias: int = 30
    notas: str | None = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre_empresa: str | None = None
    contacto_nombre: str | None = None
    contacto_telefono: str | None = None
    contacto_email: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    plazo_pago_dias: int | None = None
    notas: str | None = None
    activo: bool | None = None


class ClienteRead(ClienteBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    fecha_creacion: datetime | None = None
    fecha_modificacion: datetime | None = None


class ClienteWithPrecios(ClienteRead):
    precios: list[PrecioClienteRead] = []
