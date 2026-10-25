"""Grabación de UNA descarga real de tula en iMile ("Descarga de escaneo" / dsOffloadingScan).

Antes de descargarla, iMile solo sabe los totales del vehículo, no cuántos paquetes trae
cada tula. Para automatizar la descarga al leer la tula (servicio Go, flujo/) hace falta
ver exactamente qué manda la página y qué responde iMile. Con IMILE_GRABAR_DESCARGA=true,
la PRIMERA tula que se abre en el ERP se descarga en iMile y se graba todo en
<carpeta de la sesión>/grabacion_descarga_<fecha>/ (fotos, campos y peticiones, sin
cookies ni Authorization). Después de intentarlo una vez deja un marcador y no se repite,
aunque haya fallado: la descarga es real y no se deshace. Si iMile abre cualquier
ventana, no se presiona nada.
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.imile_sesion import ImileSesion, imile_sesion

RUTA_DESCARGA = "/#/DSOperation/DSInbound/dsOffloadingScan"
CAMPO = "input[name='scanNumber']"
ESPERA_CARGA_MS = 6_000
ESPERA_RESPUESTA_MS = 10_000
_ENCABEZADOS_OCULTOS = {"authorization", "cookie", "set-cookie"}
MARCADOR = "grabacion_descarga_hecha.txt"

# Qué campos tiene la pantalla (para saber dónde se escribe el código de la tula)
CAMPOS_JS = """() => [...document.querySelectorAll('input, select, textarea, button, [role=dialog]')]
  .filter(e => e.offsetParent !== null)
  .map(e => ({
    tag: e.tagName.toLowerCase(), type: e.type || null, name: e.name || null, id: e.id || null,
    placeholder: e.placeholder || null, texto: (e.innerText || e.value || '').trim().slice(0, 80) || null,
  }))"""

log = logging.getLogger(__name__)
_lock = asyncio.Lock()


def escuchar(page, peticiones: list):
    """Va guardando en `peticiones` cada XHR/fetch de la página con su respuesta JSON.
    Devuelve el handler, para quitarlo con page.remove_listener("response", h)."""
    async def guardar(resp):
        req = resp.request
        if req.resource_type not in ("xhr", "fetch") or "google-analytics" in req.url:
            return
        fila = {
            "hora": datetime.now().isoformat(timespec="milliseconds"),
            "metodo": req.method, "url": req.url, "estado": resp.status,
            "encabezados_peticion": {k: v for k, v in (await req.all_headers()).items()
                                     if k.lower() not in _ENCABEZADOS_OCULTOS},
            "cuerpo_peticion": req.post_data,
        }
        try:
            fila["respuesta"] = await resp.json()
        except Exception:  # noqa: BLE001 - no era JSON
            fila["respuesta"] = None
        peticiones.append(fila)

    def handler(resp):
        asyncio.ensure_future(guardar(resp))

    page.on("response", handler)
    return handler


def carpeta_base(sesion: ImileSesion = imile_sesion) -> Path:
    return sesion.state_path.parent


async def grabar_si_toca(codigo: str, sesion: ImileSesion = imile_sesion) -> Path | None:
    """Si está encendido y no se ha hecho, descarga `codigo` en iMile grabando todo.
    Nunca lanza: cualquier falla queda en el log y en la carpeta de la grabación."""
    if not settings.imile_grabar_descarga or not codigo:
        return None
    async with _lock:
        marcador = carpeta_base(sesion) / MARCADOR
        if marcador.exists():
            return None
        marcador.parent.mkdir(parents=True, exist_ok=True)
        # Antes de intentarlo: una descarga a medias tampoco se debe repetir sola
        marcador.write_text(f"{datetime.now().isoformat()} {codigo}\n")
        carpeta = carpeta_base(sesion) / f"grabacion_descarga_{datetime.now():%Y%m%d_%H%M%S}"
        carpeta.mkdir(parents=True, exist_ok=True)
        try:
            await _descargar(codigo.strip(), carpeta, sesion)
        except Exception as exc:  # noqa: BLE001
            log.exception("No se pudo grabar la descarga de la tula %s", codigo)
            (carpeta / "error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
        return carpeta


async def _descargar(codigo: str, carpeta: Path, sesion: ImileSesion) -> None:
    peticiones: list = []
    async with sesion.usar() as page:
        handler = escuchar(page, peticiones)
        try:
            await page.goto(f"{sesion.base_url}{RUTA_DESCARGA}")
            await page.locator(CAMPO).first.wait_for(state="visible", timeout=30_000)
            await page.wait_for_timeout(ESPERA_CARGA_MS)
            await sesion.cerrar_recorrido(page)
            await page.screenshot(path=str(carpeta / "1_pantalla.png"), full_page=True)
            (carpeta / "campos.json").write_text(
                json.dumps(await page.evaluate(CAMPOS_JS), ensure_ascii=False, indent=2))

            campo = page.locator(CAMPO).first
            await campo.fill(codigo)
            await campo.press("Enter")
            await page.wait_for_timeout(ESPERA_RESPUESTA_MS)
            await page.screenshot(path=str(carpeta / "2_despues.png"), full_page=True)
            ventanas = await page.locator("[role=dialog]:visible").count()
            (carpeta / "resumen.txt").write_text(
                f"codigo={codigo}\nurl={page.url}\nventanas_abiertas={ventanas} (no se presionó nada)\n")
        finally:
            page.remove_listener("response", handler)
            (carpeta / "peticiones.json").write_text(json.dumps(peticiones, ensure_ascii=False, indent=2))
