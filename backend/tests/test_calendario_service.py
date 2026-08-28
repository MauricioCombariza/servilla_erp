"""Tests unitarios de app.services.calendario_service."""
from datetime import date

from app.services.calendario_service import es_domingo_o_festivo, tarifa_con_recargo


def test_domingo_es_festivo():
    assert es_domingo_o_festivo(date(2026, 8, 30)) is True  # domingo


def test_festivo_nacional_es_festivo():
    assert es_domingo_o_festivo(date(2026, 1, 1)) is True  # Año Nuevo


def test_martes_no_es_festivo():
    assert es_domingo_o_festivo(date(2026, 8, 25)) is False  # martes


def test_tarifa_con_recargo_aplica_90_por_ciento():
    assert tarifa_con_recargo(7960.90) == 15125.71
