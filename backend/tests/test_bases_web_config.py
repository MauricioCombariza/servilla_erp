"""Configuración de la conexión a bases_web (MariaDB del legado).

Seguridad (PR 0): nunca debe conectarse a una dirección escrita en el código;
sin una URL completa la integración queda deshabilitada.
"""
import pytest

from app.config import settings
from app.services import bases_web


@pytest.fixture
def url(monkeypatch):
    def _set(valor: str):
        monkeypatch.setattr(settings, "bases_web_url", valor)
    return _set


def test_sin_url_queda_deshabilitado(url):
    url("")
    assert bases_web._parse_dsn() == {}


@pytest.mark.parametrize("valor", [
    "mysql://usuario:clave@/bases_web",          # sin host
    "mysql://@host.ejemplo:3306/bases_web",      # sin usuario
    "mysql://usuario:clave@host.ejemplo:3306",   # sin base
    "mysql://usuario:clave@host.ejemplo:3306/",  # base vacía
])
def test_url_incompleta_no_usa_valores_por_defecto(url, valor):
    url(valor)
    assert bases_web._parse_dsn() == {}


def test_url_completa(url):
    url("mysql+pymysql://lector:secreta@10.0.0.5:3307/bases_web")
    assert bases_web._parse_dsn() == {
        "host": "10.0.0.5", "port": 3307, "user": "lector",
        "password": "secreta", "database": "bases_web",
    }


def test_puerto_por_defecto_es_el_estandar(url):
    url("mysql://lector:secreta@db.interna/bases_web")
    assert bases_web._parse_dsn()["port"] == 3306


def test_usuario_y_clave_se_decodifican(url):
    url("mysql://lector%40erp:cl%40ve%25x@db.interna/bases_web")
    dsn = bases_web._parse_dsn()
    assert dsn["user"] == "lector@erp"
    assert dsn["password"] == "cl@ve%x"


def test_tls_con_certificado(url):
    url("mysql://lector:secreta@db.interna/bases_web?ssl_ca=/certs/ca.pem")
    assert bases_web._parse_dsn()["ssl"] == {"ca": "/certs/ca.pem"}


def test_tls_sin_certificado(url):
    url("mysql://lector:secreta@db.interna/bases_web?ssl=1")
    assert bases_web._parse_dsn()["ssl"] == {}


def test_sin_tls_no_agrega_ssl(url):
    url("mysql://lector:secreta@db.interna/bases_web")
    assert "ssl" not in bases_web._parse_dsn()


def test_no_quedan_direcciones_escritas_en_el_codigo():
    import inspect
    import re
    fuente = inspect.getsource(bases_web)
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", fuente), "hay una IP escrita en el código"


def test_busqueda_sin_configuracion_no_intenta_conectar(url, monkeypatch):
    url("")
    def _no_conectar(**_):
        raise AssertionError("no debía intentar conectar")
    monkeypatch.setattr(bases_web.pymysql, "connect", _no_conectar)
    assert bases_web._buscar_histo_serial_sync("123") == []
    assert bases_web._fetch_ciudades_sync("44000") == []
