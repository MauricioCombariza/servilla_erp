"""Informe de tiempo de entrega de los paquetes iMile (mejora continua).

- Fecha inicial: llegada a la estación según el tracking de iMile (`fecha_llegada_ds`).
- Fecha de entrega: "Delivered time" del informe Delivered (`fecha_entrega`).
- Devoluciones: novedades del tracking (`novedades_imile`); cada una descuenta 24 h.
  Una reprogramación ("Need after N days") también es devolución, pero descuenta 5 días
  (decisión del 2026-11-20).
- Tiempo real: horas seguidas entre la fecha inicial y la entrega.
- Tiempo ajustado: tiempo real − descuentos, nunca menos de 0 (una novedad el mismo día
  de la entrega dejaba la guía en negativo).
- Cumple el ANS si el tiempo ajustado ≤ 48 h.
- Solo entran guías entregadas: las devoluciones totales nunca tienen fecha de entrega.
- El rango de fechas filtra por el día de entrega, en hora de Bogotá.
- Una guía sin tracking todavía sale en el listado, pero no cuenta para el % ni los promedios.
- Calidad de datos (DMAIC 2.5): cada guía lleva alertas. `negativo` (la llegada a la
  estación es posterior a la entrega) es un dato imposible y sale del % y de los promedios;
  `mas_7_dias` (tiempo ajustado > 7 días) y `ajuste_al_piso` (los descuentos superan el
  tiempo real) solo se marcan para revisarlas: sacarlas inflaría el cumplimiento.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.excel_utils import construir_excel_multi

TZ = ZoneInfo("America/Bogota")
ANS_HORAS = 48
DESCUENTO_HORAS = 24
DESCUENTO_REPROGRAMACION_HORAS = 5 * 24
MAX_HORAS_AJUSTADAS = 7 * 24

ALERTA_SIN_TRACKING = "sin_tracking"
ALERTA_NEGATIVO = "negativo"
ALERTA_MAS_7_DIAS = "mas_7_dias"
ALERTA_PISO = "ajuste_al_piso"
ALERTAS = {
    ALERTA_SIN_TRACKING: "Sin tracking",
    ALERTA_NEGATIVO: "Llegada posterior a la entrega",
    ALERTA_MAS_7_DIAS: "Más de 7 días ajustados",
    ALERTA_PISO: "Descuentos mayores al tiempo real",
}
ALERTAS_QUE_EXCLUYEN = {ALERTA_SIN_TRACKING, ALERTA_NEGATIVO}

_SQL = text("""
    SELECT sg.serial, sg.cod_men, p.nombre_completo AS mensajero,
           sg.fecha_llegada_ds, sg.fecha_entrega,
           CASE WHEN sg.novedades_imile IS NULL THEN NULL
                ELSE jsonb_array_length(sg.novedades_imile) END AS devoluciones,
           CASE WHEN sg.novedades_imile IS NULL THEN NULL
                ELSE (SELECT count(*) FROM jsonb_array_elements(sg.novedades_imile) n
                      WHERE n->>'motivo' ILIKE 'Need after%') END AS reprogramaciones
    FROM seriales_gestion sg
    LEFT JOIN personal p ON p.id = sg.mensajero_id
    WHERE sg.fecha_entrega IS NOT NULL
      AND (sg.fecha_entrega AT TIME ZONE 'America/Bogota')::date BETWEEN :desde AND :hasta
    ORDER BY sg.fecha_entrega, sg.serial
