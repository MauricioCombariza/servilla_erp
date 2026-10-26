"""Asignación de paquetes a un mensajero en iMile (Paso 3.3): "Asignar repartidor" / assignDA.

Como lo haría la persona en la página: en el selector DA se busca el nombre del
mensajero y se elige la opción "Nombre | Dxxxxxxxxxx"; luego cada serial se escribe en
Número de Guía (scanNumber) y se presiona Enter. El mensajero se puede dar solo con el
nombre ("Mariela Pabon") o como sale en el selector ("Mariela Pabon | D21026309101");
con el código se elige exactamente esa opción, aunque el nombre esté repetido.

El resultado se lee de la respuesta que la propia página recibe de iMile
(POST .../bizAssignDaScan/submit), que tiene la misma forma que la de Llegada. Visto en
iMile real (2026-10-23) con un serial inexistente: blockCode 1119 "Sin información de
pedido()" → abre la ventana "bloquear" con Cancelar / Confirmar. Confirmar reenvía con
forceOperate=true (forzar la asignación): la automatización SIEMPRE cancela.

La sesión se pide serial por serial (y no para todo el lote) para no frenar el ingreso
de paquetes de quien está escaneando tulas, que usa el mismo navegador.
"""
import logging
from dataclasses import dataclass

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.services.imile_ingreso import (
    EstadoIngreso,
    ResultadoIngreso,
    abre_ventana_bloqueo,
    cancelar_ventanas,
    clasificar_respuesta,
)
from app.services.imile_sesion import ImileSesion, imile_sesion

log = logging.getLogger(__name__)

RUTA_ASIGNAR = "/#/DSOperation/DispatchManagement/assignDA"
RUTA_API_ASIGNAR = "/bizAssignDaScan/submit"
CAMPO_GUIA = "input[name='scanNumber']"
SELECTOR_DA = "#daCode .ImileSelect-root"
ETIQUETA_DA = "#daCode .ImileSelect-trigger-label"
# El desplegable del selector DA; la página tiene otros .MuiTooltip-popper (tooltips)
DESPLEGABLE = ".MuiTooltip-popper:has(.ImileSelect-list)"
OPCION_DA = "li.ImileSelect-item"

# Bloqueos vistos en iMile real en esta pantalla; cualquier otro queda "bloqueado" para revisión
BLOQUEOS_ASIGNACION = {
    "1119": EstadoIngreso.ERROR,  # "Sin información de pedido()": no existe en iMile
    "1118": EstadoIngreso.CERRADA,  # "Guía ya cerrada" (2026-10-23): no se puede asignar a nadie
}

_CARGA_PAGINA_MS = 30_000
_ESPERA_RESPUESTA_MS = 20_000
# La lista del selector la trae iMile al escribir (POST .../hrms/user/associate/list); desde
# el servidor puede tardar varios segundos. Se revisa seguido hasta que aparezca el mensajero.
_ESPERA_BUSQUEDA_MS = 10_000
_PASO_BUSQUEDA_MS = 250
_ESPERA_ABRIR_MS = 3_000
# Si algo tapa el selector DA (ventana o recorrido de iMile) el clic no entra nunca: se
# corta antes de los 30 s por defecto para recargar la pantalla y reintentar
_CLIC_DA_MS = 8_000


class MensajeroImileNoEncontradoError(Exception):
    """El nombre no está (o está repetido) en la lista de mensajeros de iMile."""


@dataclass(frozen=True)
class MensajeroImile:
    nombre: str
    codigo: str  # código de iMile, ej. D21043330501


def _opcion(texto: str) -> MensajeroImile | None:
    """'Juan Porras | D21043330501' → MensajeroImile."""
    nombre, sep, codigo = texto.strip().rpartition("|")
    if not sep:
        return None
    return MensajeroImile(nombre.strip(), codigo.strip())


