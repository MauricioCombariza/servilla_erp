from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PaqueteEstancadoRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    zona: str | None
    localidad: str | None
    direccion: str | None
    destinatario: str | None
    f_emi: date | None
    primer_ingreso: datetime
    dias: int
    lecturas: int
    codigo: str | None
    mensajero: str | None
    fecha_asignacion: date | None
    origen_asignacion: str | None
    imile_estado: str | None
    devolucion: str | None
    motivo_descarte: str | None


class GrupoEstancadosRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clave: str
    nombre: str
    paquetes: int
    max_dias: int


class PaquetesEstancadosResponse(BaseModel):
    corte: date
    dias_min: int
    total: int
    devoluciones_ocultas: int
    descartados_ocultos: int
    paquetes: list[PaqueteEstancadoRow]
    por_mensajero: list[GrupoEstancadosRow]
    por_zona: list[GrupoEstancadosRow]
