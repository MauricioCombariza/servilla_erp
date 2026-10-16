"""Recorrido de punta a punta del flujo de paquetes (FLUJO.md), por la API y en orden:
base de despacho → sectorización → sesión de iMile → tulas y lecturas → ingreso en iMile
→ destino → vista por zonas con el QR → cierre de la tula → mensajeros y zonas → lista
de seriales por mensajero (lo que usará el 3.3).

El ingreso en iMile va contra el iMile FALSO de tests/fake_imile.py: nunca contra
ds.imile.com. Cada prueba es un paso y depende de las anteriores (corren en el orden del
archivo); con `-x` el recorrido se detiene en el primer paso que falle.

Fuera del recorrido porque aún no están construidos: 2.3 (descarga de la tula en
dsOffloadingScan; el total esperado se indica a mano) y 3.3 (asignación en assignDA).

Se corre con scripts/e2e_flujo_paquetes.sh (base temporal) o con `pytest -m e2e`.
"""
from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.enlaces_vista import EnlaceVista
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.personal import Personal
from app.models.tulas import Tula
from app.routers import imile_sesion as imile_sesion_router
from app.routers import paquetes_despacho as paquetes_router
from app.routers import tulas as tulas_router
from app.routers import vista_zonas as vista_router
from app.services import tulas_service
from app.services.asignacion_zonas_service import hoy
from app.services.imile_ingreso import ImileIngreso
from app.services.imile_sesion import ImileSesion
from tests.fake_imile import CLAVE, USUARIO, _FakeImile, servidor_fake_imile

pytestmark = pytest.mark.e2e

QUIEN_ESCANEA = "test-e2e-mariela"
MENSAJEROS = {"E2E1": "Mensajero E2E Uno", "E2E2": "Mensajero E2E Dos"}

# Base de despacho del día: serial → (dirección, zona esperada). Los seriales BLOQ… y
# NOEXISTE… hacen que el iMile falso responda como el real con los bloqueos 1121 y 1119.
BASE = {
    "TESTE2E-0001": ("CL 63 # 27-12", "60_1"),
    "TESTE2E-0002": ("CL 64 # 20-11", "60_2"),
    "TESTE2E-0003": ("CL 64 # 20-31", "60_2"),
    "TESTE2E-0004": ("CR 20 # 66-15", "60_4"),
    "TESTE2E-0005": ("CL 64 # 25-12", "60_13"),
    "TESTE2E-0006": ("calle 95 # 49-22", "90_2"),
    "TESTE2E-0007": ("CL 21 33 40", None),             # Puente Aranda: fuera de zona
    "TESTE2E-0008": ("CR 7 # 32-16", None),            # Santa Fe: fuera de zona
    "TESTE2E-0009": ("lote sin numero vereda", None),  # sin sector: se corrige a mano
    "BLOQ-E2E-0010": ("CL 63 # 27-12", "60_1"),         # iMile: 1121 → repetido
    "NOEXISTE-E2E-0011": ("CL 64 # 20-11", "60_2"),     # iMile: 1119 → error
}
SIN_SECTOR = "TESTE2E-0009"
CORRECCION = ("CL 64 # 25-12", "60_13")
NO_EN_TABLA = "TESTE2E-9999"

# Lo que se va acumulando a lo largo del recorrido (ids de tulas, token del QR…)
estado: dict = {}


def _excel(filas: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(filas[0]))
    for fila in filas:
        ws.append(list(fila.values()))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _base_whatsapp() -> bytes:
    """Mismas columnas de la base que llega por WhatsApp (dirección en `Address`)."""
    return _excel([
        {"Waybill number": s, "Recipient's name": f"Cliente {s[-4:]}",
         "Customer phone": "3000000000", "Address": d}
        for s, (d, _) in BASE.items()
    ])


async def _limpiar():
    seriales = [*BASE, NO_EN_TABLA]
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario == QUIEN_ESCANEA))  # cascada a seriales
        await db.execute(delete(EnlaceVista).where(EnlaceVista.usuario == QUIEN_ESCANEA))
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.in_(seriales)))
        await db.execute(delete(Personal).where(Personal.codigo.in_(list(MENSAJEROS))))  # cascada a asignaciones
        await db.commit()


def _sesion(base_url: str, tmp_dir) -> ImileSesion:
    return ImileSesion(base_url=base_url, state_path=tmp_dir / "sesion.json", login_timeout_ms=3_000,
                       espera_carga_ms=200, recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)


