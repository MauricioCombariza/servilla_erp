"""Recorrido de la pantalla /escaneo-tulas (Pasos 2.2, 2.4, 2.5, 2.6 y 2.8 en una sola pantalla)
en un navegador del tamaño de un celular, contra el frontend y el backend corriendo de verdad
(scripts/e2e_flujo_paquetes.sh los levanta y deja la URL en E2E_FRONTEND_URL). Sin esa
variable la prueba se salta.

El backend de la prueba corre con el ingreso en iMile apagado (filas "iMile apagado"). Los
estados de iMile (error → Reintentar → ok) se prueban en la pantalla cambiando la respuesta
del backend en el navegador; contra iMile (falso) se prueban en test_flujo_paquetes_e2e.py."""
import json
import os
from datetime import date

import bcrypt
import pytest
from playwright.async_api import async_playwright, expect
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.tulas import Tula, TulaSerial
from app.models.usuarios import Usuario
from app.services.paquetes_despacho_service import PaqueteEntrada, guardar_paquetes

FRONTEND = os.environ.get("E2E_FRONTEND_URL")
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not FRONTEND, reason="Sin E2E_FRONTEND_URL (correr con scripts/e2e_flujo_paquetes.sh)"),
]

USUARIO, CLAVE = "test-e2e-tulas", "clave-e2e-tulas"
BASE = {
    "TESTE2ET-0001": "CL 63 # 27-12",  # 60_1
    "TESTE2ET-0002": "CL 64 # 20-11",  # 60_2
    "TESTE2ET-0003": "CL 21 33 40",    # fuera de zona
}
NO_EN_TABLA = "TESTE2ET-9999"
CELULAR = {"width": 390, "height": 844}


async def _limpiar():
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(select(Tula.id).where(Tula.usuario == USUARIO))).scalars().all()
        if ids:
            await db.execute(delete(TulaSerial).where(TulaSerial.tula_id.in_(ids)))
            await db.execute(delete(Tula).where(Tula.id.in_(ids)))
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.in_(list(BASE))))
        await db.execute(delete(Usuario).where(Usuario.username == USUARIO))
        await db.commit()


@pytest.fixture
async def mariela():
    """Usuario con el rol de Mariela (mensajero, tiene "Escaneo de Tulas") y la base del día."""
    await _limpiar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=bcrypt.hashpw(CLAVE.encode(), bcrypt.gensalt()).decode(),
                       nombre_completo="Prueba E2E Tulas", rol="mensajero", activo=True))
        await db.commit()
        await guardar_paquetes(db, [PaqueteEntrada(serial=s, direccion=d) for s, d in BASE.items()], date.today())
    yield
    await _limpiar()


@pytest.fixture
async def pagina(mariela):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport=CELULAR, is_mobile=True, has_touch=True)
        await page.goto(f"{FRONTEND}/login")
        await page.locator("input").first.fill(USUARIO)
        await page.locator("input[type=password]").fill(CLAVE)
        await page.get_by_role("button", name="Ingresar").click()
        await page.wait_for_url(lambda u: "/login" not in u)
        await page.goto(f"{FRONTEND}/escaneo-tulas")
        yield page
        await browser.close()


async def _leer(page, codigo):
    """Como el lector Bluetooth: escribe el código en el campo y manda Enter."""
    campo = page.get_by_placeholder("Código de la tula").or_(page.get_by_placeholder("Serial del paquete"))
    await campo.fill(codigo)
    await campo.press("Enter")


def _contador(page):
    return page.locator("header > div").first


def _fila(page, serial):
    return page.locator("li").filter(has_text=serial[-4:]).filter(has_text=serial[:-4])


