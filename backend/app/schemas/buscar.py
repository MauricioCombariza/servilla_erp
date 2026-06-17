from pydantic import BaseModel


class PaqueteItem(BaseModel):
    clave: str
    tipo: str
    numero_orden: str | None = None
    cliente: str | None = None
    mensajero: str | None = None
    ciudad: str | None = None
    fecha: str | None = None
    estado: str
    planilla: str | None = None
    tipo_gestion: str | None = None


class BuscarResultado(BaseModel):
    total: int
    seriales: int
    ordenes: int
    items: list[PaqueteItem]