@pytest.fixture(scope="module", autouse=True)
async def recorrido(tmp_path_factory):
    """Usuarios fijos en vez de iniciar sesión, iMile falso en vez del real y datos de
    prueba limpios antes y después."""
    usuario = {"username": QUIEN_ESCANEA, "rol": "mensajero"}
    deps = [paquetes_router._auth, paquetes_router._auth_destino, tulas_router._auth,
            vista_router._auth, imile_sesion_router._auth]
    for d in deps:
        app.dependency_overrides[d.dependency] = lambda: usuario

    await _limpiar()
    async with AsyncSessionLocal() as db:
        for i, (codigo, nombre) in enumerate(MENSAJEROS.items()):
            db.add(Personal(codigo=codigo, nombre_completo=nombre, identificacion=f"TEST-E2E-{i}",
                            tipo_personal="mensajero", activo=True))
        await db.commit()

    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("imile")
    _FakeImile.ingresados.clear()
    with servidor_fake_imile() as url:
        sesion = _sesion(url, tmp)
        estado["imile_url"] = url
        estado["ingreso_ok"] = ImileIngreso(sesion=sesion, espera_respuesta_ms=5_000)
        # iMile "caído": nadie escucha en ese puerto
        caida = _sesion("http://127.0.0.1:9", tmp)
        estado["ingreso_caido"] = ImileIngreso(sesion=caida, espera_respuesta_ms=1_000)
        mp.setattr(settings, "imile_user", USUARIO)
        mp.setattr(settings, "imile_pass", CLAVE)
        mp.setattr(settings, "imile_ingreso_activo", True)
        mp.setattr(imile_sesion_router, "imile_sesion", sesion)
        mp.setattr(tulas_service, "imile_ingreso", estado["ingreso_ok"])
        try:
            yield
        finally:
            mp.undo()
            await sesion.cerrar()
            await caida.cerrar()
            await _limpiar()
            for d in deps:
                app.dependency_overrides.pop(d.dependency, None)


async def _leer(client, serial: str) -> dict:
    r = await client.post(f"/api/tulas/{estado['tula']}/seriales", json={"serial": serial})
    assert r.status_code == 200, r.text
    return r.json()


# ── Etapa 1: base de despacho ─────────────────────────────────────────────────

async def test_1_1_base_con_columnas_equivocadas_se_rechaza(client):
    archivo = _excel([{"Guia": "X1", "Cliente": "Ana", "Direccion": "CL 63 # 27-12"}])
    r = await client.post("/api/paquetes-despacho/cargar", data={"f_emi": hoy().isoformat()},
                          files={"file": ("otra_cosa.xlsx", archivo)})

    assert r.status_code == 400
    faltantes = {f.split(" ")[0] for f in r.json()["detail"]["faltantes"]}
    assert faltantes == {"serial", "nombre", "telefono", "direccion"}
    assert r.json()["detail"]["columnas_archivo"] == ["Guia", "Cliente", "Direccion"]


async def test_1_1_a_1_3_subir_la_base_la_guarda_y_la_sectoriza(client):
    r = await client.post("/api/paquetes-despacho/cargar", data={"f_emi": hoy().isoformat()},
                          files={"file": ("DESPACHO SERVILLA E2E.xlsx", _base_whatsapp())})

    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["total"], body["creados"], body["reemplazados"]) == (len(BASE), len(BASE), 0)
    assert body["sin_sector"] == [{"serial": SIN_SECTOR, "direccion": BASE[SIN_SECTOR][0]}]
    assert body["devoluciones"] == 3  # 0007, 0008 y el sin sector

    paquetes = (await client.get("/api/paquetes-despacho/", params={"f_emi": hoy().isoformat()})).json()
    zonas = {p["serial"]: p["zona"] for p in paquetes if p["serial"] in BASE}
    assert zonas == {s: z for s, (_, z) in BASE.items()}
    assert {p["estado"] for p in paquetes if p["serial"] in BASE} == {"sin gestión"}


async def test_1_2_subir_otra_vez_la_misma_base_reemplaza_sin_duplicar(client):
    r = await client.post("/api/paquetes-despacho/cargar", data={"f_emi": hoy().isoformat()},
                          files={"file": ("DESPACHO SERVILLA E2E.xlsx", _base_whatsapp())})

    assert (r.json()["creados"], r.json()["reemplazados"]) == (0, len(BASE))


