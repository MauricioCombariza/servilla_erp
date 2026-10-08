"""Tests de la sesión de iMile (Paso 2.0) con un navegador real contra un iMile FALSO
servido en local: mismo formulario de ingreso (userCode / password), recorrido de
bienvenida que aparece tarde y tapa la página, y selector de idioma en el encabezado.
No tocan iMile."""
import asyncio

import pytest

from app.config import settings
from app.services.imile_sesion import (
    ImileCredencialesFaltantesError,
    ImileLoginError,
    ImileSesion,
)
from tests.fake_imile import CLAVE, USUARIO, servidor_fake_imile


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
def credenciales(monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)


@pytest.fixture
async def sesion(fake_imile_url, tmp_path):
    s = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                    login_timeout_ms=3_000, espera_carga_ms=200,
                    recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield s
    await s.cerrar()


async def test_sin_credenciales_no_abre_navegador(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", "")
    monkeypatch.setattr(settings, "imile_pass", "")
    with pytest.raises(ImileCredencialesFaltantesError):
        await sesion.conectar()
    assert (await sesion.estado()).navegador_abierto is False


async def test_conectar_inicia_sesion_cierra_recorrido_y_pone_espanol(sesion, credenciales, tmp_path):
    estado = await sesion.conectar()

    assert estado.conectado and estado.idioma == "Español"
    assert estado.ultimo_ingreso is not None
    assert (tmp_path / "sesion.json").exists()  # la sesión queda guardada para el próximo arranque
    async with sesion.usar() as page:
        assert await page.locator(".fireWrap").count() == 0


async def test_sesion_expirada_vuelve_a_entrar_sola(sesion, credenciales):
    await sesion.conectar()
    primer_ingreso = sesion.ultimo_ingreso
    async with sesion.usar() as page:
        await page.context.clear_cookies()  # iMile cierra la sesión
        await page.reload()

    async with sesion.usar() as page:
        assert "/login" not in page.url
        assert await page.locator("#idioma").inner_text() == "Español"
    assert sesion.ultimo_ingreso > primer_ingreso


async def test_credenciales_incorrectas(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", "mala")
    with pytest.raises(ImileLoginError):
        await sesion.conectar()


async def test_usar_no_deja_que_dos_pasos_escriban_a_la_vez(sesion, credenciales):
    await sesion.conectar()
    dentro = 0
    maximo = 0

    async def paso():
        nonlocal dentro, maximo
        async with sesion.usar():
            dentro += 1
            maximo = max(maximo, dentro)
            await asyncio.sleep(0.05)
            dentro -= 1

    await asyncio.gather(paso(), paso(), paso())
    assert maximo == 1
