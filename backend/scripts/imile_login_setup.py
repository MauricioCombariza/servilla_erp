"""Setup único (o repetible cuando la sesión expire) de la sesión de iMile.

Abre un navegador VISIBLE (headed) apuntando a la página de offloading scan de
iMile. Un operador inicia sesión manualmente ahí (usuario/contraseña, 2FA si
aplica). Al confirmar en la terminal, se guarda el storage_state (cookies +
localStorage) en la ruta configurada (settings.imile_storage_state_path), que
luego reutiliza el backend en modo headless para escribir los seriales
escaneados.

Requiere una pantalla disponible (correr localmente o vía escritorio remoto
hacia el servidor; no funciona dentro de un contenedor/servidor sin display).

Uso:
    uv run python backend/scripts/imile_login_setup.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.imile_automation import IMILE_OFFLOAD_URL  # noqa: E402


async def main() -> None:
    storage_state_path = settings.imile_storage_state_path
    os.makedirs(os.path.dirname(storage_state_path), exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(IMILE_OFFLOAD_URL)

        input(
            "\nInicia sesión en iMile en la ventana del navegador que se abrió.\n"
            "Cuando ya estés logueado y veas la pantalla de offloading scan, "
            "presiona Enter aquí...\n"
        )

        await context.storage_state(path=storage_state_path)
        print(f"Sesión guardada en {storage_state_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