async def test_1_4_corregir_la_direccion_sin_sector(client):
    r = await client.patch(f"/api/paquetes-despacho/{SIN_SECTOR}/direccion", json={"direccion": CORRECCION[0]})

    assert r.status_code == 200
    assert (r.json()["localidad"], r.json()["zona"]) == ("Barrios Unidos", CORRECCION[1])


async def test_1_4_descargas_exportar_y_devoluciones(client):
    exportar = await client.get("/api/paquetes-despacho/exportar", params={"f_emi": hoy().isoformat()})
    devoluciones = await client.get("/api/paquetes-despacho/devoluciones", params={"f_emi": hoy().isoformat()})

    assert exportar.status_code == 200
    assert devoluciones.status_code == 200
    filas = list(load_workbook(BytesIO(devoluciones.content)).active.iter_rows(values_only=True))
    seriales = {str(f[0]) for f in filas[1:]}
    # Tras la corrección, el 0009 ya tiene zona: solo quedan los dos fuera de zona
    assert {"TESTE2E-0007", "TESTE2E-0008"} <= seriales
    assert SIN_SECTOR not in seriales


# ── Etapa 2: tulas e ingreso en iMile (falso) ─────────────────────────────────

async def test_2_0_sesion_de_imile_queda_conectada_y_en_espanol(client):
    assert estado["imile_url"].startswith("http://127.0.0.1:")  # nunca el iMile real

    antes = (await client.get("/api/imile-sesion/estado")).json()
    r = await client.post("/api/imile-sesion/conectar")

    assert antes["conectado"] is False
    assert r.status_code == 200, r.text
    assert (r.json()["conectado"], r.json()["idioma"]) == (True, "Español")


async def test_2_8_abrir_tula_con_total_esperado(client):
    # 2.3 no está construido: el total que daría iMile al descargar la tula se indica a mano
    r = await client.post("/api/tulas/", json={"codigo": "BAG-E2E-1", "total_esperado": 10})

    assert r.status_code == 201, r.text
    assert (r.json()["contador"], r.json()["sin_etiqueta"]) == (10, False)
    estado["tula"] = r.json()["id"]
    assert (await client.get("/api/tulas/abierta")).json()["id"] == estado["tula"]


async def test_2_4_a_2_6_leer_los_paquetes_de_la_tula(client):
    seriales = [s for s in BASE if s not in ("TESTE2E-0007", "TESTE2E-0008")] + [NO_EN_TABLA]
    lecturas = {s: await _leer(client, s) for s in seriales}

    # 2.4: el contador baja desde 10
    assert [lecturas[s]["tula"]["contador"] for s in seriales] == list(range(9, -1, -1))
    # 2.5: resultado del ingreso en iMile de cada lectura
    imile = {s: lecturas[s]["imile"]["estado"] for s in seriales}
    assert imile == {**{s: "ok" for s in seriales}, "BLOQ-E2E-0010": "repetido", "NOEXISTE-E2E-0011": "error"}
    assert lecturas["NOEXISTE-E2E-0011"]["imile"]["mensaje"] == "Sin información de pedido()"
    # 2.6: destino (últimos 4, zona, avisos)
    d1 = lecturas["TESTE2E-0001"]["destino"]
    assert (d1["ultimos_4"], d1["zona"], d1["en_tabla"], d1["aviso"]) == ("0001", "60_1", True, None)
    assert lecturas[SIN_SECTOR]["destino"]["zona"] == CORRECCION[1]  # ya con la dirección corregida
    nueva = lecturas[NO_EN_TABLA]["destino"]
    assert (nueva["en_tabla"], nueva["aviso"]) == (False, "No está en la tabla")
    # El serial que no está en la tabla igual se ingresó en iMile, y solo llegó al iMile falso
    assert _FakeImile.ingresados == {s for s in seriales if not s.startswith(("BLOQ", "NOEXISTE"))}


async def test_2_5_la_ventana_de_bloqueo_se_cancela_y_nunca_se_confirma(client):
    async with estado["ingreso_ok"]._sesion.usar() as page:
        assert await page.locator("#bloqueo").count() == 0
        assert await page.evaluate("localStorage.getItem('confirmado')") is None


async def test_2_4_un_serial_ya_leido_no_se_vuelve_a_contar(client):
    r = await _leer(client, " TESTE2E-0001 ")  # con espacios, como los manda a veces el lector

    assert r["ya_escaneado"] is True
    assert r["tula"]["contador"] == 0


