"""Tests de integración de /api/tulas (Pasos 2.4 y 2.8): abrir, leer paquetes, contador,
cerrar y la confirmación al abrir una tula nueva con otra abierta. Necesitan la BD con
las migraciones 031–035. El permiso de página se reemplaza por usuarios fijos."""
from datetime import date

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.main import app
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.tulas import Tula
from app.routers import paquetes_despacho as paquetes_router
from app.routers import tulas as tulas_router
from app.services.paquetes_despacho_service import PaqueteEntrada, guardar_paquetes

USUARIO = "test-tulas"
PREFIJO = "TEST28-"
URL = "/api/tulas"


def _como(usuario: str):
    app.dependency_overrides[tulas_router._auth.dependency] = lambda: {"username": usuario, "rol": "mensajero"}


@pytest.fixture(autouse=True)
async def preparar():
    _como(USUARIO)
    app.dependency_overrides[paquetes_router._auth_destino.dependency] = lambda: {"username": USUARIO}
    await _limpiar()
    async with AsyncSessionLocal() as db:
        await guardar_paquetes(db, [
            PaqueteEntrada(f"{PREFIJO}1", "Ana", None, "calle 95 # 49-22"),
            PaqueteEntrada(f"{PREFIJO}2", "Luis", None, "CR 20 # 66-15"),
            PaqueteEntrada(f"{PREFIJO}3", "Eva", None, "CL 21 33 40"),
        ], date(2026, 10, 8))
    yield
    await _limpiar()
    app.dependency_overrides.pop(tulas_router._auth.dependency, None)
    app.dependency_overrides.pop(paquetes_router._auth_destino.dependency, None)


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario.like("test-%")))
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.like(f"{PREFIJO}%")))
        await db.commit()


async def _abrir(client, codigo=None, total=None, cerrar_anterior=False):
    return await client.post(f"{URL}/", json={
        "codigo": codigo, "total_esperado": total, "cerrar_anterior": cerrar_anterior,
    })


async def _leer(client, tula_id, serial):
    return await client.post(f"{URL}/{tula_id}/seriales", json={"serial": serial})


# ── Contador (2.4) ────────────────────────────────────────────────────────────

async def test_contador_baja_desde_el_total_y_puede_quedar_negativo(client):
    tula = (await _abrir(client, "BAG-001", total=3)).json()
    assert (tula["contador"], tula["leidos"], tula["sin_etiqueta"]) == (3, 0, False)

    contadores = []
    for serial in [f"{PREFIJO}1", f"{PREFIJO}2", f"{PREFIJO}3", f"{PREFIJO}NUEVO"]:
        contadores.append((await _leer(client, tula["id"], serial)).json()["tula"]["contador"])

    assert contadores == [2, 1, 0, -1]


async def test_tula_sin_etiqueta_cuenta_hacia_arriba(client):
    tula = (await _abrir(client, None)).json()
    assert (tula["codigo"], tula["sin_etiqueta"], tula["contador"]) == (None, True, 0)

    r1 = (await _leer(client, tula["id"], f"{PREFIJO}1")).json()
    r2 = (await _leer(client, tula["id"], f"{PREFIJO}2")).json()

    assert (r1["tula"]["contador"], r2["tula"]["contador"]) == (1, 2)


async def test_serial_repetido_en_la_misma_tula_no_se_cuenta_dos_veces(client):
    tula = (await _abrir(client, "BAG-002", total=3)).json()
    await _leer(client, tula["id"], f"{PREFIJO}1")

    r = (await _leer(client, tula["id"], f" {PREFIJO}1 ")).json()

    assert r["ya_escaneado"] is True
    assert (r["tula"]["leidos"], r["tula"]["contador"]) == (1, 2)


async def test_cada_lectura_devuelve_el_destino_del_paquete(client):
    tula = (await _abrir(client, "BAG-003")).json()

    con_zona = (await _leer(client, tula["id"], f"{PREFIJO}2")).json()["destino"]
    fuera = (await _leer(client, tula["id"], f"{PREFIJO}3")).json()["destino"]
    no_esta = (await _leer(client, tula["id"], f"{PREFIJO}X999")).json()["destino"]

    assert (con_zona["zona"], con_zona["ultimos_4"]) == ("60_4", "28-2")
    assert fuera["aviso"] == "Fuera de zona"
    assert no_esta["aviso"] == "No está en la tabla"


# ── Abrir y cerrar (2.8) ──────────────────────────────────────────────────────

async def test_tula_nueva_con_otra_abierta_pide_confirmacion(client):
    primera = (await _abrir(client, "BAG-010", total=2)).json()
    await _leer(client, primera["id"], f"{PREFIJO}1")

    r = await _abrir(client, "BAG-011")
    assert r.status_code == 409
    assert r.json()["detail"]["tula_abierta"]["id"] == primera["id"]
    assert (await client.get(f"{URL}/abierta")).json()["id"] == primera["id"]  # sigue abierta

    segunda = (await _abrir(client, "BAG-011", cerrar_anterior=True)).json()
    assert segunda["codigo"] == "BAG-011"
    cerrada = (await client.get(f"{URL}/{primera['id']}")).json()
    assert (cerrada["estado"], cerrada["leidos"], cerrada["diferencia"]) == ("cerrada", 1, 1)


async def test_volver_a_escanear_la_misma_tula_abierta_no_pide_confirmacion(client):
    primera = (await _abrir(client, "BAG-020")).json()
    r = await _abrir(client, "BAG-020")
    assert r.status_code == 201
    assert r.json()["id"] == primera["id"]


async def test_tula_sin_etiqueta_con_otra_abierta_tambien_pide_confirmacion(client):
    await _abrir(client, "BAG-030")
    assert (await _abrir(client, None)).status_code == 409
    assert (await _abrir(client, None, cerrar_anterior=True)).json()["sin_etiqueta"] is True


async def test_cerrar_a_mano_devuelve_resumen_con_seriales(client):
    tula = (await _abrir(client, "BAG-040", total=10)).json()
    for i in (1, 2, 3):
        await _leer(client, tula["id"], f"{PREFIJO}{i}")

    r = (await client.post(f"{URL}/{tula['id']}/cerrar")).json()

    assert (r["estado"], r["total_esperado"], r["leidos"], r["diferencia"]) == ("cerrada", 10, 3, 7)
    assert r["fecha_cierre"] is not None
    assert [s["serial"] for s in r["seriales"]] == [f"{PREFIJO}1", f"{PREFIJO}2", f"{PREFIJO}3"]
    assert (await client.get(f"{URL}/abierta")).json() is None


async def test_no_se_puede_leer_en_una_tula_cerrada(client):
    tula = (await _abrir(client, "BAG-050")).json()
    await client.post(f"{URL}/{tula['id']}/cerrar")

    r = await _leer(client, tula["id"], f"{PREFIJO}1")
    assert r.status_code == 409


async def test_cada_usuario_tiene_su_propia_tula_abierta(client):
    await _abrir(client, "BAG-060")
    _como("test-otro")
    r = await _abrir(client, "BAG-061")
    assert r.status_code == 201  # otro usuario no choca con la tula abierta del primero


async def test_listar_tulas_del_dia(client):
    tula = (await _abrir(client, "BAG-070")).json()
    r = (await client.get(f"{URL}/", params={"fecha": tula["fecha"]})).json()
    assert tula["id"] in [t["id"] for t in r]


async def test_tula_inexistente(client):
    assert (await client.get(f"{URL}/999999999")).status_code == 404
    assert (await _leer(client, 999999999, "X")).status_code == 404
