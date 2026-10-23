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

RUTA_ASIGNAR = "/#/DSOperation/DispatchManagement/assignDA"
RUTA_API_ASIGNAR = "/bizAssignDaScan/submit"
CAMPO_GUIA = "input[name='scanNumber']"
SELECTOR_DA = "#daCode .ImileSelect-root"
ETIQUETA_DA = "#daCode .ImileSelect-trigger-label"
DESPLEGABLE = ".MuiTooltip-popper"
OPCION_DA = "li.ImileSelect-item"

# En esta pantalla solo se conoce el 1119; cualquier otro bloqueo queda para revisión
BLOQUEOS_ASIGNACION = {"1119": EstadoIngreso.ERROR}  # "Sin información de pedido()": no existe en iMile

_CARGA_PAGINA_MS = 30_000
_ESPERA_RESPUESTA_MS = 20_000
_ESPERA_BUSQUEDA_MS = 1_500


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
    def __init__(self, sesion: ImileSesion = imile_sesion, espera_respuesta_ms: int = _ESPERA_RESPUESTA_MS):
        self._sesion = sesion
        self._espera_respuesta_ms = espera_respuesta_ms

    async def asignar(self, nombre: str, serial: str) -> ResultadoIngreso:
        """Asigna un serial al mensajero `nombre` de iMile. Lanza
        MensajeroImileNoEncontradoError si el nombre no se puede elegir en el selector DA."""
        serial = serial.strip()
        async with self._sesion.usar() as page:
            await self._abrir_asignar(page)
            await cancelar_ventanas(page)
            await self._elegir_mensajero(page, nombre)
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

    async def _abrir_asignar(self, page: Page) -> None:
        if "assignDA" in page.url and await page.locator(CAMPO_GUIA).count() > 0:
            return
        await page.goto(f"{self._sesion.base_url}{RUTA_ASIGNAR}")
        await page.locator(CAMPO_GUIA).first.wait_for(state="visible", timeout=_CARGA_PAGINA_MS)
        await self._sesion.cerrar_recorrido(page)

    async def _elegir_mensajero(self, page: Page, nombre: str) -> MensajeroImile:
        buscado = _buscado(nombre)
        # Si ya está elegido (serial anterior del mismo lote) no se toca el selector
        actual = _opcion(await page.locator(ETIQUETA_DA).first.inner_text())
        if actual and _es_el_buscado(actual, buscado):
            return actual

        await page.locator(SELECTOR_DA).first.click()
        desplegable = page.locator(DESPLEGABLE).last
        await desplegable.locator("input").first.fill(buscado.nombre)
        await page.wait_for_timeout(_ESPERA_BUSQUEDA_MS)

        opciones = desplegable.locator(OPCION_DA)
        encontradas = []
        for i in range(await opciones.count()):
            m = _opcion(await opciones.nth(i).inner_text())
            if m and _es_el_buscado(m, buscado):
                encontradas.append((i, m))
        if len(encontradas) != 1:
            await page.keyboard.press("Escape")
            motivo = "no está" if not encontradas else f"aparece {len(encontradas)} veces"
            raise MensajeroImileNoEncontradoError(f'"{nombre}" {motivo} en la lista de mensajeros de iMile')
        i, mensajero = encontradas[0]
        await opciones.nth(i).click()
        return mensajero


imile_asignacion = ImileAsignacion()
