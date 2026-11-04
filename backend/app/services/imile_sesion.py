"""Sesión de iMile en el servidor (Paso 2.0 del flujo de ingreso de paquetes).

Mantiene un único navegador Playwright headless con sesión iniciada en iMile y la
interfaz en español. Inicia sesión solo con IMILE_USER / IMILE_PASS del .env, y si la
sesión expira vuelve a entrar sin que intervenga nadie. Los pasos que automatizan
iMile (descarga de tulas, ingreso de paquetes, asignación a mensajeros) piden la
página con `async with imile_sesion.usar() as page:`, que además los serializa:
hay un solo navegador y no pueden escribir en él dos a la vez.

A diferencia de imile_automation.py (offloading de paquetes del ERP), no depende de
una sesión guardada a mano con scripts/imile_login_setup.py.
"""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright
from playwright.async_api import Error as PlaywrightError

from app.config import settings

IMILE_BASE_URL = "https://ds.imile.com"
# Desde oct. 2026 el ingreso está en otro dominio: ds.imile.com/login redirige aquí
IMILE_LOGIN_URL = "https://ds-login.imile.com/"
IMILE_HOME_URL = f"{IMILE_BASE_URL}/#"

USUARIO_SELECTOR = "input[name='userCode']"
CLAVE_SELECTOR = "input[name='password']"
# Botón "Acceso" del formulario nuevo, por si Enter no envía
BOTON_ACCESO_SELECTOR = "button:has-text('Acceso'), button:has-text('Login'), button[type='submit']"
# Recorrido de bienvenida ("1 / 6 Switch system") que tapa la página tras entrar
RECORRIDO_CERRAR_SELECTOR = ".fireWrap .close-icon"
IDIOMA_OBJETIVO = "Español"
# Etiquetas que muestra el selector de idioma del encabezado (orden del menú de iMile)
IDIOMAS_IMILE = ["English", "简体中文", "Português", "Español", "Italian", "Macedonian", "German"]

_NAV_TIMEOUT_MS = 30_000
_LOGIN_TIMEOUT_MS = 30_000
_ACCION_TIMEOUT_MS = 5_000
_ESPERA_ENTER_MS = 3_000
_ESPERA_CARGA_MS = 3_000
_CAMBIO_IDIOMA_TIMEOUT_MS = 15_000
_RECORRIDO_QUIETO_MS = 4_000
_RECORRIDO_MAX_MS = 20_000
_PASO_RECORRIDO_MS = 250

# Chrome headless consume menos memoria (el VPS tiene ~4 GB y el kernel ya lo mató por OOM)
_ARGS_CHROMIUM = ["--disable-dev-shm-usage", "--disable-gpu", "--no-zygote"]
# Errores de Playwright que indican que el navegador o la página murieron (no de iMile)
_MARCAS_NAVEGADOR_MUERTO = ("target crashed", "target closed", "has been closed", "browser closed")

_STATE_PATH_DEFECTO = Path(__file__).resolve().parents[2] / ".secrets" / "imile_sesion.json"


class ImileCredencialesFaltantesError(Exception):
    pass


class ImileLoginError(Exception):
    pass


class ImileIdiomaError(Exception):
    pass


def es_navegador_muerto(exc: BaseException) -> bool:
    return isinstance(exc, PlaywrightError) and any(
        m in str(exc).lower() for m in _MARCAS_NAVEGADOR_MUERTO
    )


@dataclass(frozen=True)
class EstadoSesionImile:
    credenciales_configuradas: bool
    navegador_abierto: bool
    conectado: bool
    idioma: str | None
    ultimo_ingreso: datetime | None


