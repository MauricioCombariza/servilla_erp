"""Tests de integración de la asignación de zonas (Pasos 3.1 y 3.2): código → nombre del
mensajero, cada zona completa a un solo mensajero por día y reasignación serial por
serial. Necesitan la BD con las migraciones 031–038."""
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, select, update

from app.database import AsyncSessionLocal
from app.main import app
from app.models.asignaciones_zona import AsignacionZona
from app.models.enlaces_vista import EnlaceVista
from app.models.personal import Personal
from app.models.tulas import Tula, TulaSerial
from app.routers import asignacion_zonas as router_module
from app.routers import vista_zonas as vista_router

URL = "/api/asignacion-zonas"
FECHA = date(2026, 10, 8)
CODIGOS = {"T901": "Mensajero Prueba Uno", "T902": "Mensajero Prueba Dos", "T903": "Mensajero Inactivo"}


@pytest.fixture(autouse=True)
async def preparar():
    app.dependency_overrides[router_module._auth.dependency] = lambda: {"username": "test-asigna", "rol": "logistica"}
    await _limpiar()
    async with AsyncSessionLocal() as db:
        for i, (codigo, nombre) in enumerate(CODIGOS.items()):
            db.add(Personal(codigo=codigo, nombre_completo=nombre, identificacion=f"TEST-ID-{i}",
                            tipo_personal="mensajero", activo=codigo != "T903"))
        await db.commit()
    yield
    await _limpiar()
    app.dependency_overrides.pop(router_module._auth.dependency, None)


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario == "test-asigna"))
        await db.execute(delete(Personal).where(Personal.codigo.in_(list(CODIGOS))))  # cascada a asignaciones
        await db.commit()


async def _asignar(client, codigo, zonas, reasignar=False):
    return await client.put(f"{URL}/mensajero/{codigo}",
                            json={"zonas": zonas, "fecha": FECHA.isoformat(), "reasignar": reasignar})


# ── 3.1 ───────────────────────────────────────────────────────────────────────

async def test_codigo_del_mensajero_muestra_su_nombre(client):
    r = await client.get(f"{URL}/mensajero/ T901 ", params={"fecha": FECHA.isoformat()})
    assert r.status_code == 200
    assert r.json() == {"codigo": "T901", "nombre": "Mensajero Prueba Uno",
                        "fecha": FECHA.isoformat(), "zonas": []}


