"""Tests de integración de la asignación de zonas (Pasos 3.1 y 3.2): código → nombre del
mensajero, cada zona completa a un solo mensajero por día y reasignación serial por
serial. Necesitan la BD con las migraciones 031–038."""
import asyncio
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
from app.services import asignacion_imile_service
from app.services.imile_asignacion import MensajeroImileNoEncontradoError
from app.services.imile_ingreso import EstadoIngreso, ResultadoIngreso

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
                        "fecha": FECHA.isoformat(), "zonas": [], "nombre_imile": None}


@pytest.mark.parametrize("codigo", ["T999", "T903"])  # inexistente · inactivo
async def test_codigo_inexistente_o_inactivo(client, codigo):
    r = await client.get(f"{URL}/mensajero/{codigo}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Mensajero no encontrado"


async def test_no_expone_datos_personales(client):
    body = (await client.get(f"{URL}/mensajero/T901")).json()
    assert set(body) == {"codigo", "nombre", "fecha", "zonas", "nombre_imile"}


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

    assert len(r) == 28
    assert por_zona["60_1"] == {"zona": "60_1", "paquetes_leidos": 2,
                                "mensajero": {"codigo": "T901", "nombre": "Mensajero Prueba Uno"}}
    assert por_zona["60_2"]["paquetes_leidos"] == 1 and por_zona["60_2"]["mensajero"] is None


# ── Reasignación serial por serial ────────────────────────────────────────────

async def _tula_con(*seriales_y_zonas, estado="abierta"):
    async with AsyncSessionLocal() as db:
        tula = Tula(codigo="BAG-REASIG", usuario="test-asigna", fecha=FECHA, estado=estado)
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


# ── Total de paquetes por mensajero ───────────────────────────────────────────

async def _totales(client):
    r = await client.get(f"{URL}/mensajeros", params={"fecha": FECHA.isoformat()})
    assert r.status_code == 200
    return {t["codigo"]: (t["zonas"], t["paquetes"], t["reasignados"]) for t in r.json() if t["codigo"] in CODIGOS}


async def test_total_por_mensajero_cuenta_sus_zonas_y_los_reasignados(client):
    await _asignar(client, "T901", ["60_1", "60_2"])
    await _tula_con(("TEST32-A001", "60_1"), ("TEST32-B002", "60_2"), ("TEST32-C003", "60_3"))
    await _tula_con(("TEST32-A001", "60_1"), estado="cerrada")  # leído en dos tulas: cuenta una vez
    assert await _totales(client) == {"T901": (["60_1", "60_2"], 2, 0)}

    await _pistolear(client, "T902", "TEST32-B002")  # T902 sin zonas, solo con un reasignado

    assert await _totales(client) == {"T901": (["60_1", "60_2"], 1, 0), "T902": ([], 1, 1)}
    for codigo, (_, paquetes, _r) in (await _totales(client)).items():
        assert len(await _seriales(client, codigo)) == paquetes  # misma regla que la lista del mensajero


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


# ── Paso 3.3: asignar en iMile ────────────────────────────────────────────────

class _ImileFalso:
    """Reemplaza a imile_asignacion: guarda lo que se mandó y responde según el serial."""

    def __init__(self, nombres_validos=("Mensajero Prueba Uno", "Mensajero Prueba Dos")):
        self.enviados: list[tuple[str, str]] = []
        self.nombres_validos = nombres_validos

    async def asignar(self, nombre, serial):
        if nombre not in self.nombres_validos:
            raise MensajeroImileNoEncontradoError(f'"{nombre}" no está en la lista de mensajeros de iMile')
        self.enviados.append((nombre, serial))
        if serial.endswith("X"):
            return ResultadoIngreso(EstadoIngreso.ERROR, "Sin información de pedido()", "1119")
        return ResultadoIngreso(EstadoIngreso.OK)


@pytest.fixture
def imile(monkeypatch):
    falso = _ImileFalso()
    monkeypatch.setattr(asignacion_imile_service, "imile_asignacion", falso)
    monkeypatch.setattr(asignacion_imile_service.settings, "imile_asignacion_activa", True)
    return falso


async def _enviar_a_imile(client, codigo):
    r = await client.post(f"{URL}/mensajero/{codigo}/imile", params={"fecha": FECHA.isoformat()})
    assert r.status_code == 202, r.text
    for _ in range(100):
        estado = (await client.get(f"{URL}/mensajero/{codigo}/imile", params={"fecha": FECHA.isoformat()})).json()
        if not estado["en_curso"]:
            return estado
        await asyncio.sleep(0.02)
    raise AssertionError("el envío a iMile no terminó")


async def _estados_imile(client, codigo):
    r = await client.get(f"{URL}/mensajero/{codigo}/seriales", params={"fecha": FECHA.isoformat()})
    return {s["serial"]: s["imile_estado"] for s in r.json()}


async def test_asignar_en_imile_manda_cada_serial_y_guarda_el_resultado(client, imile):
    await _asignar(client, "T901", ["60_1"])
    await _tula_con(("TEST32-A001", "60_1"), ("TEST32-B00X", "60_1"))

    envio = await _enviar_a_imile(client, "T901")

    assert {k: envio[k] for k in ("total", "hechos", "asignados", "fallidos", "error")} == \
        {"total": 2, "hechos": 2, "asignados": 1, "fallidos": 1, "error": None}
    assert imile.enviados == [("Mensajero Prueba Uno", "TEST32-A001"), ("Mensajero Prueba Uno", "TEST32-B00X")]
    assert await _estados_imile(client, "T901") == {"TEST32-A001": "ok", "TEST32-B00X": "error"}

    # La segunda vez solo se reintenta el que falló
    imile.enviados.clear()
    await _enviar_a_imile(client, "T901")
    assert imile.enviados == [("Mensajero Prueba Uno", "TEST32-B00X")]


async def test_si_el_paquete_pasa_a_otro_mensajero_hay_que_volver_a_mandarlo(client, imile):
    await _asignar(client, "T901", ["60_1"])
    await _tula_con(("TEST32-A001", "60_1"))
    await _enviar_a_imile(client, "T901")

    await _pistolear(client, "T902", "TEST32-A001")
    r = await client.get(f"{URL}/mensajero/T902/seriales", params={"fecha": FECHA.isoformat()})
    assert (r.json()[0]["imile_estado"], r.json()[0]["imile_mensaje"]) == (None, "En iMile quedó con Mensajero Prueba Uno")

    imile.enviados.clear()
    await _enviar_a_imile(client, "T902")
    assert imile.enviados == [("Mensajero Prueba Dos", "TEST32-A001")]
    assert await _estados_imile(client, "T902") == {"TEST32-A001": "ok"}


async def test_mensajero_que_no_esta_en_imile_detiene_el_envio_y_se_corrige_con_su_nombre_imile(client, imile):
    imile.nombres_validos = ("Juan P. iMile",)
    await _asignar(client, "T901", ["60_1"])
    await _tula_con(("TEST32-A001", "60_1"))

    envio = await _enviar_a_imile(client, "T901")
    assert (envio["hechos"], envio["error"]) == (0, '"Mensajero Prueba Uno" no está en la lista de mensajeros de iMile')
    assert await _estados_imile(client, "T901") == {"TEST32-A001": None}

    r = await client.put(f"{URL}/mensajero/T901/nombre-imile", json={"nombre_imile": "  Juan P.  iMile "})
    assert r.json()["nombre_imile"] == "Juan P. iMile"
    envio = await _enviar_a_imile(client, "T901")
    assert (envio["nombre_imile"], envio["asignados"]) == ("Juan P. iMile", 1)


async def test_sin_pendientes_no_manda_nada(client, imile):
    envio = await _enviar_a_imile(client, "T901")
    assert (envio["total"], envio["en_curso"]) == (0, False)
    assert imile.enviados == []


async def test_asignacion_en_imile_apagada(client, monkeypatch):
    monkeypatch.setattr(asignacion_imile_service.settings, "imile_asignacion_activa", False)
    r = await client.post(f"{URL}/mensajero/T901/imile")
    assert r.status_code == 503
