"""Tests de integración de la vista por zonas (Paso 2.7): una persona escanea y las
demás, sin iniciar sesión y solo con el enlace del día, ven los paquetes de sus zonas.
Necesitan la BD con las migraciones 031–037."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, update

from app.database import AsyncSessionLocal
from app.main import app
from app.models.enlaces_vista import EnlaceVista
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.tulas import Tula
from app.routers import tulas as tulas_router
from app.routers import vista_zonas as vista_router
from app.services.paquetes_despacho_service import PaqueteEntrada, guardar_paquetes

USUARIO = "test-vista"
PREFIJO = "TEST27-"
URL = "/api/escaneo-vista"


@pytest.fixture(autouse=True)
async def preparar():
    quien_escanea = {"username": USUARIO, "rol": "mensajero"}
    app.dependency_overrides[tulas_router._auth.dependency] = lambda: quien_escanea
    app.dependency_overrides[vista_router._auth.dependency] = lambda: quien_escanea
    await _limpiar()
    async with AsyncSessionLocal() as db:
        await guardar_paquetes(db, [
            PaqueteEntrada(f"{PREFIJO}0001", "Ana", None, "CL 63 # 27-11"),   # 60_1
            PaqueteEntrada(f"{PREFIJO}0002", "Luis", None, "CL 64 # 20-11"),  # 60_2
            PaqueteEntrada(f"{PREFIJO}0003", "Eva", None, "CL 21 33 40"),     # fuera de zona
        ], date(2026, 10, 8))
    yield
    await _limpiar()
    app.dependency_overrides.pop(tulas_router._auth.dependency, None)
    app.dependency_overrides.pop(vista_router._auth.dependency, None)


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario == USUARIO))
        await db.execute(delete(EnlaceVista).where(EnlaceVista.usuario == USUARIO))
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.like(f"{PREFIJO}%")))
        await db.commit()


async def _escanear(client, *seriales):
    tula = (await client.post("/api/tulas/", json={"codigo": "BAG-VISTA", "cerrar_anterior": True})).json()
    for s in seriales:
        await client.post(f"/api/tulas/{tula['id']}/seriales", json={"serial": s})


async def _token(client) -> str:
    return (await client.post(f"{URL}/enlace")).json()["token"]


async def _ver(client, token, zonas, desde=0):
    return await client.get(f"{URL}/{token}/paquetes", params={"zonas": zonas, "desde": desde})


async def test_el_enlace_del_dia_es_siempre_el_mismo(client):
    r1 = (await client.post(f"{URL}/enlace")).json()
    r2 = (await client.post(f"{URL}/enlace")).json()
    assert r1["token"] == r2["token"]
    assert r1["ruta"] == f"/ver-zonas/{r1['token']}"
    assert len(r1["token"]) >= 30


async def test_cada_persona_ve_solo_sus_zonas_y_todos_ven_fuera_de_zona(client):
    token = await _token(client)
    await _escanear(client, f"{PREFIJO}0001", f"{PREFIJO}0002", f"{PREFIJO}0003", f"{PREFIJO}9999")

    a = (await _ver(client, token, "60_1")).json()["paquetes"]
    b = (await _ver(client, token, "60_2")).json()["paquetes"]

    assert [(p["ultimos_4"], p["zona"], p["aviso"]) for p in a] == [
        ("0001", "60_1", None), ("0003", None, "Fuera de zona"), ("9999", None, "Fuera de zona"),
    ]
    assert [(p["ultimos_4"], p["zona"]) for p in b] == [("0002", "60_2"), ("0003", None), ("9999", None)]
    assert a[0]["direccion"] == "CL 63 27 11"
    assert "serial" not in a[0]  # solo los últimos 4 dígitos


async def test_sin_zonas_elegidas_solo_se_ven_los_fuera_de_zona(client):
    token = await _token(client)
    await _escanear(client, f"{PREFIJO}0001", f"{PREFIJO}0003")

    paquetes = (await _ver(client, token, "")).json()["paquetes"]
    assert [p["ultimos_4"] for p in paquetes] == ["0003"]


async def test_cada_consulta_trae_solo_lo_nuevo(client):
    token = await _token(client)
    await _escanear(client, f"{PREFIJO}0001")
    primera = (await _ver(client, token, "60_1,60_2")).json()

    await _escanear(client, f"{PREFIJO}0002")
    segunda = (await _ver(client, token, "60_1,60_2", desde=primera["ultimo_id"])).json()
    tercera = (await _ver(client, token, "60_1,60_2", desde=segunda["ultimo_id"])).json()

    assert [p["ultimos_4"] for p in primera["paquetes"]] == ["0001"]
    assert [p["ultimos_4"] for p in segunda["paquetes"]] == ["0002"]
    assert tercera["paquetes"] == [] and tercera["ultimo_id"] == segunda["ultimo_id"]


async def test_el_cursor_avanza_aunque_el_paquete_sea_de_otra_zona(client):
    token = await _token(client)
    await _escanear(client, f"{PREFIJO}0002")  # 60_2, la persona mira 60_1
    r = (await _ver(client, token, "60_1")).json()
    assert r["paquetes"] == []
    assert r["ultimo_id"] > 0  # no lo vuelve a revisar en la siguiente consulta


async def test_zonas_para_elegir(client):
    zonas = (await client.get(f"{URL}/{await _token(client)}/zonas")).json()
    assert len(zonas) == 33
    assert zonas[0] == "60_1"


async def test_enlace_inventado_o_vencido_no_muestra_nada(client):
    assert (await _ver(client, "no-existe", "60_1")).status_code == 404
    assert (await client.get(f"{URL}/no-existe/zonas")).status_code == 404

    token = await _token(client)
    async with AsyncSessionLocal() as db:
        await db.execute(update(EnlaceVista).where(EnlaceVista.token == token)
                         .values(expira=datetime(2020, 1, 1, tzinfo=UTC)))
        await db.commit()
    assert (await _ver(client, token, "60_1")).status_code == 404


async def test_la_vista_no_pide_sesion_pero_crear_el_enlace_si(client):
    token = await _token(client)
    app.dependency_overrides.pop(vista_router._auth.dependency, None)

    assert (await _ver(client, token, "60_1")).status_code == 200
    assert (await client.post(f"{URL}/enlace")).status_code in (401, 403)
