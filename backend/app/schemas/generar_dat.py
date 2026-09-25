from pydantic import BaseModel


class SerialError(BaseModel):
    serial: str
    courrier: str


class GenerarDatResult(BaseModel):
    orden: str
    fecha_ini: str
    tipo: str
    informe: str
    registros: int
    seriales_excel: int
    seriales_orden: int
    nombre_dat: str
    dat_base64: str
    errores: list[SerialError]
    nombre_errores: str | None = None
    errores_base64: str | None = None
    no_encontrados_en_orden: list[str]
    duplicados_en_excel: list[str]


class SerialPorRevisar(BaseModel):
    serial: str
    courrier: str
    motivo: str
    falta: str


class FormatoServillaResult(BaseModel):
    orden: str
    filas: int
    excluidos: int
    nombre: str
    excel_base64: str
    por_revisar: list[SerialPorRevisar]


class OperadorInforme(BaseModel):
    operador: str
    enviada: int
    entrega: int
    devoluciones: int
    dev_iniciales: int
    nrd: int


class ItemInformeGlobal(BaseModel):
    nombre_archivo: str
    orden: str
    nombre: str
    tipo: str
    registros: int
    corte: str
    fecha_minima: str
    operadores: list[OperadorInforme]
    causales: dict[str, int]
    nombre_excel: str
    advertencias: list[str]


class InformeGlobalResult(BaseModel):
    items: list[ItemInformeGlobal]
    nombre_zip: str
    zip_base64: str
