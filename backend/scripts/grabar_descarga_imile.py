"""Graba cómo funciona la descarga de una tula en iMile (Offloading Scan), para poder
automatizarla en el servicio Go (flujo/). Usa la sesión de iMile del backend
(app/services/imile_sesion.py): se corre dentro del contenedor servilla_backend.

Dos pasos:

  mirar      NO descarga nada. Abre dsOffloadingScan, toma una foto y anota los campos
             de la pantalla y las peticiones que hace la página al cargar.

  tarea      NO descarga nada. En el panel "Seguimiento de descarga" abre el detalle de un
             vehículo en camino (--numero BGNB...) y graba qué responde iMile (¿trae la
             lista de tulas y paquetes antes de llegar?).

  descargar  DESCARGA DE VERDAD la tula --codigo en iMile (no se deshace). Escribe el
             código en el campo de escaneo, presiona Enter y graba la petición y la
             respuesta de iMile. Si aparece cualquier ventana (confirmar, bloquear…) NO
             presiona nada: toma la foto y termina. Exige --confirmo.

Uso (en el servidor):
  docker exec servilla_backend python scripts/grabar_descarga_imile.py mirar
  docker exec servilla_backend python scripts/grabar_descarga_imile.py tarea --numero BGNB202610240018
  docker exec servilla_backend python scripts/grabar_descarga_imile.py descargar --codigo 2610... --confirmo

Todo queda en /app/.secrets/grabacion_imile_<fecha>/ (fotos .png y peticiones.json). No se
guardan cookies ni el encabezado Authorization.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.imile_descarga_grabacion import CAMPOS_JS, RUTA_DESCARGA, escuchar  # noqa: E402
from app.services.imile_sesion import imile_sesion  # noqa: E402

ESPERA_CARGA_MS = 6_000
ESPERA_RESPUESTA_MS = 10_000


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("modo", choices=["mirar", "tarea", "descargar"])
    p.add_argument("--numero", help="número de tarea del vehículo (solo con tarea)")
    p.add_argument("--codigo", help="código de la tula (solo con descargar)")
    p.add_argument("--selector", help="campo donde se escribe el código (si no, input[name=scanNumber] o el primero visible)")
    p.add_argument("--confirmo", action="store_true", help="sé que la descarga en iMile es real y no se deshace")
    a = p.parse_args()
    if a.modo == "descargar" and (not a.codigo or not a.confirmo):
        p.error("descargar necesita --codigo y --confirmo")
    if a.modo == "tarea" and not a.numero:
        p.error("tarea necesita --numero")

    base = Path(os.environ.get("GRABACION_DIR", "/app/.secrets"))
    carpeta = base / f"grabacion_imile_{datetime.now():%Y%m%d_%H%M%S}"
    carpeta.mkdir(parents=True, exist_ok=True)
    peticiones: list = []
    try:
        async with imile_sesion.usar() as page:
            escuchar(page, peticiones)
            await page.goto(f"{imile_sesion.base_url}{RUTA_DESCARGA}")
            await page.wait_for_timeout(ESPERA_CARGA_MS)
            await imile_sesion.cerrar_recorrido(page)
            await page.screenshot(path=str(carpeta / "1_pantalla.png"), full_page=True)
            campos = await page.evaluate(CAMPOS_JS)
            (carpeta / "campos.json").write_text(json.dumps(campos, ensure_ascii=False, indent=2))
            print(f"URL: {page.url}")
            print(json.dumps(campos, ensure_ascii=False, indent=2))

            if a.modo == "tarea":
                antes = len(peticiones)
                await page.get_by_text(a.numero.strip(), exact=True).first.click()
                await page.wait_for_timeout(ESPERA_RESPUESTA_MS)
                await page.screenshot(path=str(carpeta / "2_tarea.png"), full_page=True)
                print(f"Peticiones al abrir la tarea: {len(peticiones) - antes}")

            if a.modo == "descargar":
                selector = a.selector or (
                    "input[name='scanNumber']" if await page.locator("input[name='scanNumber']").count()
                    else "input[type='text']:visible"
                )
                campo = page.locator(selector).first
                await campo.fill(a.codigo.strip())
                await page.screenshot(path=str(carpeta / "2_codigo_escrito.png"), full_page=True)
                await campo.press("Enter")
                await page.wait_for_timeout(ESPERA_RESPUESTA_MS)
                await page.screenshot(path=str(carpeta / "3_despues.png"), full_page=True)
                ventanas = await page.locator("[role=dialog]:visible").count()
                print(f"Ventanas abiertas después de Enter: {ventanas} (no se presionó nada)")
    finally:
        (carpeta / "peticiones.json").write_text(json.dumps(peticiones, ensure_ascii=False, indent=2))
        await imile_sesion.cerrar()
    print(f"\nPeticiones grabadas: {len(peticiones)}")
    for f in peticiones:
        print(f"  {f['metodo']} {f['estado']} {f['url']}")
    print(f"Archivos en {carpeta}")


if __name__ == "__main__":
    asyncio.run(main())
