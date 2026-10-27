"""Tests de la asignación de paquetes a un mensajero en iMile (Paso 3.3) con un navegador
real contra el iMile FALSO de tests/fake_imile.py, que responde con el mismo JSON que
iMile real (.../bizAssignDaScan/submit). No tocan iMile."""
import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

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
    yield ImileAsignacion(sesion=sesion, espera_respuesta_ms=5_000, espera_busqueda_ms=4_000, clic_da_ms=1_500)
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


@pytest.mark.parametrize("nombre", ["carlos perez", "Rojas Carlos", "Carlos Pérez"])
async def test_elige_el_unico_cuyo_nombre_trae_todas_las_palabras(asignacion, nombre):
    # En el ERP sin tildes, sin el segundo apellido o en otro orden que en iMile
    await asignacion.asignar(nombre, "IM200014")
    assert [(a[0], a[1]) for a in _enviados()] == [("D21050000001", "Carlos Pérez Rojas")]


async def test_si_imile_no_trae_nada_con_el_nombre_completo_busca_por_el_apellido(asignacion):
    # En iMile quedó "Diana  Mora" (doble espacio): buscar "Diana Mora" no trae nada
    await asignacion.asignar("Diana Mora", "IM200018")
    assert [a[0] for a in _enviados()] == ["D21050000002"]


async def test_el_nombre_exacto_gana_al_que_lo_contiene(asignacion):
    await asignacion.asignar("Juan Carlos", "IM200015")  # solo "Juan Carlos Rodriguez" trae ambas
    await asignacion.asignar("Juan Porras", "IM200016")  # exacto, aunque otro la contuviera
    assert [a[0] for a in _enviados()] == ["D21038000001", "D21043330501"]


@pytest.mark.parametrize("nombre,detalle", [
    ("Rodriguez Ana", "(iMile mostró: Juan Carlos Rodriguez | D21038000001)"),
    ("Pedro Inexistente", "(iMile no devolvió resultados al buscarlo)"),
    ("Ana Ruiz", "aparece 2 veces en la lista de mensajeros de iMile (Ana Ruiz | D21000000001; Ana Ruiz | D21000000002)"),
])
async def test_el_error_dice_que_mostro_imile(asignacion, nombre, detalle):
    # Para que se pueda copiar la opción correcta a "Nombre exacto en iMile"
    with pytest.raises(MensajeroImileNoEncontradoError) as e:
        await asignacion.asignar(nombre, "IM200017")
    assert str(e.value).endswith(detalle)
    assert _enviados() == []


# Algo transparente encima de toda la página (como quedó iMile el 2026-10-26): el selector DA
# se ve, pero el clic nunca le llega
TAPAR = """() => { const d = document.createElement("div"); d.id = "tapa";
  d.style.cssText = "position:fixed;inset:0;z-index:99999"; document.body.appendChild(d); }"""


async def test_selector_tapado_se_recarga_la_pantalla_y_asigna(asignacion):
    await asignacion.asignar("Juan Porras", "IM200010")
    async with asignacion._sesion.usar() as page:
        await page.evaluate(TAPAR)

    r = await asignacion.asignar("Juan Carlos Rodriguez", "IM200011")  # otro mensajero: hay que abrir el selector

    assert r.estado == EstadoIngreso.OK
    assert [(a[0], a[2]) for a in _enviados()][-1] == ("D21038000001", "IM200011")


async def test_selector_que_sigue_tapado_tras_recargar_falla_sin_mandar_nada(asignacion):
    await asignacion.asignar("Juan Porras", "IM200012")
    async with asignacion._sesion.usar() as page:
        await page.add_init_script(f"addEventListener('DOMContentLoaded', {TAPAR})")
        await page.evaluate(TAPAR)

    with pytest.raises(PlaywrightTimeoutError):
        await asignacion.asignar("Juan Carlos Rodriguez", "IM200013")
    assert [a[2] for a in _enviados()] == ["IM200012"]
    assert (asignacion._sesion.state_path.parent / "imile_asignar_error.png").exists()  # para ver qué lo tapaba


@pytest.mark.parametrize("codigo,info,estado", [
    ("1119", "Sin información de pedido()", EstadoIngreso.ERROR),
    ("1118", "Guía ya cerrada", EstadoIngreso.CERRADA),  # respuesta real del 2026-10-23
    ("1121", "Otro", EstadoIngreso.BLOQUEADO),  # en esta pantalla no se conoce: para revisión
])
def test_bloqueos_conocidos_al_asignar(codigo, info, estado):
    body = {"status": "success", "resultObject": {"blockCode": codigo, "blockInfo": info, "voiceType": "fail"}}
    r = clasificar_respuesta(body, BLOQUEOS_ASIGNACION)
    assert (r.estado, r.mensaje) == (estado, info)
