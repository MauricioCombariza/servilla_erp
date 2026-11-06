"""Paquetes con más de N días en instalaciones sin entregar: leídos en una tula y que todavía
no aparecen en seriales_gestion. Necesitan la BD con las migraciones hasta la 052."""
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.main import app
from app.models.devoluciones import Devolucion
from app.models.asignaciones_zona import AsignacionSerial, AsignacionZona
from app.models.gestiones import SerialGestion
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.personal import Personal
from app.models.tulas import Tula, TulaSerial
from app.routers import paquetes_estancados as router_module
from app.services import paquetes_estancados_service as svc

HOY = date(2026, 11, 6)
USUARIO = "test-estancados"
PREFIJO = "999000000"  # + 4 dígitos = serial de 13 dígitos válido
CODIGOS = {"E901": "Mensajero Estancado Uno", "E902": "Mensajero Estancado Dos"}


def _dia(n: int) -> date:
    return HOY - timedelta(days=n)


@pytest.fixture(autouse=True)
async def preparar(monkeypatch):
    app.dependency_overrides[router_module._auth.dependency] = lambda: {"username": USUARIO, "rol": "logistica"}
    monkeypatch.setattr(svc, "hoy_bogota", lambda: HOY)
    await _limpiar()
    yield
    await _limpiar()
    app.dependency_overrides.pop(router_module._auth.dependency, None)


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Tula).where(Tula.usuario == USUARIO))  # cascada a tula_seriales
        await db.execute(delete(SerialGestion).where(SerialGestion.serial.like(f"{PREFIJO}%")))
        await db.execute(delete(Devolucion).where(Devolucion.serial.like(f"{PREFIJO}%")))
        await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.like(f"{PREFIJO}%")))
        await db.execute(delete(Personal).where(Personal.codigo.in_(list(CODIGOS))))  # cascada a asignaciones
        await db.commit()


async def _personal() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        ids = {}
        for i, (codigo, nombre) in enumerate(CODIGOS.items()):
            p = Personal(codigo=codigo, nombre_completo=nombre, identificacion=f"TEST-EST-{i}",
                         tipo_personal="mensajero", activo=True)
            db.add(p)
            await db.flush()
            ids[codigo] = p.id
        await db.commit()
        return ids


async def _leer(serial: str, hace_dias: int, zona: str | None = "70_1"):
    """Lee el serial en una tula de hace `hace_dias` días (12:00 hora Bogotá)."""
    dia = _dia(hace_dias)
    async with AsyncSessionLocal() as db:
        tula = Tula(codigo=f"BAG-{serial}-{hace_dias}", usuario=USUARIO, fecha=dia, estado="cerrada")
        db.add(tula)
        await db.flush()
        db.add(TulaSerial(tula_id=tula.id, serial=serial, en_tabla=True, zona=zona,
                          fecha_escaneo=datetime.combine(dia, time(12), tzinfo=svc.TZ)))
        await db.commit()


async def _entregar(serial: str):
    async with AsyncSessionLocal() as db:
        db.add(SerialGestion(serial=serial, f_esc=HOY, planilla="TEST", cod_men="E901", tipo_gestion="Entrega",
                             fecha_creacion=datetime.now(svc.TZ), fecha_modificacion=datetime.now(svc.TZ)))
        await db.commit()


async def _seriales(**kw) -> list[str]:
    async with AsyncSessionLocal() as db:
        return [p.serial for p in (await svc.listar_estancados(db, hoy=HOY, **kw)).paquetes
                if p.serial.startswith(PREFIJO)]


async def test_mas_de_dos_dias_sin_entregar_aparece_y_al_entregarse_desaparece():
    await _leer(f"{PREFIJO}0001", 3)
    await _leer(f"{PREFIJO}0002", 2)  # justo 2 días: todavía no pasa
    await _leer(f"{PREFIJO}0003", 1)
    assert await _seriales() == [f"{PREFIJO}0001"]

    await _entregar(f"{PREFIJO}0001")
    assert await _seriales() == []


async def test_los_dias_cuentan_desde_el_primer_ingreso():
    await _leer(f"{PREFIJO}0001", 5)
    await _leer(f"{PREFIJO}0001", 1)  # se volvió a leer en otra tula
    async with AsyncSessionLocal() as db:
        [p] = [p for p in (await svc.listar_estancados(db, hoy=HOY)).paquetes if p.serial == f"{PREFIJO}0001"]
    assert p.dias == 5
    assert p.lecturas == 2


async def test_mensajero_por_zona_y_reasignacion_por_serial():
    ids = await _personal()
    await _leer(f"{PREFIJO}0026", 4, zona="70_1")
    await _leer(f"{PREFIJO}0019", 4, zona="70_1")
    await _leer(f"{PREFIJO}0014", 4, zona="70_9")  # zona sin mensajero
    async with AsyncSessionLocal() as db:
        db.add(AsignacionZona(fecha=_dia(3), zona="70_1", personal_id=ids["E901"], usuario=USUARIO))
        db.add(AsignacionSerial(fecha=_dia(3), serial=f"{PREFIJO}0019", personal_id=ids["E902"], usuario=USUARIO))
        # una asignación de la zona anterior al ingreso no cuenta
        db.add(AsignacionZona(fecha=_dia(10), zona="70_9", personal_id=ids["E901"], usuario=USUARIO))
        await db.commit()

    async with AsyncSessionLocal() as db:
        paquetes = {p.serial: p for p in (await svc.listar_estancados(db, hoy=HOY)).paquetes if p.serial.startswith(PREFIJO)}
    assert (paquetes[f"{PREFIJO}0026"].codigo, paquetes[f"{PREFIJO}0026"].origen_asignacion) == ("E901", "zona")
    assert (paquetes[f"{PREFIJO}0019"].codigo, paquetes[f"{PREFIJO}0019"].origen_asignacion) == ("E902", "serial")
    assert paquetes[f"{PREFIJO}0014"].codigo is None

    assert await _seriales(codigo="E901") == [f"{PREFIJO}0026"]
    assert await _seriales(codigo="") == [f"{PREFIJO}0014"]
    assert sorted(await _seriales(zona="70_1")) == [f"{PREFIJO}0019", f"{PREFIJO}0026"]


