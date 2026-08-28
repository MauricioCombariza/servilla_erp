"""Tests unitarios del servicio de automatización iMile, con un Page simulado
(sin lanzar un navegador real ni tocar la base de datos)."""
import pytest

from app.services.imile_automation import (
    ImileAutomationSession,
    ImileSessionExpiredError,
    ScanResultado,
)


class FakeLocator:
    def __init__(self, count=0, raise_on_action=None):
        self._count = count
        self._raise_on_action = raise_on_action
        self.first = self

    async def count(self):
        return self._count

    async def click(self, timeout=None):
        if self._raise_on_action:
            raise self._raise_on_action

    async def fill(self, value, timeout=None):
        if self._raise_on_action:
            raise self._raise_on_action

    async def press(self, key, timeout=None):
        if self._raise_on_action:
            raise self._raise_on_action


class FakePage:
    def __init__(self, login_form_count=0, raise_on_action=None):
        self.login_form_count = login_form_count
        self._raise_on_action = raise_on_action
        self.url = "https://ds.imile.com/#/DSOperation/DSInbound/dsOffloadingScan"

    def locator(self, selector):
        from app.services.imile_automation import LOGIN_FORM_SELECTOR

        if selector == LOGIN_FORM_SELECTOR:
            return FakeLocator(count=self.login_form_count)
        return FakeLocator(raise_on_action=self._raise_on_action)

    async def wait_for_timeout(self, ms):
        pass


@pytest.fixture
def session():
    return ImileAutomationSession()


def _mock_ensure_ready(session, page):
    async def fake_ensure_ready():
        return page

    session._ensure_ready = fake_ensure_ready


async def test_scan_ok(session):
    page = FakePage()
    _mock_ensure_ready(session, page)

    resultado = await session.scan("SERIAL-1")

    assert resultado.resultado == ScanResultado.OK


async def test_scan_sesion_expirada_antes_de_escanear(session):
    page = FakePage(login_form_count=1)
    _mock_ensure_ready(session, page)

    with pytest.raises(ImileSessionExpiredError):
        await session.scan("SERIAL-1")


async def test_scan_error_de_pagina_sin_sesion_expirada(session):
    page = FakePage(raise_on_action=RuntimeError("elemento no encontrado"))
    _mock_ensure_ready(session, page)

    resultado = await session.scan("SERIAL-1")

    assert resultado.resultado == ScanResultado.ERROR
    assert "elemento no encontrado" in resultado.detalle


async def test_scan_falla_por_sesion_expirada_durante_la_accion(session):
    page = FakePage(login_form_count=1, raise_on_action=RuntimeError("timeout"))
    _mock_ensure_ready(session, page)

    with pytest.raises(ImileSessionExpiredError):
        await session.scan("SERIAL-1")
