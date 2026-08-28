"""Automatiza el ingreso de seriales en la página real de offloading scan de iMile.

Mantiene un único navegador Playwright headless, logueado en iMile mediante una
sesión persistida manualmente (ver backend/scripts/imile_login_setup.py). Cada
serial escaneado desde el celular del operador se escribe en el campo de escaneo
real de esa página, tal como si el operador lo hubiera tecleado ahí.
"""
import asyncio
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.config import settings

IMILE_OFFLOAD_URL = "https://ds.imile.com/#/DSOperation/DSInbound/dsOffloadingScan"

# TODO(usuario): reemplazar con el selector real del campo de escaneo, obtenido
# inspeccionando el DOM de la página ya logueada. El heurístico de abajo intenta
# el primer input de texto visible como fallback mientras se define el selector.
SCAN_INPUT_SELECTOR = "input[placeholder*='scan' i], input[type='text']:visible"

# Presencia de esto en la página indica que la sesión de iMile expiró.
LOGIN_FORM_SELECTOR = "input[type='password']"

_NAV_TIMEOUT_MS = 15_000
_ACTION_TIMEOUT_MS = 5_000
_POST_SCAN_WAIT_MS = 400


class ScanResultado(str, Enum):
    OK = "ok"
    ERROR = "error"
    SESION_EXPIRADA = "sesion_expirada"


@dataclass
class ImileScanResult:
    resultado: ScanResultado
    detalle: str | None = None


class ImileSessionExpiredError(Exception):
    pass


class ImileAutomationSession:
    """Singleton perezoso: no lanza el navegador hasta el primer scan."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._lock = asyncio.Lock()

    async def _launch(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

        storage_state_path = settings.imile_storage_state_path
        has_session = os.path.exists(storage_state_path)
        self._context = await self._browser.new_context(
            storage_state=storage_state_path if has_session else None
        )
        self._page = await self._context.new_page()

    async def _ensure_ready(self) -> Page:
        if self._page is None:
            await self._launch()
        assert self._page is not None

        if IMILE_OFFLOAD_URL.split("#")[0] not in self._page.url:
            await self._page.goto(IMILE_OFFLOAD_URL, timeout=_NAV_TIMEOUT_MS)

        return self._page

    async def _sesion_expirada(self, page: Page) -> bool:
        try:
            return await page.locator(LOGIN_FORM_SELECTOR).count() > 0
        except Exception:
            return False

    async def scan(self, serial: str) -> ImileScanResult:
        async with self._lock:
            page = await self._ensure_ready()

            if await self._sesion_expirada(page):
                raise ImileSessionExpiredError(
                    "Sesión de iMile expirada, un administrador debe reingresar manualmente"
                )

            try:
                campo = page.locator(SCAN_INPUT_SELECTOR).first
                await campo.click(timeout=_ACTION_TIMEOUT_MS)
                await campo.fill(serial, timeout=_ACTION_TIMEOUT_MS)
                await campo.press("Enter", timeout=_ACTION_TIMEOUT_MS)
                await page.wait_for_timeout(_POST_SCAN_WAIT_MS)
            except Exception as exc:
                if await self._sesion_expirada(page):
                    raise ImileSessionExpiredError(
                        "Sesión de iMile expirada, un administrador debe reingresar manualmente"
                    ) from exc
                return ImileScanResult(resultado=ScanResultado.ERROR, detalle=str(exc))

            if await self._sesion_expirada(page):
                raise ImileSessionExpiredError(
                    "Sesión de iMile expirada, un administrador debe reingresar manualmente"
                )

            return ImileScanResult(resultado=ScanResultado.OK)

    async def shutdown(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def session_file_exists(self) -> bool:
        return Path(settings.imile_storage_state_path).exists()


imile_automation = ImileAutomationSession()
