"""Imágenes de guía del servidor legado (PR 0 de seguridad).

Sin IMAGENES_LEGADO_URL no se intenta ninguna conexión, no hay direcciones
escritas en el código y la API no expone la URL del servidor legado.
"""
import inspect
import re

import pytest

from app.config import settings
from app.routers import imagenes as router_imagenes
from app.services import imagenes


@pytest.fixture
def base(monkeypatch):
    def _set(url: str, ca: str = ""):
        monkeypatch.setattr(settings, "imagenes_legado_url", url)
        monkeypatch.setattr(settings, "imagenes_legado_ca", ca)
    return _set


def test_url_se_arma_desde_la_configuracion(base):
    base("https://legado.interno/guias/")
    assert imagenes.construir_image_url("1234567890") == "https://legado.interno/guias/1234/567/567890.png"


async def test_sin_configuracion_no_descarga(base, monkeypatch):
    base("")

    class _NoUsar:
        def __init__(self, *a, **k):
            raise AssertionError("no debía crear un cliente HTTP")

    monkeypatch.setattr(imagenes.httpx, "AsyncClient", _NoUsar)
    assert await imagenes.fetch_imagen_bytes("1234567890") is None


async def test_verifica_tls_si_hay_certificado(base, monkeypatch):
    base("https://legado.interno/guias", ca="/certs/legado.pem")
    capturado = {}

    class _Cliente:
        def __init__(self, *, verify, timeout):
            capturado["verify"] = verify

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            class R:
                status_code = 404
                headers = {}
            return R()

    monkeypatch.setattr(imagenes.httpx, "AsyncClient", _Cliente)
    assert await imagenes.fetch_imagen_bytes("1234567890") is None
    assert capturado["verify"] == "/certs/legado.pem"


@pytest.mark.parametrize("modulo", [imagenes, router_imagenes])
def test_no_hay_ip_escrita_en_el_codigo(modulo):
    fuente = inspect.getsource(modulo)
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", fuente), "hay una IP escrita en el código"


def test_la_api_solo_expone_el_proxy():
    fuente = inspect.getsource(router_imagenes.obtener_imagen_guia)
    assert "construir_image_url" not in fuente
    assert "/api/imagenes/" in fuente
