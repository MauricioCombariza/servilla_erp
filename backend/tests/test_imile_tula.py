"""Tests de la consulta del total de una tula en iMile (Paso 2.3) con un navegador real
contra el iMile FALSO de tests/fake_imile.py. Solo consulta: nunca descarga la tula."""
import pytest

from app.config import settings
from app.services.imile_sesion import ImileSesion
from app.services.imile_tula import ImileTula
from tests.fake_imile import CLAVE, DESCARGADOS, USUARIO, _FakeImile, servidor_fake_imile


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
async def sesion(fake_imile_url, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)
    s = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                    login_timeout_ms=3_000, espera_carga_ms=200,
                    recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield s
    await s.cerrar()


async def test_cuenta_los_paquetes_de_la_tula_entre_todo_lo_descargado(sesion):
    # Página de 2 para obligar a recorrer varias páginas (6 renglones → 3 páginas + 1 vacía)
    consulta = await ImileTula(sesion=sesion, tam_pagina=2).consultar(" 2610154964301 ")

    assert consulta.encontrada
    assert consulta.total == 4
    assert consulta.seriales == tuple(sorted(DESCARGADOS["2610154964301"]))


async def test_tula_que_no_se_ha_descargado(sesion):
    consulta = await ImileTula(sesion=sesion).consultar("2610169999901")

    assert not consulta.encontrada
    assert consulta.total is None


async def test_nunca_descarga_la_tula_en_imile(sesion):
    _FakeImile.descargas.clear()
    await ImileTula(sesion=sesion).consultar("2610154963701")

    assert _FakeImile.descargas == []
