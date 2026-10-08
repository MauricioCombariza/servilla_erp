"""Ingreso de cada paquete en iMile (Paso 2.5): "Llegada (Waybill No)" / arrivalScanAWB.

Escribe el serial en Número de Guía (scanNumber) y presiona Enter, como haría la
persona en la página. El peso no se llena (decisión del usuario) y la fecha de la
página se deja como está.

El resultado se lee de la respuesta que la propia página recibe de iMile
(POST .../inbound/submit), no del texto en pantalla. Visto en iMile real (2026-10-08):
la respuesta siempre trae status "success"; lo que importa está en resultObject:
  - blockCode / blockInfo → iMile abre una ventana "bloquear" con Cancelar / Confirmar;
    la automatización SIEMPRE cancela. 1121 "No registrar Motivo Problema" = el paquete
    ya estaba ingresado (repetido); 1119 "Sin información de pedido()" = el serial no
    existe en iMile (error); cualquier otro código queda "bloqueado" para revisión.
  - repeat = true → el paquete ya se había ingresado.
  - voiceType = "fail" sin bloqueo → error.

Se apaga con IMILE_INGRESO_ACTIVO=false (por defecto) hasta validarlo contra iMile real.
"""
from dataclasses import dataclass
from enum import Enum

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.services.imile_sesion import ImileSesion, imile_sesion

RUTA_LLEGADA = "/#/DSOperation/OperationManagement/arrivalScanAWB"
RUTA_API_INGRESO = "/inbound/submit"
CAMPO_GUIA = "input[name='scanNumber']"

_CARGA_PAGINA_MS = 30_000
_ESPERA_RESPUESTA_MS = 20_000
_ESPERA_VENTANA_MS = 3_000


class EstadoIngreso(str, Enum):
    OK = "ok"
    REPETIDO = "repetido"
    BLOQUEADO = "bloqueado"
    ERROR = "error"
    SIN_CONFIRMAR = "sin_confirmar"


# Significado operativo de los bloqueos de iMile (confirmado por el usuario 2026-10-08:
# en el celular de quien escanea, 1121 suena como "repetido" y 1119 sale como error
# porque el serial no existe en la base de iMile). Otros códigos quedan "bloqueado".
_BLOQUEOS_CONOCIDOS = {
    "1121": EstadoIngreso.REPETIDO,  # "No registrar Motivo Problema": ya estaba ingresado
    "1119": EstadoIngreso.ERROR,  # "Sin información de pedido()": no existe en iMile
}


@dataclass(frozen=True)
class ResultadoIngreso:
    estado: EstadoIngreso
    mensaje: str | None = None
    codigo: str | None = None  # blockCode / msgCode de iMile


def _abre_ventana_bloqueo(body: dict | None) -> bool:
    ro = (body or {}).get("resultObject") or {}
    return bool(ro.get("blockCode") or ro.get("blockInfo"))


def clasificar_respuesta(body: dict | None) -> ResultadoIngreso:
    """Respuesta JSON de .../inbound/submit → resultado del ingreso."""
    if not body:
        return ResultadoIngreso(EstadoIngreso.SIN_CONFIRMAR, "iMile no devolvió respuesta")
    if body.get("status") != "success":
        return ResultadoIngreso(EstadoIngreso.ERROR, body.get("message"), body.get("resultCode") or None)

    ro = body.get("resultObject") or {}
    codigo = ro.get("blockCode") or ro.get("msgCode") or None
    if _abre_ventana_bloqueo(body):
        estado = _BLOQUEOS_CONOCIDOS.get(str(ro.get("blockCode")), EstadoIngreso.BLOQUEADO)
        return ResultadoIngreso(estado, ro.get("blockInfo"), codigo)
    if ro.get("repeat"):
        return ResultadoIngreso(EstadoIngreso.REPETIDO, ro.get("warnMsg") or "Ya ingresado", codigo)
    if ro.get("voiceType") == "fail":
        return ResultadoIngreso(EstadoIngreso.ERROR, ro.get("warnMsg") or body.get("message"), codigo)
    return ResultadoIngreso(EstadoIngreso.OK, ro.get("warnMsg") or None, codigo)


class ImileIngreso:
    def __init__(self, sesion: ImileSesion = imile_sesion, espera_respuesta_ms: int = _ESPERA_RESPUESTA_MS):
        self._sesion = sesion
        self._espera_respuesta_ms = espera_respuesta_ms

    async def ingresar(self, serial: str) -> ResultadoIngreso:
        serial = serial.strip()
        async with self._sesion.usar() as page:
            await self._abrir_llegada(page)
            await self._cancelar_ventanas(page)
            campo = page.locator(CAMPO_GUIA).first
            await campo.fill(serial)
            try:
                async with page.expect_response(
                    lambda r: RUTA_API_INGRESO in r.url and r.request.method == "POST",
                    timeout=self._espera_respuesta_ms,
                ) as info:
                    await campo.press("Enter")
                body = await (await info.value).json()
            except (PlaywrightTimeoutError, ValueError):  # sin respuesta a tiempo, o no es JSON
                body = None
            if _abre_ventana_bloqueo(body):
                await self._cancelar_ventanas(page, esperar=True)
        return clasificar_respuesta(body)

    async def _abrir_llegada(self, page: Page) -> None:
        if "arrivalScanAWB" in page.url and await page.locator(CAMPO_GUIA).count() > 0:
            return
        await page.goto(f"{self._sesion.base_url}{RUTA_LLEGADA}")
        await page.locator(CAMPO_GUIA).first.wait_for(state="visible", timeout=_CARGA_PAGINA_MS)
        await self._sesion.cerrar_recorrido(page)

    async def _cancelar_ventanas(self, page: Page, esperar: bool = False) -> None:
        """Cierra sin confirmar: el aviso "Excepción de impresión" (botón "cierre") y la
        ventana "bloquear" (botón "Cancelar"). Nunca presiona "Confirmar"."""
        if esperar:
            try:
                await page.get_by_text("Cancelar", exact=True).first.wait_for(
                    state="visible", timeout=_ESPERA_VENTANA_MS
                )
            except PlaywrightTimeoutError:
                return
        for texto in ("Cancelar", "cierre"):
            botones = page.get_by_text(texto, exact=True)
            for i in range(await botones.count()):
                if await botones.nth(i).is_visible():
                    await botones.nth(i).click()
                    await page.wait_for_timeout(300)


imile_ingreso = ImileIngreso()
