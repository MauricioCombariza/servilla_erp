"""Formato de un serial de paquete, para separar lecturas reales de basura.

Vistos en los 3.407 seriales entregados (2026-11): 13 dígitos (61…, 36…, 60…) o IM + 14
dígitos. Los códigos de tula de iMile son 13 dígitos que empiezan por 26 (26 + AAMMDD…).
"""
import re

RE_SERIAL_VALIDO = re.compile(r"^(?:\d{13}|IM\d{14})$")
RE_CODIGO_TULA = re.compile(r"^26\d{11}$")


def parece_codigo_tula(serial: str) -> bool:
    return bool(RE_CODIGO_TULA.match(serial))


def es_serial_valido(serial: str) -> bool:
    """Formato de paquete y no de tula."""
    return bool(RE_SERIAL_VALIDO.match(serial)) and not parece_codigo_tula(serial)
