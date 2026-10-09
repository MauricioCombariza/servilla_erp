"""Tests del ingreso de paquetes en iMile (Paso 2.5) con un navegador real contra el
iMile FALSO de tests/fake_imile.py, que responde con el mismo JSON que iMile real
(.../inbound/submit). No tocan iMile."""
import pytest

from app.config import settings
from app.services.imile_ingreso import EstadoIngreso, ImileIngreso, clasificar_respuesta
from app.services.imile_sesion import ImileSesion
from tests.fake_imile import (
    BLOQUEO_NO_EXISTE,
    BLOQUEO_PROBLEMA,
    CLAVE,
    USUARIO,
    servidor_fake_imile,
)


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
async def ingreso(fake_imile_url, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)
    sesion = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                         login_timeout_ms=3_000, espera_carga_ms=200,
                         recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield ImileIngreso(sesion=sesion, espera_respuesta_ms=5_000)
    await sesion.cerrar()


async def test_ingreso_ok_y_luego_repetido(ingreso):
    ok = await ingreso.ingresar(" IM100001 ")
    repetido = await ingreso.ingresar("IM100001")

    assert ok.estado == EstadoIngreso.OK
    assert repetido.estado == EstadoIngreso.REPETIDO


@pytest.mark.parametrize("serial,bloqueo,estado", [
    ("NOEXISTE-1", BLOQUEO_NO_EXISTE, EstadoIngreso.ERROR),  # no existe en iMile
    ("BLOQ-1", BLOQUEO_PROBLEMA, EstadoIngreso.REPETIDO),  # ya estaba ingresado
])
async def test_bloqueo_se_reporta_y_la_ventana_se_cancela_sin_confirmar(ingreso, serial, bloqueo, estado):
    r = await ingreso.ingresar(serial)

    assert (r.estado, r.codigo, r.mensaje) == (estado, bloqueo[0], bloqueo[1])
    async with ingreso._sesion.usar() as page:
        assert await page.locator("#bloqueo").count() == 0  # ventana cerrada
        assert await page.evaluate("localStorage.getItem('confirmado')") is None  # nunca Confirmar


async def test_despues_de_un_bloqueo_se_puede_seguir_escaneando(ingreso):
    await ingreso.ingresar("NOEXISTE-2")
    assert (await ingreso.ingresar("IM100003")).estado == EstadoIngreso.OK


async def test_cierra_el_aviso_de_impresion(ingreso):
    await ingreso.ingresar("IM100004")
    async with ingreso._sesion.usar() as page:
        assert await page.locator("#impresion").count() == 0


# ── Clasificación de la respuesta real de iMile (.../inbound/submit) ──────────

def _respuesta(**ro):
    return {"status": "success", "resultCode": "", "message": "Successful operation!",
            "resultObject": {"status": 2, "repeat": False, "voiceType": "success", **ro}}


@pytest.mark.parametrize("body,estado,codigo,mensaje", [
    # Respuestas reales del 2026-10-08
    (_respuesta(blockInfo="No registrar Motivo Problema", blockCode="1121", msgCode="1121", voiceType="fail"),
     EstadoIngreso.REPETIDO, "1121", "No registrar Motivo Problema"),
    (_respuesta(blockInfo="Sin información de pedido()", blockCode="1119", msgCode="1119", voiceType="fail"),
     EstadoIngreso.ERROR, "1119", "Sin información de pedido()"),
    # Respuesta real del 2026-10-09 al volver a pasar un paquete ya ingresado
    (_respuesta(blockInfo="Escaneo repetido", blockCode="31000", voiceType="fail"),
     EstadoIngreso.REPETIDO, "31000", "Escaneo repetido"),
    # Un bloqueo con código desconocido queda para revisión
    (_respuesta(blockInfo="Otro motivo", blockCode="9999", voiceType="fail"),
     EstadoIngreso.BLOQUEADO, "9999", "Otro motivo"),
    (_respuesta(repeat=True, warnMsg="Ya escaneado"), EstadoIngreso.REPETIDO, None, "Ya escaneado"),
    (_respuesta(voiceType="fail", warnMsg="Algo falló"), EstadoIngreso.ERROR, None, "Algo falló"),
    (_respuesta(), EstadoIngreso.OK, None, None),
    ({"status": "fail", "message": "Token inválido", "resultCode": "401"}, EstadoIngreso.ERROR, "401", "Token inválido"),
    (None, EstadoIngreso.SIN_CONFIRMAR, None, "iMile no devolvió respuesta"),
])
def test_clasificar_respuesta(body, estado, codigo, mensaje):
    r = clasificar_respuesta(body)
    assert (r.estado, r.codigo, r.mensaje) == (estado, codigo, mensaje)