@pytest.mark.parametrize("codigo", ["T999", "T903"])  # inexistente · inactivo
async def test_codigo_inexistente_o_inactivo(client, codigo):
    r = await client.get(f"{URL}/mensajero/{codigo}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Mensajero no encontrado"


async def test_no_expone_datos_personales(client):
    body = (await client.get(f"{URL}/mensajero/T901")).json()
    assert set(body) == {"codigo", "nombre", "fecha", "zonas"}


# ── 3.2 ───────────────────────────────────────────────────────────────────────

async def test_asignar_y_cambiar_las_zonas_de_un_mensajero(client):
    r = await _asignar(client, "T901", ["60_1", "60_2", "60_1"])
    assert r.json()["zonas"] == ["60_1", "60_2"]

    await _asignar(client, "T901", ["60_2", "60_3"])  # deja exactamente estas
    zonas = (await client.get(f"{URL}/mensajero/T901", params={"fecha": FECHA.isoformat()})).json()["zonas"]
    assert zonas == ["60_2", "60_3"]


async def test_una_zona_no_puede_tener_dos_mensajeros(client):
    await _asignar(client, "T901", ["60_1", "60_2"])

    r = await _asignar(client, "T902", ["60_2", "60_4"])
    assert r.status_code == 409
    assert r.json()["detail"]["choques"] == [{"zona": "60_2", "codigo": "T901", "nombre": "Mensajero Prueba Uno"}]
    zonas_t902 = (await client.get(f"{URL}/mensajero/T902", params={"fecha": FECHA.isoformat()})).json()["zonas"]
    assert zonas_t902 == []  # no se asignó nada

    r = await _asignar(client, "T902", ["60_2", "60_4"], reasignar=True)
    assert r.json()["zonas"] == ["60_2", "60_4"]
    zonas_t901 = (await client.get(f"{URL}/mensajero/T901", params={"fecha": FECHA.isoformat()})).json()["zonas"]
    assert zonas_t901 == ["60_1"]


async def test_zona_inexistente(client):
    r = await _asignar(client, "T901", ["60_1", "99_9"])
    assert r.status_code == 400
    assert r.json()["detail"]["zonas"] == ["99_9"]


async def test_las_asignaciones_son_por_dia(client):
    await _asignar(client, "T901", ["60_1"])
    otro_dia = await client.put(f"{URL}/mensajero/T902", json={"zonas": ["60_1"], "fecha": "2026-10-09"})
    assert otro_dia.status_code == 200


async def test_tablero_del_dia_con_mensajeros_y_paquetes_leidos(client):
    await _asignar(client, "T901", ["60_1"])
    async with AsyncSessionLocal() as db:
        tula = Tula(codigo="BAG-ASIG", usuario="test-asigna", fecha=FECHA, estado="abierta")
        db.add(tula)
        await db.flush()
        for i, zona in enumerate(["60_1", "60_1", "60_2", None]):
            db.add(TulaSerial(tula_id=tula.id, serial=f"TEST32-{i}", en_tabla=True, zona=zona))
        await db.commit()

    r = (await client.get(f"{URL}/", params={"fecha": FECHA.isoformat()})).json()
    por_zona = {z["zona"]: z for z in r}

    assert len(r) == 33
    assert por_zona["60_1"] == {"zona": "60_1", "paquetes_leidos": 2,
                                "mensajero": {"codigo": "T901", "nombre": "Mensajero Prueba Uno"}}
    assert por_zona["60_2"]["paquetes_leidos"] == 1 and por_zona["60_2"]["mensajero"] is None


# ── Reasignación serial por serial ────────────────────────────────────────────

async def _tula_con(*seriales_y_zonas):
    async with AsyncSessionLocal() as db:
        tula = Tula(codigo="BAG-REASIG", usuario="test-asigna", fecha=FECHA, estado="abierta")
        db.add(tula)
        await db.flush()
        for serial, zona in seriales_y_zonas:
            db.add(TulaSerial(tula_id=tula.id, serial=serial, en_tabla=True, zona=zona))
        await db.commit()


async def _pistolear(client, codigo, serial):
    return await client.post(f"{URL}/mensajero/{codigo}/seriales",
                             json={"serial": serial, "fecha": FECHA.isoformat()})


async def _seriales(client, codigo):
    r = await client.get(f"{URL}/mensajero/{codigo}/seriales", params={"fecha": FECHA.isoformat()})
    return [(s["serial"], s["origen"]) for s in r.json()]


async def test_pistolear_seriales_los_pasa_a_otro_mensajero(client):
    await _asignar(client, "T901", ["60_1"])
    await _asignar(client, "T902", ["60_2"])
    await _tula_con(("TEST32-A001", "60_1"), ("TEST32-B002", "60_1"), ("TEST32-C003", "60_2"))
    assert await _seriales(client, "T901") == [("TEST32-A001", "zona"), ("TEST32-B002", "zona")]

    r = (await _pistolear(client, "T902", " TEST32-A001 ")).json()

    assert (r["serial"], r["ultimos_4"], r["zona"], r["ya_era_suyo"]) == ("TEST32-A001", "A001", "60_1", False)
    assert r["mensajero_anterior"] == {"codigo": "T901", "nombre": "Mensajero Prueba Uno"}
    assert await _seriales(client, "T901") == [("TEST32-B002", "zona")]
    assert await _seriales(client, "T902") == [("TEST32-C003", "zona"), ("TEST32-A001", "serial")]


async def test_volver_a_pistolear_el_mismo_serial_avisa_que_ya_era_suyo(client):
    await _tula_con(("TEST32-A001", "60_1"))
    await _pistolear(client, "T902", "TEST32-A001")
    r = (await _pistolear(client, "T902", "TEST32-A001")).json()
    assert r["ya_era_suyo"] is True


async def test_un_serial_reasignado_se_puede_mover_otra_vez_o_devolver_a_su_zona(client):
    await _asignar(client, "T901", ["60_1"])
    await _tula_con(("TEST32-A001", "60_1"))
    await _pistolear(client, "T902", "TEST32-A001")

    r = (await _pistolear(client, "T901", "TEST32-A001")).json()  # se devuelve pistoleando
    assert r["mensajero_anterior"]["codigo"] == "T902"

    await _pistolear(client, "T902", "TEST32-A001")
    borrar = await client.delete(f"{URL}/mensajero/T902/seriales/TEST32-A001", params={"fecha": FECHA.isoformat()})
    assert borrar.status_code == 204
    assert await _seriales(client, "T901") == [("TEST32-A001", "zona")]  # volvió a su zona
    assert await _seriales(client, "T902") == []


async def test_se_puede_pistolear_un_serial_que_no_paso_por_ninguna_tula(client):
    r = (await _pistolear(client, "T902", "TEST32-SUELTO")).json()
    assert (r["zona"], r["mensajero_anterior"]) == (None, None)
    assert await _seriales(client, "T902") == [("TEST32-SUELTO", "serial")]


async def test_pistolear_con_mensajero_inexistente(client):
    assert (await _pistolear(client, "T999", "TEST32-A001")).status_code == 404


# ── Con el QR del día, sin iniciar sesión ─────────────────────────────────────

async def _qr(client) -> str:
    app.dependency_overrides[vista_router._auth.dependency] = lambda: {"username": "test-asigna"}
    token = (await client.post("/api/escaneo-vista/enlace")).json()["token"]
    app.dependency_overrides.pop(vista_router._auth.dependency, None)
    return token


async def test_con_el_qr_se_asignan_zonas_y_seriales_sin_sesion(client):
    token = await _qr(client)
    app.dependency_overrides.pop(router_module._auth.dependency, None)  # sin sesión del ERP
    qr = f"/api/asignacion-qr/{token}"

    nombre = (await client.get(f"{qr}/mensajero/T901")).json()["nombre"]
    zonas = (await client.put(f"{qr}/mensajero/T901", json={"zonas": ["60_1"], "fecha": FECHA.isoformat()})).json()
    serial = await client.post(f"{qr}/mensajero/T902/seriales", json={"serial": "TEST32-QR01", "fecha": FECHA.isoformat()})

    assert nombre == "Mensajero Prueba Uno"
    assert zonas["zonas"] == ["60_1"]
    assert serial.status_code == 200
    async with AsyncSessionLocal() as db:
        quien = (await db.execute(select(AsignacionZona.usuario).where(AsignacionZona.zona == "60_1",
                                                                      AsignacionZona.fecha == FECHA))).scalar_one()
        await db.execute(delete(EnlaceVista).where(EnlaceVista.usuario == "test-asigna"))
        await db.commit()
    assert quien == "qr:test-asigna"  # queda registrado de qué QR salió


async def test_qr_inventado_o_vencido_no_asigna_nada(client):
    app.dependency_overrides.pop(router_module._auth.dependency, None)
    r = await client.put("/api/asignacion-qr/no-existe/mensajero/T901", json={"zonas": ["60_1"]})
    assert r.status_code == 404

    token = await _qr(client)
    async with AsyncSessionLocal() as db:
        await db.execute(update(EnlaceVista).where(EnlaceVista.token == token)
                         .values(expira=datetime(2020, 1, 1, tzinfo=UTC)))
        await db.commit()
    assert (await client.get(f"/api/asignacion-qr/{token}/mensajero/T901")).status_code == 404
    async with AsyncSessionLocal() as db:
        await db.execute(delete(EnlaceVista).where(EnlaceVista.usuario == "test-asigna"))
        await db.commit()


async def test_sin_permiso(client):
    app.dependency_overrides.pop(router_module._auth.dependency, None)
    assert (await client.get(f"{URL}/mensajero/T901")).status_code in (401, 403)
