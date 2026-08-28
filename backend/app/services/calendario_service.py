from __future__ import annotations

from datetime import date

import holidays

_CO_HOLIDAYS = holidays.country_holidays("CO")

# Recargo dominical/festivo legal vigente (Ley 2466 de 2025): 90% desde jul-2026,
# sube a 100% en jul-2027. Ajustar aquí cuando cambie.
RECARGO_DOMINICAL_FESTIVO = 0.90


def es_domingo_o_festivo(fecha: date) -> bool:
    return fecha.weekday() == 6 or fecha in _CO_HOLIDAYS


def tarifa_con_recargo(tarifa_base: float) -> float:
    return round(tarifa_base * (1 + RECARGO_DOMINICAL_FESTIVO), 2)
