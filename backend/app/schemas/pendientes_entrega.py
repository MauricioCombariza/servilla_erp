from pydantic import BaseModel


class DesgloseMesRow(BaseModel):
    mes: str
    pendientes: int


class PendientesEntregaRow(BaseModel):
    cod_men: str
    nombre: str
    email: str | None
    tiene_email: bool
    pendientes: int
    desglose_mensual: list[DesgloseMesRow]


class PendientesEntregaResumen(BaseModel):
    tipo_personal: str
    corte_desde: str
    personas: list[PendientesEntregaRow]


class ResumenMensualRow(BaseModel):
    anomes: str
    mes: str
    courier_externo: int
    mensajero: int
    total: int


class ResumenMensualResponse(BaseModel):
    corte_desde: str
    meses: list[ResumenMensualRow]
