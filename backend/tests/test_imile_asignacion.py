"""Tests de la asignación de paquetes a un mensajero en iMile (Paso 3.3) con un navegador
real contra el iMile FALSO de tests/fake_imile.py, que responde con el mismo JSON que
iMile real (.../bizAssignDaScan/submit). No tocan iMile."""
import pytest

from app.config import settings
from app.services.imile_asignacion import ImileAsignacion, MensajeroImileNoEncontradoError
from app.services.imile_ingreso import EstadoIngreso, clasificar_respuesta
from app.services.imile_asignacion import BLOQUEOS_ASIGNACION
from app.services.imile_sesion import ImileSesion
from tests.fake_imile import BLOQUEO_NO_EXISTE, CLAVE, USUARIO, _FakeImile, servidor_fake_imile


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
async def asignacion(fake_imile_url, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)
    _FakeImile.asignaciones.clear()
    sesion = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                         login_timeout_ms=3_000, espera_carga_ms=200,
                         recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield ImileAsignacion(sesion=sesion, espera_respuesta_ms=5_000, espera_busqueda_ms=4_000)
    await sesion.cerrar()


def _enviados():
    return [(a["daCode"], a["daName"], a["scanNumber"], a["forceOperate"]) for a in _FakeImile.asignaciones]


async def test_elige_el_mensajero_por_nombre_y_asigna_cada_serial(asignacion):
    uno = await asignacion.asignar("juan  porras", " IM200001 ")  # sin importar mayúsculas ni espacios
    dos = await asignacion.asignar("Juan Porras", "IM200002")

    assert (uno.estado, dos.estado) == (EstadoIngreso.OK, EstadoIngreso.OK)
    assert _enviados() == [("D21043330501", "Juan Porras", "IM200001", False),
                           ("D21043330501", "Juan Porras", "IM200002", False)]


async def test_no_confunde_mensajeros_cuyo_nombre_contiene_otro(asignacion):
    await asignacion.asignar("Juan Carlos Rodriguez", "IM200003")
    await asignacion.asignar("Juan Porras", "IM200004")  # cambia de mensajero entre seriales
    assert [(a[0], a[2]) for a in _enviados()] == [("D21038000001", "IM200003"), ("D21043330501", "IM200004")]


async def test_volver_a_asignar_al_mismo_mensajero_es_repetido(asignacion):
    await asignacion.asignar("Juan Porras", "IM200005")
    assert (await asignacion.asignar("Juan Porras", "IM200005")).estado == EstadoIngreso.REPETIDO


async def test_bloqueo_se_reporta_y_nunca_se_confirma(asignacion):
    r = await asignacion.asignar("Juan Porras", "NOEXISTE-9")

    assert (r.estado, r.codigo, r.mensaje) == (EstadoIngreso.ERROR, *BLOQUEO_NO_EXISTE)
    assert all(not a[3] for a in _enviados())  # nunca se reenvió con forceOperate
    async with asignacion._sesion.usar() as page:
        assert await page.locator("#bloqueo").count() == 0  # ventana cancelada
    assert (await asignacion.asignar("Juan Porras", "IM200006")).estado == EstadoIngreso.OK  # y se sigue


async def test_acepta_el_nombre_como_sale_en_el_selector_con_su_codigo(asignacion):
    # Con el código se elige esa opción exacta, aunque el nombre esté repetido
    await asignacion.asignar("Ana Ruiz | D21000000002", "IM200008")
    await asignacion.asignar(" juan porras |  D21043330501 ", "IM200009")
    assert [(a[0], a[2]) for a in _enviados()] == [("D21000000002", "IM200008"), ("D21043330501", "IM200009")]


@pytest.mark.parametrize("nombre", ["Pedro Inexistente", "Ana Ruiz", "Juan Porras | D99999999999"])
async def test_mensajero_que_no_se_puede_elegir_no_manda_nada(asignacion, nombre):  # no está · repetido · código errado
    with pytest.raises(MensajeroImileNoEncontradoError):
        await asignacion.asignar(nombre, "IM200007")
    assert _enviados() == []


def test_en_asignar_solo_el_1119_es_error_conocido():
    body = {"status": "success", "resultObject": {"blockCode": "1121", "blockInfo": "Otro", "voiceType": "fail"}}
    assert clasificar_respuesta(body, BLOQUEOS_ASIGNACION).estado == EstadoIngreso.BLOQUEADO