async def test_2_5_con_imile_caido_la_lectura_cuenta_y_se_reintenta(client, monkeypatch):
    monkeypatch.setattr(tulas_service, "imile_ingreso", estado["ingreso_caido"])
    r = await _leer(client, "TESTE2E-0007")

    assert r["imile"]["estado"] == "error"
    assert r["tula"]["contador"] == -1  # llegó uno más de los esperados: igual cuenta
    assert r["destino"]["aviso"] == "Fuera de zona"

    monkeypatch.setattr(tulas_service, "imile_ingreso", estado["ingreso_ok"])
    reintento = await client.post(f"/api/tulas/{estado['tula']}/seriales/TESTE2E-0007/reintentar-imile")
    assert reintento.json()["imile_estado"] == "ok"
    assert "TESTE2E-0007" in _FakeImile.ingresados


async def test_2_7_cada_persona_ve_solo_sus_zonas_con_el_qr(client):
    token = (await client.post("/api/escaneo-vista/enlace")).json()["token"]
    estado["token"] = token
    url = f"/api/escaneo-vista/{token}/paquetes"

    zonas = (await client.get(f"/api/escaneo-vista/{token}/zonas")).json()
    a = (await client.get(url, params={"zonas": "60_1,60_2"})).json()
    b = (await client.get(url, params={"zonas": "90_2"})).json()

    assert {"60_1", "60_2", "90_2"} <= set(zonas)
    fuera = {"9999", "0007"}  # no está en la tabla · fuera de zona: los ven todos
    assert {p["ultimos_4"] for p in a["paquetes"]} == {"0001", "0002", "0003", "0010", "0011", *fuera}
    assert {p["ultimos_4"] for p in b["paquetes"]} == {"0006", *fuera}
    assert {p["aviso"] for p in a["paquetes"] if p["ultimos_4"] in fuera} == {"Fuera de zona"}
    # 60_4 (0004) y 60_13 (0005, 0009) no los eligió nadie: nadie los ve
    estado["ultimo_id_a"] = a["ultimo_id"]
    assert (await client.get(url, params={"zonas": "60_1,60_2", "desde": a["ultimo_id"]})).json()["paquetes"] == []
    assert (await client.get("/api/escaneo-vista/inventado/paquetes", params={"zonas": "60_1"})).status_code == 404


async def test_2_8_cerrar_la_tula_con_su_resumen(client):
    r = await client.post(f"/api/tulas/{estado['tula']}/cerrar")

    assert r.status_code == 200
    body = r.json()
    assert (body["estado"], body["total_esperado"], body["leidos"], body["diferencia"]) == ("cerrada", 10, 11, -1)
    por_serial = {s["serial"]: s["imile_estado"] for s in body["seriales"]}
    assert len(por_serial) == 11
    assert por_serial["TESTE2E-0007"] == "ok"  # el reintento quedó guardado
    lectura = await client.post(f"/api/tulas/{estado['tula']}/seriales", json={"serial": "TESTE2E-0008"})
    assert lectura.status_code == 409  # una tula cerrada no recibe más paquetes


async def test_2_8_tula_sin_etiqueta_y_confirmar_antes_de_abrir_otra(client):
    sin_etiqueta = (await client.post("/api/tulas/", json={"codigo": None})).json()
    estado["tula"] = sin_etiqueta["id"]
    r = await _leer(client, "TESTE2E-0008")

    assert (sin_etiqueta["sin_etiqueta"], sin_etiqueta["contador"]) == (True, 0)
    assert r["tula"]["contador"] == 1  # sin total: el contador sube

    # La persona B ve el nuevo "Fuera de zona" en su siguiente consulta, y solo ese
    nuevos = (await client.get(f"/api/escaneo-vista/{estado['token']}/paquetes",
                               params={"zonas": "60_1,60_2", "desde": estado["ultimo_id_a"]})).json()
    assert [p["ultimos_4"] for p in nuevos["paquetes"]] == ["0008"]

    otra = await client.post("/api/tulas/", json={"codigo": "BAG-E2E-2"})
    assert otra.status_code == 409
    assert otra.json()["detail"]["tula_abierta"]["id"] == sin_etiqueta["id"]
    otra = await client.post("/api/tulas/", json={"codigo": "BAG-E2E-2", "cerrar_anterior": True})
    assert otra.status_code == 201
    anterior = (await client.get(f"/api/tulas/{sin_etiqueta['id']}")).json()
    assert (anterior["estado"], anterior["leidos"], anterior["diferencia"]) == ("cerrada", 1, None)
    await client.post(f"/api/tulas/{otra.json()['id']}/cerrar")

    tulas = (await client.get("/api/tulas/", params={"fecha": hoy().isoformat()})).json()
    assert {t["codigo"] for t in tulas if t["usuario"] == QUIEN_ESCANEA} == {"BAG-E2E-1", None, "BAG-E2E-2"}


