"""Recorrido de la pantalla /subir-despacho (Paso 1.4) en un navegador del tamaño de un
celular, contra el frontend y el backend corriendo de verdad (scripts/e2e_flujo_paquetes.sh
los levanta y deja la URL en E2E_FRONTEND_URL). Sin esa variable la prueba se salta.

Es la única pantalla del flujo construida hasta ahora; escaneo de tulas, vista por zonas y
asignación se prueban por la API en test_flujo_paquetes_e2e.py."""
import os
from io import BytesIO

import bcrypt
import pytest
from openpyxl import Workbook
from playwright.async_api import async_playwright, expect
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.usuarios import Usuario

FRONTEND = os.environ.get("E2E_FRONTEND_URL")
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not FRONTEND, reason="Sin E2E_FRONTEND_URL (correr con scripts/e2e_flujo_paquetes.sh)"),
]

USUARIO, CLAVE = "test-e2e-pantalla", "clave-e2e-pantalla"
BASE = {
    "TESTE2EP-0001": "CL 63 # 27-12",     # 60_1
    "TESTE2EP-0002": "CL 64 # 20-11",     # 60_2
    "TESTE2EP-0003": "CL 21 33 40",       # fuera de zona
    "TESTE2EP-0004": "lote sin numero",   # sin sector
}
CELULAR = {"width": 390, "height": 844}


def _excel(columnas: list[str], filas: list[list]) -> bytes:
    wb = Workbook()
    wb.active.append(columnas)
    for f in filas:
        wb.active.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.in_(list(BASE))))
        await db.execute(delete(Usuario).where(Usuario.username == USUARIO))
        await db.commit()


@pytest.fixture
async def mariela():
    """Usuario con el rol de Mariela (mensajero), que tiene la página "Ingreso de Paquetes"."""
    await _limpiar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=bcrypt.hashpw(CLAVE.encode(), bcrypt.gensalt()).decode(),
                       nombre_completo="Prueba E2E Pantalla", rol="mensajero", activo=True))
        await db.commit()
    yield
    await _limpiar()


@pytest.fixture
async def pagina(mariela, tmp_path):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport=CELULAR, is_mobile=True, has_touch=True)
        await page.goto(f"{FRONTEND}/login")
        await page.locator("input").first.fill(USUARIO)
        await page.locator("input[type=password]").fill(CLAVE)
        await page.get_by_role("button", name="Ingresar").click()
        await page.wait_for_url(lambda u: "/login" not in u)
        await page.goto(f"{FRONTEND}/subir-despacho")
        yield page, tmp_path
        await browser.close()


async def _subir(page, ruta):
    await page.locator("input[type=file]").set_input_files(str(ruta))
    await page.get_by_role("button", name="Subir base").click()


def _dato(page, etiqueta):
    return page.locator("dl > div").filter(has=page.get_by_text(etiqueta, exact=True)).locator("dd")


async def test_1_4_subir_la_base_y_corregir_desde_el_celular(pagina):
    page, tmp = pagina
    ruta = tmp / "DESPACHO SERVILLA E2E.xlsx"
    ruta.write_bytes(_excel(["Waybill number", "Recipient's name", "Customer phone", "Address"],
                            [[s, "Cliente", "3000000000", d] for s, d in BASE.items()]))

    await _subir(page, ruta)

    await expect(page.get_by_text("Base guardada")).to_be_visible()
    await expect(_dato(page, "Paquetes")).to_have_text("4")
    await expect(_dato(page, "Nuevos")).to_have_text("4")
    await expect(_dato(page, "Sin sector")).to_have_text("1")
    await expect(_dato(page, "Devoluciones (fuera de zona)")).to_have_text("2")
    await expect(page.get_by_role("button", name="Descargar devoluciones (Excel)")).to_be_visible()
    # La pantalla cabe en el celular: nada se sale a lo ancho
    ancho = await page.evaluate("document.documentElement.scrollWidth")
    assert ancho <= CELULAR["width"]

    corregir = page.locator("li").filter(has_text="…0004")
    await corregir.locator("input").fill("CL 64 # 25-12")
    await corregir.get_by_role("button", name="Guardar").click()
    await expect(corregir.get_by_text("✓ Barrios Unidos · zona 60_13")).to_be_visible()


async def test_1_4_un_archivo_que_no_es_base_de_imile_avisa_las_columnas(pagina):
    page, tmp = pagina
    ruta = tmp / "otra_cosa.xlsx"
    ruta.write_bytes(_excel(["Guia", "Cliente"], [["X1", "Ana"]]))

    await _subir(page, ruta)

    aviso = page.get_by_role("alert")
    await expect(aviso).to_contain_text("Faltan estas columnas")
    await expect(aviso).to_contain_text("Guia · Cliente")