async def test_zona_sale_de_la_base_de_despacho_si_la_tula_no_la_tiene():
    await _leer(f"{PREFIJO}0001", 3, zona=None)
    async with AsyncSessionLocal() as db:
        db.add(PaqueteDespacho(serial=f"{PREFIJO}0001", zona="70_5", localidad="Suba", f_emi=_dia(4)))
        await db.commit()
        [p] = [p for p in (await svc.listar_estancados(db, hoy=HOY)).paquetes if p.serial == f"{PREFIJO}0001"]
    assert (p.zona, p.localidad) == ("70_5", "Suba")


async def test_api_y_excel(client):
    await _leer(f"{PREFIJO}0001", 3)
    r = await client.get("/api/paquetes-estancados", params={"zona": "70_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["corte"] == HOY.isoformat()
    assert [p["serial"] for p in body["paquetes"]] == [f"{PREFIJO}0001"]
    assert body["por_zona"][0] == {"clave": "70_1", "nombre": "70_1", "paquetes": 1, "max_dias": 3}
    assert body["por_mensajero"][0]["nombre"] == svc.SIN_ASIGNAR
    assert body["devoluciones_ocultas"] == 0

    r = await client.get("/api/paquetes-estancados/excel", params={"zona": "70_1"})
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


async def test_devoluciones_se_ocultan_salvo_que_se_pidan(client):
    await _leer(f"{PREFIJO}0001", 3)
    await _leer(f"{PREFIJO}0004", 3)
    async with AsyncSessionLocal() as db:
        db.add(Devolucion(serial=f"{PREFIJO}0004", estado="transito"))
        await db.commit()

    assert await _seriales() == [f"{PREFIJO}0001"]
    assert sorted(await _seriales(incluir_devoluciones=True)) == [f"{PREFIJO}0001", f"{PREFIJO}0004"]

    body = (await client.get("/api/paquetes-estancados", params={"zona": "70_1"})).json()
    assert body["devoluciones_ocultas"] == 1
    body = (await client.get("/api/paquetes-estancados",
                             params={"zona": "70_1", "incluir_devoluciones": "true"})).json()
    assert {p["serial"]: p["devolucion"] for p in body["paquetes"]} == {f"{PREFIJO}0001": None, f"{PREFIJO}0004": "transito"}


@pytest.mark.parametrize("serial, motivo", [
    ("2610212648301", svc.DESCARTE_TULA),       # código de tula leído como paquete
    ("21", svc.DESCARTE_FORMATO),               # lectura cortada
    ("IM100", svc.DESCARTE_FORMATO),
    ("610132689427", svc.DESCARTE_FORMATO),     # 12 dígitos
    ("36101426297867", svc.DESCARTE_FORMATO),   # dos lecturas pegadas
    ("3673671050801252", svc.DESCARTE_FORMATO),
    ("6101526556557", None),
    ("3671050777091", None),
    ("IM10000000731513", None),
])
def test_motivo_descarte_por_formato(serial, motivo):
    assert svc.motivo_descarte(serial, es_codigo_tula=False, en_base=True, rechazado_imile=False) == motivo


def test_motivo_descarte_rechazado_por_imile_y_fuera_de_la_base():
    assert svc.motivo_descarte("6101526556557", False, en_base=False, rechazado_imile=True) == svc.DESCARTE_RECHAZADO
    assert svc.motivo_descarte("6101526556557", False, en_base=True, rechazado_imile=True) is None
    assert svc.motivo_descarte("6101526556557", False, en_base=False, rechazado_imile=None) is None
    assert svc.motivo_descarte("9990000000001", True, en_base=False, rechazado_imile=False) == svc.DESCARTE_TULA


async def test_lecturas_descartadas_se_ocultan_salvo_que_se_pidan(client):
    await _leer(f"{PREFIJO}0001", 3)
    await _leer(f"{PREFIJO}12", 3)  # 11 dígitos: lectura cortada
    body = (await client.get("/api/paquetes-estancados", params={"zona": "70_1"})).json()
    assert [p["serial"] for p in body["paquetes"]] == [f"{PREFIJO}0001"]
    assert body["descartados_ocultos"] == 1

    body = (await client.get("/api/paquetes-estancados",
                             params={"zona": "70_1", "incluir_descartados": "true"})).json()
    assert {p["serial"]: p["motivo_descarte"] for p in body["paquetes"]} == {
        f"{PREFIJO}0001": None, f"{PREFIJO}12": svc.DESCARTE_FORMATO}