""")


@dataclass(frozen=True)
class GuiaTiempoEntrega:
    serial: str
    cod_men: str | None
    mensajero: str | None
    devoluciones: int | None
    reprogramaciones: int | None  # de las devoluciones, cuántas son reprogramaciones
    fecha_inicial: datetime | None
    fecha_entrega: datetime
    horas_reales: float | None
    horas_ajustadas: float | None
    cumple: bool | None
    alertas: tuple[str, ...] = ()

    @property
    def medida(self) -> bool:
        """Cuenta para el % y los promedios: tiene tracking y el dato es posible."""
        return self.cumple is not None and not ALERTAS_QUE_EXCLUYEN.intersection(self.alertas)


@dataclass(frozen=True)
class Resumen:
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
    cumplen_sin_descuento: int  # tiempo real ≤ 48 h, sin descontar devoluciones
    porcentaje_cumple_sin_descuento: float | None
    alertas: dict[str, int]  # guías por alerta (una guía puede tener varias)


def _descuento(devoluciones: int, reprogramaciones: int) -> int:
    return (DESCUENTO_HORAS * (devoluciones - reprogramaciones)
            + DESCUENTO_REPROGRAMACION_HORAS * reprogramaciones)


def calcular(fecha_inicial: datetime | None, fecha_entrega: datetime,
             devoluciones: int | None, reprogramaciones: int = 0,
             ) -> tuple[float | None, float | None, bool | None]:
    """→ (horas reales, horas ajustadas, cumple el ANS). None si falta el tracking.
    `reprogramaciones` está incluido en `devoluciones` y descuenta 5 días en vez de 24 h."""
    if fecha_inicial is None or devoluciones is None:
        return None, None, None
    reales = round((fecha_entrega - fecha_inicial).total_seconds() / 3600, 2)
    ajustadas = max(0.0, round(reales - _descuento(devoluciones, reprogramaciones), 2))
    return reales, ajustadas, ajustadas <= ANS_HORAS


def detectar_alertas(horas_reales: float | None, horas_ajustadas: float | None,
                     devoluciones: int | None, reprogramaciones: int = 0) -> tuple[str, ...]:
    """Reglas automáticas de calidad de datos (DMAIC 2.5)."""
    if horas_reales is None or horas_ajustadas is None or devoluciones is None:
        return (ALERTA_SIN_TRACKING,)
    if horas_reales < 0:
        return (ALERTA_NEGATIVO,)
    alertas = []
    if horas_ajustadas > MAX_HORAS_AJUSTADAS:
        alertas.append(ALERTA_MAS_7_DIAS)
    if horas_reales - _descuento(devoluciones, reprogramaciones) < 0:
        alertas.append(ALERTA_PISO)
    return tuple(alertas)


async def listar(db: AsyncSession, desde: date, hasta: date) -> list[GuiaTiempoEntrega]:
    filas = (await db.execute(_SQL, {"desde": desde, "hasta": hasta})).all()
    guias = []
    for r in filas:
        reprog = r.reprogramaciones or 0
        reales, ajustadas, cumple = calcular(r.fecha_llegada_ds, r.fecha_entrega, r.devoluciones,
                                             reprog)
        guias.append(GuiaTiempoEntrega(
            serial=r.serial, cod_men=(r.cod_men or "").strip() or None, mensajero=r.mensajero,
            devoluciones=r.devoluciones, reprogramaciones=r.reprogramaciones,
            fecha_inicial=r.fecha_llegada_ds,
            fecha_entrega=r.fecha_entrega, horas_reales=reales, horas_ajustadas=ajustadas,
            cumple=cumple,
            alertas=detectar_alertas(reales, ajustadas, r.devoluciones, reprog),
        ))
    return guias


def _promedio(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def _percentil(valores: list[float], p: float) -> float | None:
    """Percentil con interpolación lineal (igual que PERCENTIL.INCLUIR de Excel)."""
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p
    i = int(k)
    siguiente = v[min(i + 1, len(v) - 1)]
    return round(v[i] + (siguiente - v[i]) * (k - i), 2)


def _porcentaje(parte: int, total: int) -> float | None:
    return round(100 * parte / total, 1) if total else None


def resumir(guias: list[GuiaTiempoEntrega]) -> Resumen:
    con_tracking = sum(1 for g in guias if g.cumple is not None)
    medidas = [g for g in guias if g.medida]
    cumplen = sum(1 for g in medidas if g.cumple)
    reales = [g.horas_reales for g in medidas]
    ajustadas = [g.horas_ajustadas for g in medidas]
    con_devoluciones = sum(1 for g in medidas if g.devoluciones)
    sin_descuento = sum(1 for h in reales if h <= ANS_HORAS)
    return Resumen(
        total=len(guias),
        con_tracking=con_tracking,
        sin_tracking=len(guias) - con_tracking,
        medidas=len(medidas),
        cumplen=cumplen,
        porcentaje_cumple=_porcentaje(cumplen, len(medidas)),
        promedio_horas_reales=_promedio(reales),
        promedio_horas_ajustadas=_promedio(ajustadas),
        mediana_horas_reales=_percentil(reales, 0.5),
        mediana_horas_ajustadas=_percentil(ajustadas, 0.5),
        p90_horas_reales=_percentil(reales, 0.9),
        p90_horas_ajustadas=_percentil(ajustadas, 0.9),
        con_devoluciones=con_devoluciones,
        porcentaje_con_devoluciones=_porcentaje(con_devoluciones, len(medidas)),
        cumplen_sin_descuento=sin_descuento,
        porcentaje_cumple_sin_descuento=_porcentaje(sin_descuento, len(medidas)),
        alertas={a: sum(1 for g in guias if a in g.alertas) for a in ALERTAS},
    )


def _fecha(v: datetime | None) -> str | None:
    return v.astimezone(TZ).strftime("%Y-%m-%d %H:%M") if v else None


_COLUMNAS = ["Guía", "Código", "Mensajero", "Devoluciones", "Reprogramaciones",
             "Fecha inicial (llegada DS)", "Fecha de entrega", "Tiempo real (h)",
             "Tiempo ajustado (h)", "Cumple ANS 48 h", "Alertas"]
_WIDTHS = [20, 8, 30, 13, 17, 22, 18, 15, 18, 16, 34]


def construir_excel(guias: list[GuiaTiempoEntrega], desde: date, hasta: date) -> bytes:
    def cumple(g: GuiaTiempoEntrega) -> str:
        return "Sin tracking" if g.cumple is None else ("Sí" if g.cumple else "No")

    filas = [{
        "Guía": g.serial,
        "Código": g.cod_men,
        "Mensajero": g.mensajero,
        "Devoluciones": g.devoluciones,
        "Reprogramaciones": g.reprogramaciones,
        "Fecha inicial (llegada DS)": _fecha(g.fecha_inicial),
        "Fecha de entrega": _fecha(g.fecha_entrega),
        "Tiempo real (h)": g.horas_reales,
        "Tiempo ajustado (h)": g.horas_ajustadas,
        "Cumple ANS 48 h": cumple(g),
        "Alertas": ", ".join(ALERTAS[a] for a in g.alertas if a != ALERTA_SIN_TRACKING),
    } for g in guias]
    r = resumir(guias)
    resumen = [
        {"Indicador": "Guías entregadas", "Valor": r.total},
        {"Indicador": "Con tracking", "Valor": r.con_tracking},
        {"Indicador": "Sin tracking todavía", "Valor": r.sin_tracking},
        {"Indicador": "Medidas (con tracking y datos posibles)", "Valor": r.medidas},
        {"Indicador": "Cumplen el ANS", "Valor": r.cumplen},
        {"Indicador": "% que cumple", "Valor": r.porcentaje_cumple},
        {"Indicador": "% que cumple sin descuento (real ≤ 48 h)", "Valor": r.porcentaje_cumple_sin_descuento},
        {"Indicador": "Promedio tiempo real (h)", "Valor": r.promedio_horas_reales},
        {"Indicador": "Mediana tiempo real (h)", "Valor": r.mediana_horas_reales},
        {"Indicador": "Percentil 90 tiempo real (h)", "Valor": r.p90_horas_reales},
        {"Indicador": "Promedio tiempo ajustado (h)", "Valor": r.promedio_horas_ajustadas},
        {"Indicador": "Mediana tiempo ajustado (h)", "Valor": r.mediana_horas_ajustadas},
        {"Indicador": "Percentil 90 tiempo ajustado (h)", "Valor": r.p90_horas_ajustadas},
        {"Indicador": "Guías con devoluciones", "Valor": r.con_devoluciones},
        {"Indicador": "% con devoluciones", "Valor": r.porcentaje_con_devoluciones},
        *({"Indicador": f"Alerta: {ALERTAS[a]}", "Valor": n} for a, n in r.alertas.items()
          if a != ALERTA_SIN_TRACKING),
    ]
    titulo = (f"Tiempo de entrega iMile — entregas del {desde.isoformat()} al {hasta.isoformat()} "
              f"(ANS {ANS_HORAS} h, −{DESCUENTO_HORAS} h por devolución, "
              f"−{DESCUENTO_REPROGRAMACION_HORAS // 24} días por reprogramación)")
    return construir_excel_multi(
        [
            ("Detalle", titulo, _COLUMNAS, filas, _WIDTHS),
            ("Resumen", titulo, ["Indicador", "Valor"], resumen, [42, 12]),
        ],
        formatos={"Tiempo real (h)": "0.00", "Tiempo ajustado (h)": "0.00"},
    )
