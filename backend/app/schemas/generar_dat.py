from pydantic import BaseModel


class SerialError(BaseModel):
    serial: str
    courrier: str


class GenerarDatResult(BaseModel):
    orden: str
    fecha_ini: str
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
