from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class GuiaTiempoEntregaRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    serial: str
    cod_men: str | None
    mensajero: str | None
    devoluciones: int | None  # None = tracking sin consultar
    reprogramaciones: int | None  # incluidas en devoluciones; descuentan 5 días
    fecha_inicial: datetime | None  # llegada a la estación (tracking iMile)
    fecha_entrega: datetime
    horas_reales: float | None
    horas_ajustadas: float | None
    cumple: bool | None  # None = falta el tracking para calcularlo


class ResumenTiempoEntrega(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    con_tracking: int
    sin_tracking: int
    cumplen: int
    porcentaje_cumple: float | None
    promedio_horas_reales: float | None
    promedio_horas_ajustadas: float | None
    con_devoluciones: int


class TiempoEntregaResponse(BaseModel):
    desde: date
    hasta: date
    ans_horas: int
    descuento_horas: int
    descuento_reprogramacion_horas: int
    resumen: ResumenTiempoEntrega
    guias: list[GuiaTiempoEntregaRow]