# ── Etapa 3: mensajeros (con el QR del día, sin sesión) ───────────────────────

async def test_3_1_codigo_del_mensajero_muestra_su_nombre(client):
    qr = f"/api/asignacion-qr/{estado['token']}"

    assert (await client.get(f"{qr}/mensajero/E2E1")).json()["nombre"] == "Mensajero E2E Uno"
    assert (await client.get(f"{qr}/mensajero/ZZZZ")).status_code == 404
    assert (await client.get("/api/asignacion-qr/inventado/mensajero/E2E1")).status_code == 404


async def test_3_2_zonas_choque_y_reasignacion(client):
    qr = f"/api/asignacion-qr/{estado['token']}"

    uno = await client.put(f"{qr}/mensajero/E2E1", json={"zonas": ["60_1", "60_2"]})
    choque = await client.put(f"{qr}/mensajero/E2E2", json={"zonas": ["60_2", "90_2"]})
    reasignar = await client.put(f"{qr}/mensajero/E2E2", json={"zonas": ["60_2", "90_2"], "reasignar": True})

    assert uno.json()["zonas"] == ["60_1", "60_2"]
    assert choque.status_code == 409
    assert choque.json()["detail"]["choques"] == [{"zona": "60_2", "codigo": "E2E1", "nombre": "Mensajero E2E Uno"}]
    assert reasignar.json()["zonas"] == ["60_2", "90_2"]
    assert (await client.get(f"{qr}/mensajero/E2E1")).json()["zonas"] == ["60_1"]

    tablero = {z["zona"]: z for z in (await client.get(f"{qr}/")).json()}
    assert len(tablero) == 33
    assert (tablero["60_1"]["mensajero"]["codigo"], tablero["60_1"]["paquetes_leidos"]) == ("E2E1", 2)
    assert (tablero["60_2"]["mensajero"]["codigo"], tablero["60_2"]["paquetes_leidos"]) == ("E2E2", 3)
    assert (tablero["90_2"]["mensajero"]["codigo"], tablero["90_2"]["paquetes_leidos"]) == ("E2E2", 1)


async def test_3_2_pistolear_seriales_a_otro_mensajero_y_deshacer(client):
    qr = f"/api/asignacion-qr/{estado['token']}"

    sin_dueno = (await client.post(f"{qr}/mensajero/E2E1/seriales", json={"serial": "TESTE2E-0004"})).json()
    de_otro = (await client.post(f"{qr}/mensajero/E2E1/seriales", json={"serial": "TESTE2E-0002"})).json()
    deshacer = await client.delete(f"{qr}/mensajero/E2E1/seriales/TESTE2E-0002")
    queda = (await client.post(f"{qr}/mensajero/E2E1/seriales", json={"serial": "TESTE2E-0003"})).json()

    assert (sin_dueno["zona"], sin_dueno["mensajero_anterior"]) == ("60_4", None)
    assert de_otro["mensajero_anterior"] == {"codigo": "E2E2", "nombre": "Mensajero E2E Dos"}
    assert deshacer.status_code == 204
    assert queda["mensajero_anterior"]["codigo"] == "E2E2"


async def test_3_3_lista_final_de_seriales_por_mensajero(client):
    """Es la lista que el 3.3 (aún no construido) asignará en iMile."""
    qr = f"/api/asignacion-qr/{estado['token']}"

    async def seriales(codigo):
        return {(s["serial"], s["origen"]) for s in (await client.get(f"{qr}/mensajero/{codigo}/seriales")).json()}

    assert await seriales("E2E1") == {
        ("TESTE2E-0001", "zona"), ("BLOQ-E2E-0010", "zona"),         # su zona 60_1
        ("TESTE2E-0004", "serial"), ("TESTE2E-0003", "serial"),      # pistoleados
    }
    assert await seriales("E2E2") == {
        ("TESTE2E-0002", "zona"), ("NOEXISTE-E2E-0011", "zona"),     # 60_2 sin el 0003
        ("TESTE2E-0006", "zona"),                                    # 90_2
    }
