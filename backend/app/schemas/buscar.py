from pydantic import BaseModel


class PaqueteItem(BaseModel):
    clave: str
    fuente: str
    nombre: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    fecha: str | None = None
    cod_men: str | None = None
    estado: str | None = None
    # campos ERP
    cliente: str | None = None
    planilla: str | None = None
    tipo_gestion: str | None = None


class BuscarResultado(BaseModel):
    total: int
    historico: int
    erp: int
    items: list[PaqueteItem]