async def test_2_2_leer_la_tula_y_sus_paquetes_en_la_misma_pantalla(pagina):
    page = pagina
    await expect(page.get_by_text("Lee el código de la TULA", exact=True)).to_be_visible()

    # Tula con 3 paquetes esperados
    await page.get_by_label("Paquetes que trae").fill("3")
    await _leer(page, "BAG-E2E-1")
    await expect(page.get_by_text("Tula BAG-E2E-1")).to_be_visible()
    await expect(page.get_by_text("Lee los PAQUETES de la tula", exact=True)).to_be_visible()
    await expect(_contador(page)).to_have_text("3faltan")

    # Paquete en zona: destino grande (2.6), cuenta (2.4) y queda en la lista con iMile apagado (2.5)
    await _leer(page, "TESTE2ET-0001")
    await expect(_contador(page)).to_have_text("2faltan")
    await expect(page.get_by_text("60_1", exact=True).first).to_be_visible()
    await expect(_fila(page, "TESTE2ET-0001")).to_contain_text("iMile apagado")

    # El mismo paquete otra vez: avisa y no cuenta
    await page.wait_for_timeout(2100)  # pasa el antirrebote de la cámara
    await _leer(page, "TESTE2ET-0001")
    await expect(page.get_by_text("Ya estaba leído en esta tula")).to_be_visible()
    await expect(_contador(page)).to_have_text("2faltan")

    # Fuera de zona y uno que no está en la base
    await _leer(page, "TESTE2ET-0003")
    await expect(_fila(page, "TESTE2ET-0003")).to_contain_text("Fuera de zona")
    await _leer(page, NO_EN_TABLA)
    await expect(page.get_by_text("No está en la tabla").first).to_be_visible()
    await expect(_contador(page)).to_have_text("0faltan")

    # Uno de más: el contador pasa a "sobran"
    await _leer(page, "TESTE2ET-0002")
    await expect(_contador(page)).to_have_text("1sobran")

    # La pantalla cabe en el celular
    assert await page.evaluate("document.documentElement.scrollWidth") <= CELULAR["width"]

    # Si se recarga, retoma la tula abierta con lo leído
    await page.reload()
    await expect(page.get_by_text("Tula BAG-E2E-1")).to_be_visible()
    await expect(_contador(page)).to_have_text("1sobran")
    await expect(page.locator("li")).to_have_count(4)

    # Otra tula con esta abierta: pregunta antes de cerrarla (2.8)
    await page.get_by_role("button", name="Nueva tula").click()
    await expect(page.get_by_text("Lee el código de la TULA", exact=True)).to_be_visible()
    await _leer(page, "BAG-E2E-2")
    await expect(page.get_by_text("Tienes abierta la tula BAG-E2E-1 con 4 paquetes.")).to_be_visible()
    await page.get_by_role("button", name="Sí, cerrar y abrir").click()
    await expect(page.get_by_text("Tula BAG-E2E-2")).to_be_visible()
    await expect(_contador(page)).to_have_text("0leídos")

    # Sin total (iMile no lo dio): se escribe con la tula ya abierta y el contador pasa a "faltan"
    await page.get_by_label("¿Cuántos paquetes trae?").fill("5")
    await page.get_by_role("button", name="Guardar").click()
    await expect(_contador(page)).to_have_text("5faltan")
    await expect(page.get_by_label("¿Cuántos paquetes trae?")).to_have_count(0)

    # Cerrar a mano: resumen
    await _leer(page, "TESTE2ET-0002")
    await expect(_contador(page)).to_have_text("4faltan")
    await page.get_by_role("button", name="Cerrar tula").click()
    await page.get_by_role("button", name="Sí, cerrar").click()
    await expect(page.get_by_text("Tula BAG-E2E-2 cerrada")).to_be_visible()
    await expect(page.get_by_text("Lee el código de la TULA", exact=True)).to_be_visible()

    async with AsyncSessionLocal() as db:
        tulas = (await db.execute(select(Tula).where(Tula.usuario == USUARIO).order_by(Tula.id))).scalars().all()
    assert [(t.codigo, t.estado) for t in tulas] == [("BAG-E2E-1", "cerrada"), ("BAG-E2E-2", "cerrada")]


async def test_2_5_tula_sin_etiqueta_y_reintentar_imile_desde_la_pantalla(pagina):
    page = pagina

    # La respuesta del backend se cambia en el navegador para simular que iMile falló
    async def imile_falla(route):
        resp = await route.fetch()
        body = await resp.json()
        body["imile"] = {"estado": "error", "mensaje": "TimeoutError: iMile no respondió"}
        await route.fulfill(response=resp, body=json.dumps(body))

    async def imile_ok(route):
        resp = await route.fetch()
        body = await resp.json()
        body.update(imile_estado="ok", imile_mensaje=None)
        await route.fulfill(response=resp, body=json.dumps(body))

    await page.route("**/api/tulas/*/seriales", imile_falla)
    await page.route("**/api/tulas/*/seriales/*/reintentar-imile", imile_ok)

    await page.get_by_role("button", name="Tula sin etiqueta").click()
    await expect(page.get_by_text("Tula sin etiqueta", exact=True)).to_be_visible()

    await _leer(page, "TESTE2ET-0002")
    fila = _fila(page, "TESTE2ET-0002")
    await expect(fila).to_contain_text("iMile: error")
    await expect(fila).to_contain_text("iMile no respondió")
    await expect(_contador(page)).to_have_text("1leídos")  # la lectura cuenta aunque iMile falle

    await fila.get_by_role("button", name="Reintentar").click()
    await expect(fila).to_contain_text("iMile ✓")

    # Al cerrar, lo que iMile dice que traía la tula: qué faltó y qué no venía en ella
    async def con_faltantes(route):
        resp = await route.fetch()
        body = await resp.json()
        body.update(faltantes=["TESTE2ET-0001", "TESTE2ET-0003"], no_esperados=["TESTE2ET-0002"])
        await route.fulfill(response=resp, body=json.dumps(body))

    await page.route("**/api/tulas/*/cerrar", con_faltantes)
    await page.get_by_role("button", name="Cerrar tula").click()
    await page.get_by_role("button", name="Sí, cerrar").click()
    await expect(page.get_by_text("Faltaron (2)")).to_be_visible()
    await expect(page.get_by_text("Leídos que no venían en esta tula según iMile (1)")).to_be_visible()
