"""Grabación de UNA descarga real de tula (imile_descarga_grabacion.py) con un navegador
real contra el iMile FALSO de tests/fake_imile.py."""
import json

import pytest

from app.config import settings
from app.services import imile_descarga_grabacion as grabacion
from app.services.imile_sesion import ImileSesion
from tests.fake_imile import CLAVE, USUARIO, _FakeImile, servidor_fake_imile


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
async def sesion(fake_imile_url, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)
    monkeypatch.setattr(grabacion, "ESPERA_CARGA_MS", 200)
    monkeypatch.setattr(grabacion, "ESPERA_RESPUESTA_MS", 1_000)
    s = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                    login_timeout_ms=3_000, espera_carga_ms=200,
                    recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield s
    await s.cerrar()


async def test_apagada_no_hace_nada(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_grabar_descarga", False)
    antes = len(_FakeImile.descargas)

    assert await grabacion.grabar_si_toca("BAG-1", sesion=sesion) is None
    assert len(_FakeImile.descargas) == antes


async def test_descarga_una_sola_vez_y_graba_la_respuesta(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_grabar_descarga", True)
    antes = len(_FakeImile.descargas)

    carpeta = await grabacion.grabar_si_toca(" BAG-GRAB-1 ", sesion=sesion)

    assert _FakeImile.descargas[antes:] == [{"scanNumber": "BAG-GRAB-1"}]
    peticiones = json.loads((carpeta / "peticiones.json").read_text())
    submit = [p for p in peticiones if "/unloading/submit" in p["url"]]
    assert submit and json.loads(submit[0]["cuerpo_peticion"]) == {"scanNumber": "BAG-GRAB-1"}
    assert submit[0]["respuesta"]["status"] == "success"
    assert all("cookie" not in {k.lower() for k in p["encabezados_peticion"]} for p in peticiones)
    assert (carpeta / "1_pantalla.png").exists() and (carpeta / "2_despues.png").exists()

    # La segunda tula ya no se descarga: el marcador lo impide
    assert await grabacion.grabar_si_toca("BAG-GRAB-2", sesion=sesion) is None
    assert len(_FakeImile.descargas) == antes + 1
