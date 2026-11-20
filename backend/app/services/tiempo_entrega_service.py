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


@dataclass(frozen=True)
class Resumen:
    total: int
    con_tracking: int
    sin_tracking: int
    cumplen: int
    porcentaje_cumple: float | None
    promedio_horas_reales: float | None
    promedio_horas_ajustadas: float | None
    con_devoluciones: int


def calcular(fecha_inicial: datetime | None, fecha_entrega: datetime,
             devoluciones: int | None, reprogramaciones: int = 0,
             ) -> tuple[float | None, float | None, bool | None]:
    """→ (horas reales, horas ajustadas, cumple el ANS). None si falta el tracking.
    `reprogramaciones` está incluido en `devoluciones` y descuenta 5 días en vez de 24 h."""
    if fecha_inicial is None or devoluciones is None:
        return None, None, None
    reales = round((fecha_entrega - fecha_inicial).total_seconds() / 3600, 2)
    descuento = (DESCUENTO_HORAS * (devoluciones - reprogramaciones)
                 + DESCUENTO_REPROGRAMACION_HORAS * reprogramaciones)
    ajustadas = max(0.0, round(reales - descuento, 2))
    return reales, ajustadas, ajustadas <= ANS_HORAS


async def listar(db: AsyncSession, desde: date, hasta: date) -> list[GuiaTiempoEntrega]:
    filas = (await db.execute(_SQL, {"desde": desde, "hasta": hasta})).all()
    guias = []
    for r in filas:
        reales, ajustadas, cumple = calcular(r.fecha_llegada_ds, r.fecha_entrega, r.devoluciones,
                                             r.reprogramaciones or 0)
        guias.append(GuiaTiempoEntrega(
            serial=r.serial, cod_men=(r.cod_men or "").strip() or None, mensajero=r.mensajero,
            devoluciones=r.devoluciones, reprogramaciones=r.reprogramaciones,
            fecha_inicial=r.fecha_llegada_ds,
            fecha_entrega=r.fecha_entrega, horas_reales=reales, horas_ajustadas=ajustadas,
            cumple=cumple,
        ))
    return guias


def _promedio(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def resumir(guias: list[GuiaTiempoEntrega]) -> Resumen:
    medidas = [g for g in guias if g.cumple is not None]
    cumplen = sum(1 for g in medidas if g.cumple)
    return Resumen(
        total=len(guias),
        con_tracking=len(medidas),
        sin_tracking=len(guias) - len(medidas),
        cumplen=cumplen,
        porcentaje_cumple=round(100 * cumplen / len(medidas), 1) if medidas else None,
        promedio_horas_reales=_promedio([g.horas_reales for g in medidas]),
        promedio_horas_ajustadas=_promedio([g.horas_ajustadas for g in medidas]),
        con_devoluciones=sum(1 for g in medidas if g.devoluciones),
    )


def _fecha(v: datetime | None) -> str | None:
    return v.astimezone(TZ).strftime("%Y-%m-%d %H:%M") if v else None


_COLUMNAS = ["Guía", "Código", "Mensajero", "Devoluciones", "Reprogramaciones",
             "Fecha inicial (llegada DS)", "Fecha de entrega", "Tiempo real (h)",
             "Tiempo ajustado (h)", "Cumple ANS 48 h"]
_WIDTHS = [20, 8, 30, 13, 17, 22, 18, 15, 18, 16]


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
    } for g in guias]
    r = resumir(guias)
    resumen = [
        {"Indicador": "Guías entregadas", "Valor": r.total},
        {"Indicador": "Con tracking (se miden)", "Valor": r.con_tracking},
        {"Indicador": "Sin tracking todavía", "Valor": r.sin_tracking},
        {"Indicador": "Cumplen el ANS", "Valor": r.cumplen},
        {"Indicador": "% que cumple", "Valor": r.porcentaje_cumple},
        {"Indicador": "Promedio tiempo real (h)", "Valor": r.promedio_horas_reales},
        {"Indicador": "Promedio tiempo ajustado (h)", "Valor": r.promedio_horas_ajustadas},
        {"Indicador": "Guías con devoluciones", "Valor": r.con_devoluciones},
    ]
    titulo = (f"Tiempo de entrega iMile — entregas del {desde.isoformat()} al {hasta.isoformat()} "
              f"(ANS {ANS_HORAS} h, −{DESCUENTO_HORAS} h por devolución, "
              f"−{DESCUENTO_REPROGRAMACION_HORAS // 24} días por reprogramación)")
    return construir_excel_multi(
        [
            ("Detalle", titulo, _COLUMNAS, filas, _WIDTHS),
            ("Resumen", titulo, ["Indicador", "Valor"], resumen, [32, 12]),
        ],
        formatos={"Tiempo real (h)": "0.00", "Tiempo ajustado (h)": "0.00"},
    )
