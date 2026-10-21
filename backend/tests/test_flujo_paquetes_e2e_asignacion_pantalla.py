"""Recorrido de la pantalla /asignacion-zonas (Pasos 3.1 y 3.2 con sesión del ERP) en un navegador
de escritorio, contra el frontend y el backend corriendo de verdad (scripts/e2e_flujo_paquetes.sh
deja la URL en E2E_FRONTEND_URL). Sin esa variable la prueba se salta."""
import os

import bcrypt
import pytest
from playwright.async_api import async_playwright, expect
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.personal import Personal
from app.models.tulas import Tula, TulaSerial
from app.models.usuarios import Usuario
from app.services.asignacion_zonas_service import hoy

FRONTEND = os.environ.get("E2E_FRONTEND_URL")
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not FRONTEND, reason="Sin E2E_FRONTEND_URL (correr con scripts/e2e_flujo_paquetes.sh)"),
]

USUARIO, CLAVE = "test-e2e-asignacion", "clave-e2e-asignacion"
MENSAJEROS = {"E2EA": "Mensajero Pantalla Uno", "E2EB": "Mensajero Pantalla Dos"}
SERIAL = "TESTE2EA-0001"  # leído hoy en una tula, de la zona 60_1


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario == USUARIO))
        await db.execute(delete(Personal).where(Personal.codigo.in_(list(MENSAJEROS))))  # cascada a asignaciones
        await db.execute(delete(Usuario).where(Usuario.username == USUARIO))
        await db.commit()


@pytest.fixture
async def pagina():
    """Usuario de logística (tiene "Asignación de Zonas"), dos mensajeros y un paquete leído hoy en 60_1."""
    await _limpiar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=bcrypt.hashpw(CLAVE.encode(), bcrypt.gensalt()).decode(),
                       nombre_completo="Prueba E2E Asignación", rol="logistica", activo=True))
        for i, (codigo, nombre) in enumerate(MENSAJEROS.items()):
            db.add(Personal(codigo=codigo, nombre_completo=nombre, identificacion=f"TEST-E2EA-{i}",
                            tipo_personal="mensajero", activo=True))
        tula = Tula(codigo="BAG-E2EA", sin_etiqueta=False, estado="cerrada", usuario=USUARIO, fecha=hoy())
        db.add(tula)
        await db.flush()
        db.add(TulaSerial(tula_id=tula.id, serial=SERIAL, en_tabla=True, zona="60_1"))
        await db.commit()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(f"{FRONTEND}/login")
        await page.locator("input").first.fill(USUARIO)
        await page.locator("input[type=password]").fill(CLAVE)
        await page.get_by_role("button", name="Ingresar").click()
        await page.wait_for_url(lambda u: "/login" not in u)
        await page.get_by_role("link", name="Asignación de Zonas").click()
        yield page
        await browser.close()
    await _limpiar()


def _zona(page, zona):
    return page.locator("button[aria-pressed], button:disabled").filter(has_text=zona).first


async def _buscar(page, codigo):
    await page.get_by_placeholder("Código del mensajero").fill(codigo)
    await page.get_by_role("button", name="Buscar").click()


async def test_3_2_asignar_zonas_choque_reasignar_y_pistolear(pagina):
    page = pagina
    await expect(page.get_by_role("heading", name="Asignación de Zonas")).to_be_visible()

    # Código inexistente
    await _buscar(page, "NOEXISTE")
    await expect(page.get_by_text("Mensajero no encontrado")).to_be_visible()

    # 3.1: código → nombre; 3.2: le marco 60_1 y 60_2 y guardo
    await _buscar(page, "E2EA")
    await expect(page.get_by_text("Mensajero Pantalla Uno").first).to_be_visible()
    await _zona(page, "60_1").click()
    await _zona(page, "60_2").click()
    await page.get_by_role("button", name="Guardar zonas de Mensajero Pantalla Uno").click()
    await expect(page.get_by_text("Zonas de Mensajero Pantalla Uno guardadas (2)")).to_be_visible()
    await expect(_zona(page, "60_1")).to_contain_text("Mensajero Pantalla Uno")
    await expect(_zona(page, "60_1")).to_contain_text("1 paq.")
    await expect(page.get_by_text("Paquetes de Mensajero Pantalla Uno hoy")).to_contain_text("(1")

    # Otro mensajero pide 60_2: avisa del choque y con "Sí, reasignar" se la pasa
    await _buscar(page, "E2EB")
    await expect(page.get_by_text("Mensajero Pantalla Dos").first).to_be_visible()
    await _zona(page, "60_2").click()
    await page.get_by_role("button", name="Guardar zonas de Mensajero Pantalla Dos").click()
    await expect(page.get_by_text("Estas zonas ya las tiene otro mensajero")).to_be_visible()
    await page.get_by_role("button", name="Sí, reasignar").click()
    await expect(_zona(page, "60_2")).to_contain_text("Mensajero Pantalla Dos")
    await expect(_zona(page, "60_1")).to_contain_text("Mensajero Pantalla Uno")

    # Paquete suelto de 60_1 pistoleado al segundo, y devuelto a su zona
    campo = page.get_by_placeholder("Serial del paquete")
    await campo.fill(SERIAL)
    await campo.press("Enter")
    await expect(page.get_by_text("pasó de Mensajero Pantalla Uno a Mensajero Pantalla Dos")).to_be_visible()
    await expect(page.get_by_text("Paquetes de Mensajero Pantalla Dos hoy")).to_contain_text("1 reasignado")
    await page.get_by_role("button", name="Devolver a su zona").click()
    await expect(page.get_by_text("Todavía no tiene paquetes leídos en sus zonas.")).to_be_visible()