class ImileSesion:
    """Singleton perezoso: no abre el navegador hasta que alguien lo necesita."""

    def __init__(
        self,
        base_url: str = IMILE_BASE_URL,
        login_url: str | None = None,
        state_path: Path | None = None,
        login_timeout_ms: int = _LOGIN_TIMEOUT_MS,
        espera_carga_ms: int = _ESPERA_CARGA_MS,
        recorrido_quieto_ms: int = _RECORRIDO_QUIETO_MS,
        recorrido_max_ms: int = _RECORRIDO_MAX_MS,
    ) -> None:
        self._base_url = base_url
        self._login_url = login_url or (IMILE_LOGIN_URL if base_url == IMILE_BASE_URL else f"{base_url}/login")
        self._recorrido_quieto_ms = recorrido_quieto_ms
        self._recorrido_max_ms = recorrido_max_ms
        self._login_timeout_ms = login_timeout_ms
        self._espera_carga_ms = espera_carga_ms
        self._state_path = state_path or Path(settings.imile_sesion_state_path or _STATE_PATH_DEFECTO)
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._roto = False  # Chrome se cayó (OOM, crash): hay que abrir uno nuevo
        self._lock = asyncio.Lock()
        self.ultimo_ingreso: datetime | None = None

    # ── API pública ───────────────────────────────────────────────────────────

    @asynccontextmanager
    async def usar(self) -> AsyncIterator[Page]:
        """Página de iMile con sesión iniciada y en español, de uso exclusivo mientras dure el bloque."""
        async with self._lock:
            try:
                page = await self._preparar()
            except PlaywrightError as exc:
                # Chrome murió entre un paso y otro (aún no llegó el aviso de "crash"):
                # se abre uno nuevo y el paso sigue sin fallar.
                if not es_navegador_muerto(exc):
                    raise
                await self._descartar()
                page = await self._preparar()
            try:
                yield page
            except BaseException as exc:
                # Si Chrome murió a mitad de un paso, ese paso falla, pero el siguiente
                # debe encontrar un navegador nuevo en vez de la página muerta.
                if es_navegador_muerto(exc):
                    await self._descartar()
                raise

    async def conectar(self, forzar: bool = False) -> EstadoSesionImile:
        async with self._lock:
            if forzar:
                await self._descartar()
                await self._abrir_navegador()
                await self._iniciar_sesion(self._page)
            await self._preparar()
            return await self._estado_sin_lock()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def state_path(self) -> Path:
        return self._state_path

    async def cerrar_recorrido(self, page: Page) -> None:
        """Para los pasos que navegan a otra página de iMile: el recorrido puede volver a salir."""
        await self._cerrar_recorrido(page)

    async def estado(self) -> EstadoSesionImile:
        async with self._lock:
            return await self._estado_sin_lock()

    async def cerrar(self) -> None:
        await self._descartar()

    # ── Internos ──────────────────────────────────────────────────────────────

    def _credenciales(self) -> tuple[str, str]:
        if not settings.imile_user or not settings.imile_pass:
            raise ImileCredencialesFaltantesError(
                "Faltan IMILE_USER e IMILE_PASS en el .env del servidor"
            )
        return settings.imile_user, settings.imile_pass

    def _navegador_vivo(self) -> bool:
        return (
            self._page is not None and not self._roto and not self._page.is_closed()
            and self._browser is not None and self._browser.is_connected()
        )

    def _marcar_roto(self, *_args) -> None:
        self._roto = True

    async def _descartar(self) -> None:
        """Cierra lo que quede del navegador. Si Chrome ya murió, cerrar puede fallar: da igual."""
        for cerrar in (
            self._context.close if self._context is not None else None,
            self._browser.close if self._browser is not None else None,
            self._playwright.stop if self._playwright is not None else None,
        ):
            if cerrar is None:
                continue
            try:
                await cerrar()
            except Exception:
                pass
        self._page = self._context = self._browser = self._playwright = None
        self._roto = False

    async def _abrir_navegador(self) -> None:
        if self._navegador_vivo():
            return
        if self._page is not None or self._browser is not None or self._playwright is not None:
            await self._descartar()  # la página quedó muerta (p. ej. el kernel mató a Chrome)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True, args=_ARGS_CHROMIUM)
        self._browser.on("disconnected", self._marcar_roto)
        state = str(self._state_path) if self._state_path.exists() else None
        self._context = await self._browser.new_context(
            storage_state=state, viewport={"width": 1400, "height": 900}
        )
        self._page = await self._context.new_page()
        self._page.on("crash", self._marcar_roto)
        self._page.on("close", self._marcar_roto)

    async def _preparar(self) -> Page:
        self._credenciales()
        await self._abrir_navegador()
        page = self._page
        assert page is not None

        if not page.url.startswith(self._base_url):
            await page.goto(f"{self._base_url}/#", timeout=_NAV_TIMEOUT_MS)
            await page.wait_for_timeout(self._espera_carga_ms)

        if await self._en_login(page):
            await self._iniciar_sesion(page)

        await self._cerrar_recorrido(page)
        await self._poner_en_espanol(page)
        return page

    async def _en_login(self, page: Page) -> bool:
        return (
            page.url.startswith(self._login_url) or "/login" in page.url
            or await page.locator(CLAVE_SELECTOR).count() > 0
        )

    async def _iniciar_sesion(self, page: Page) -> None:
        usuario, clave = self._credenciales()
        await page.goto(self._login_url, timeout=_NAV_TIMEOUT_MS)
        await page.wait_for_selector(USUARIO_SELECTOR, timeout=_NAV_TIMEOUT_MS)
        await page.fill(USUARIO_SELECTOR, usuario)
        await page.fill(CLAVE_SELECTOR, clave)
        await page.press(CLAVE_SELECTOR, "Enter")
        # Entró cuando vuelve a la página de iMile (no basta con salir de /login: el
        # formulario nuevo vive en ds-login.imile.com, cuya URL no dice "/login")
        entro = "base => location.href.startsWith(base) && !location.href.includes('/login')"
        try:
            try:
                await page.wait_for_function(entro, arg=self._base_url, timeout=_ESPERA_ENTER_MS)
            except Exception:
                boton = page.locator(BOTON_ACCESO_SELECTOR)
                if await boton.count() > 0:
                    await boton.first.click(timeout=_ACCION_TIMEOUT_MS)
                await page.wait_for_function(entro, arg=self._base_url, timeout=self._login_timeout_ms)
        except Exception as exc:
            raise ImileLoginError(
                "No se pudo iniciar sesión en iMile: usuario o contraseña incorrectos, "
                "o iMile no respondió"
            ) from exc
        await page.wait_for_timeout(self._espera_carga_ms)
        self.ultimo_ingreso = datetime.now(UTC)
        if self._context is not None:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=str(self._state_path))

    async def _cerrar_recorrido(self, page: Page) -> None:
        """El recorrido de bienvenida aparece unos segundos DESPUÉS de cargar la página y su
        capa tapa los clics. Se cierra cada vez que aparece y se sigue solo cuando lleva
        `recorrido_quieto_ms` sin aparecer (o se agotó `recorrido_max_ms`)."""
        quieto = 0
        transcurrido = 0
        while quieto < self._recorrido_quieto_ms and transcurrido < self._recorrido_max_ms:
            cerrar = page.locator(RECORRIDO_CERRAR_SELECTOR)
            if await cerrar.count() > 0:
                await cerrar.first.click(timeout=_ACCION_TIMEOUT_MS)
                quieto = 0
            else:
                quieto += _PASO_RECORRIDO_MS
            await page.wait_for_timeout(_PASO_RECORRIDO_MS)
            transcurrido += _PASO_RECORRIDO_MS

    async def _etiqueta_idioma(self, page: Page) -> tuple[str, Locator] | None:
        """Etiqueta VISIBLE del selector de idioma (el menú desplegable puede estar en el DOM oculto)."""
        for idioma in IDIOMAS_IMILE:
            candidatos = page.get_by_text(idioma, exact=True)
            for i in range(await candidatos.count()):
                if await candidatos.nth(i).is_visible():
                    return idioma, candidatos.nth(i)
        return None

    async def _idioma_actual(self, page: Page) -> str | None:
        etiqueta = await self._etiqueta_idioma(page)
        return etiqueta[0] if etiqueta else None

    async def _poner_en_espanol(self, page: Page) -> None:
        etiqueta = await self._etiqueta_idioma(page)
        if etiqueta is None or etiqueta[0] == IDIOMA_OBJETIVO:
            return
        await self._cerrar_recorrido(page)
        await etiqueta[1].click(timeout=_ACCION_TIMEOUT_MS)
        await page.locator(
            f"li:has-text('{IDIOMA_OBJETIVO}'), [role='option']:has-text('{IDIOMA_OBJETIVO}'), "
            f"[role='menuitem']:has-text('{IDIOMA_OBJETIVO}')"
        ).first.click(timeout=_ACCION_TIMEOUT_MS)
        # iMile recarga la página al cambiar el idioma y tarda en pintar el encabezado
        await self._esperar_idioma(page, IDIOMA_OBJETIVO)
        await self._cerrar_recorrido(page)
        if self._context is not None:
            await self._context.storage_state(path=str(self._state_path))

    async def _esperar_idioma(self, page: Page, idioma: str) -> None:
        intentos = max(1, _CAMBIO_IDIOMA_TIMEOUT_MS // 500)
        for _ in range(intentos):
            if await self._idioma_actual(page) == idioma:
                return
            await page.wait_for_timeout(500)
        raise ImileIdiomaError(f"iMile no quedó en {idioma} después de cambiar el idioma")

    async def _estado_sin_lock(self) -> EstadoSesionImile:
        configuradas = bool(settings.imile_user and settings.imile_pass)
        if not self._navegador_vivo():
            return EstadoSesionImile(configuradas, False, False, None, self.ultimo_ingreso)
        conectado = not await self._en_login(self._page)
        idioma = await self._idioma_actual(self._page) if conectado else None
        return EstadoSesionImile(configuradas, True, conectado, idioma, self.ultimo_ingreso)


imile_sesion = ImileSesion()