def _mismo_nombre(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _es_el_buscado(m: MensajeroImile, buscado: MensajeroImile) -> bool:
    if buscado.codigo:
        return m.codigo.casefold() == buscado.codigo.casefold()
    return _mismo_nombre(m.nombre, buscado.nombre)


def _buscado(texto: str) -> MensajeroImile:
    """'Mariela Pabon' o 'Mariela Pabon | D21026309101' → nombre (y código si lo trae)."""
    texto = " ".join(texto.split())
    return _opcion(texto) or MensajeroImile(texto, "")


class ImileAsignacion:
    def __init__(self, sesion: ImileSesion = imile_sesion, espera_respuesta_ms: int = _ESPERA_RESPUESTA_MS,
                 espera_busqueda_ms: int = _ESPERA_BUSQUEDA_MS, clic_da_ms: int = _CLIC_DA_MS):
        self._sesion = sesion
        self._espera_respuesta_ms = espera_respuesta_ms
        self._espera_busqueda_ms = espera_busqueda_ms
        self._clic_da_ms = clic_da_ms

    async def asignar(self, nombre: str, serial: str) -> ResultadoIngreso:
        """Asigna un serial al mensajero `nombre` de iMile. Lanza
        MensajeroImileNoEncontradoError si el nombre no se puede elegir en el selector DA."""
        serial = serial.strip()
        async with self._sesion.usar() as page:
            await self._abrir_asignar(page)
            await cancelar_ventanas(page)
            try:
                await self._elegir_mensajero(page, nombre)
            except PlaywrightTimeoutError:
                # La página quedó trabada (2026-10-26: todos los seriales de un lote fallaban
                # al hacer clic en el selector DA): se recarga la pantalla y se reintenta una vez
                try:
                    await page.keyboard.press("Escape")
                    await cancelar_ventanas(page)
                    await self._abrir_asignar(page, recargar=True)
                    await self._elegir_mensajero(page, nombre)
                except PlaywrightTimeoutError:
                    await self._guardar_pantalla(page)
                    raise
            campo = page.locator(CAMPO_GUIA).first
            await campo.fill(serial)
            try:
                async with page.expect_response(
                    lambda r: RUTA_API_ASIGNAR in r.url and r.request.method == "POST",
                    timeout=self._espera_respuesta_ms,
                ) as info:
                    await campo.press("Enter")
                body = await (await info.value).json()
            except (PlaywrightTimeoutError, ValueError):  # sin respuesta a tiempo, o no es JSON
                body = None
            if abre_ventana_bloqueo(body):
                await cancelar_ventanas(page, esperar=True)
        return clasificar_respuesta(body, BLOQUEOS_ASIGNACION)

    async def _abrir_asignar(self, page: Page, recargar: bool = False) -> None:
        if not recargar and "assignDA" in page.url and await page.locator(CAMPO_GUIA).count() > 0:
            return
        await page.goto(f"{self._sesion.base_url}{RUTA_ASIGNAR}")
        if recargar:  # goto a la misma ruta con # no recarga el documento
            await page.reload()
        await page.locator(CAMPO_GUIA).first.wait_for(state="visible", timeout=_CARGA_PAGINA_MS)
        await self._sesion.cerrar_recorrido(page)

    async def _guardar_pantalla(self, page: Page) -> None:
        """Para ver después qué tapaba el selector DA."""
        ruta = self._sesion.state_path.parent / "imile_asignar_error.png"
        try:
            await page.screenshot(path=str(ruta), full_page=True)
            log.warning("Selector DA de iMile tapado; pantalla guardada en %s", ruta)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo guardar la pantalla del selector DA tapado")

    async def _elegir_mensajero(self, page: Page, nombre: str) -> MensajeroImile:
        buscado = _buscado(nombre)
        # Si ya está elegido (serial anterior del mismo lote) no se toca el selector
        actual = _opcion(await page.locator(ETIQUETA_DA).first.inner_text())
        if actual and _es_el_buscado(actual, buscado):
            return actual

        desplegable = page.locator(DESPLEGABLE).last
        await page.locator(SELECTOR_DA).first.click(timeout=self._clic_da_ms)
        try:
            await desplegable.wait_for(state="visible", timeout=_ESPERA_ABRIR_MS)
        except PlaywrightTimeoutError:
            # Si ya estaba abierto, ese clic lo cerró: se vuelve a abrir
            await page.locator(SELECTOR_DA).first.click(timeout=self._clic_da_ms)
            await desplegable.wait_for(state="visible", timeout=_CARGA_PAGINA_MS)
        await desplegable.locator("input").first.fill(buscado.nombre)

        opciones = desplegable.locator(OPCION_DA)
        encontradas: list[tuple[int, MensajeroImile]] = []
        for _ in range(max(1, self._espera_busqueda_ms // _PASO_BUSQUEDA_MS)):
            await page.wait_for_timeout(_PASO_BUSQUEDA_MS)
            encontradas = []
            for i in range(await opciones.count()):
                m = _opcion(await opciones.nth(i).inner_text())
                if m and _es_el_buscado(m, buscado):
                    encontradas.append((i, m))
            if encontradas:
                # Un momento más por si la lista sigue llegando (nombres repetidos)
                await page.wait_for_timeout(_PASO_BUSQUEDA_MS)
                encontradas = [
                    (i, m) for i in range(await opciones.count())
                    if (m := _opcion(await opciones.nth(i).inner_text())) and _es_el_buscado(m, buscado)
                ]
                break
        if len(encontradas) != 1:
            await page.keyboard.press("Escape")
            motivo = "no está" if not encontradas else f"aparece {len(encontradas)} veces"
            raise MensajeroImileNoEncontradoError(f'"{nombre}" {motivo} en la lista de mensajeros de iMile')
        i, mensajero = encontradas[0]
        await opciones.nth(i).click()
        return mensajero


imile_asignacion = ImileAsignacion()
