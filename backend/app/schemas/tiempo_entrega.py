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
    alertas: list[str]  # calidad de datos: sin_tracking, negativo, mas_7_dias, ajuste_al_piso


class ResumenTiempoEntrega(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: int
    con_tracking: int
    sin_tracking: int
    medidas: int  # con tracking y sin datos imposibles: la base del %
    cumplen: int
    porcentaje_cumple: float | None
    promedio_horas_reales: float | None
    promedio_horas_ajustadas: float | None
    mediana_horas_reales: float | None
    mediana_horas_ajustadas: float | None
    p90_horas_reales: float | None
    p90_horas_ajustadas: float | None
    con_devoluciones: int
    porcentaje_con_devoluciones: float | None
    cumplen_sin_descuento: int
    porcentaje_cumple_sin_descuento: float | None
    alertas: dict[str, int]


class TiempoEntregaResponse(BaseModel):
    desde: date
    hasta: date
    ans_horas: int
    descuento_horas: int
    descuento_reprogramacion_horas: int
    resumen: ResumenTiempoEntrega
    guias: list[GuiaTiempoEntregaRow]
