"""Seguimiento de tareas y proyectos. Necesita la BD con las migraciones hasta la 053."""
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.database import AsyncSessionLocal
from app.main import app
from app.models.seguimiento import Proyecto, TareaRecurrente, TareaSeguimiento
from app.models.usuarios import Usuario
from app.routers import seguimiento as router_module
from app.services import seguimiento_service as svc

HOY = date(2026, 11, 12)  # jueves, semana ISO 46
PREFIJO = "[test-seg]"
USERS = {"test_seg_admin": "administrador", "test_seg_uno": "logistica", "test_seg_dos": "logistica"}


# ── Funciones puras ─────────────────────────────────────────────────────────

def test_semanas_en_anio():
    assert svc.semanas_en_anio(2026) == 53
    assert svc.semanas_en_anio(2027) == 52
    assert date(2026, 12, 31).isocalendar()[:2] == (2026, 53)


def test_distribuir_balanceado():
    desde, hasta = date(2026, 11, 16), date(2026, 12, 13)  # 4 semanas
    items = [svc.ItemReparto(p) for p in (8, 4, 4, 2, 2, 2, 2)]
    fechas = svc.distribuir(items, desde, hasta)
    carga: dict[date, float] = {}
    for it, f in zip(items, fechas):
        assert desde <= f <= hasta
        carga[svc.lunes_de(f)] = carga.get(svc.lunes_de(f), 0) + it.peso
    assert len(carga) == 4
    assert max(carga.values()) == 8  # la tarea de 8 h queda sola; ninguna semana se sobrecarga más
    assert sorted(carga.values()) == [4, 6, 6, 8]


def test_distribuir_secuencial_y_fijas():
    desde, hasta = date(2026, 11, 16), date(2026, 12, 13)
    items = [svc.ItemReparto(1) for _ in range(8)]
    fechas = svc.distribuir(items, desde, hasta, secuencial=True)
    assert fechas == sorted(fechas)  # respeta el orden
    assert len({svc.lunes_de(f) for f in fechas}) == 4
    fija = date(2026, 12, 10)
    fechas = svc.distribuir([svc.ItemReparto(1, fija), svc.ItemReparto(1)], desde, hasta)
    assert fechas[0] == fija
    assert svc.lunes_de(fechas[1]) == date(2026, 11, 16)


def test_distribuir_salta_festivo():
    # 2026-11-16 (lunes) es festivo en Colombia (Independencia de Cartagena, trasladado).
    fechas = svc.distribuir([svc.ItemReparto(1)], date(2026, 11, 16), date(2026, 11, 22))
    assert fechas == [date(2026, 11, 17)]


def test_fechas_recurrencia():
    # semanal lunes y jueves, salta el festivo del 16-nov
    f = svc.fechas_recurrencia("semanal", [1, 4], None, date(2026, 11, 1), None, True,
                               date(2026, 11, 9), date(2026, 11, 22))
    assert f == [date(2026, 11, 9), date(2026, 11, 12), date(2026, 11, 19)]
    # diaria sin domingos/festivos
    f = svc.fechas_recurrencia("diaria", None, None, date(2026, 11, 14), None, True,
                               date(2026, 11, 14), date(2026, 11, 17))
    assert f == [date(2026, 11, 14), date(2026, 11, 17)]
    # mensual día 31 → último día; si cae festivo/domingo pasa al siguiente hábil
    f = svc.fechas_recurrencia("mensual", None, 31, date(2026, 1, 1), date(2026, 6, 30), False,
                               date(2026, 1, 1), date(2026, 4, 30))
    assert f == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]
    f = svc.fechas_recurrencia("mensual", None, 1, date(2026, 11, 1), None, True,
                               date(2026, 11, 1), date(2026, 11, 30))
    assert f == [date(2026, 11, 3)]  # 1-nov domingo, 2-nov festivo


# ── Endpoints ───────────────────────────────────────────────────────────────

@pytest.fixture
async def usuarios():
    async with AsyncSessionLocal() as db:
        ids = {}
        for username, rol in USERS.items():
            u = await db.scalar(select(Usuario).where(Usuario.username == username))
            if not u:
                u = Usuario(username=username, password_hash="x", nombre_completo=f"Test {username}", rol=rol,
                            activo=True)
                db.add(u)
                await db.flush()
            ids[username] = {"id": u.id, "username": username, "rol": rol}
        await db.commit()
    return ids


@pytest.fixture(autouse=True)
async def preparar(monkeypatch):
    monkeypatch.setattr(svc, "hoy_bogota", lambda: HOY)
    await _limpiar()
    yield
    await _limpiar()
    app.dependency_overrides.pop(router_module._auth.dependency, None)


def _como(user: dict):
    app.dependency_overrides[router_module._auth.dependency] = lambda: user


async def _limpiar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TareaSeguimiento).where(TareaSeguimiento.titulo.like(f"{PREFIJO}%")))
        await db.execute(delete(TareaRecurrente).where(TareaRecurrente.titulo.like(f"{PREFIJO}%")))
        await db.execute(delete(Proyecto).where(Proyecto.nombre.like(f"{PREFIJO}%")))
        await db.commit()


async def _tarea(client, titulo: str, fecha: date, **kw) -> dict:
    r = await client.post("/api/seguimiento/tareas",
                          json={"titulo": f"{PREFIJO} {titulo}", "fecha_programada": fecha.isoformat(), **kw})
    assert r.status_code == 201, r.text
    return r.json()


async def test_hoy_manana_demoradas(client, usuarios):
    _como(usuarios["test_seg_uno"])
    t_hoy = await _tarea(client, "hoy", HOY, prioridad="alta")
    t_man = await _tarea(client, "mañana", HOY + timedelta(days=1))
    t_dem = await _tarea(client, "atrasada", HOY - timedelta(days=3))
    t_lim = await _tarea(client, "vence ayer", HOY - timedelta(days=10), fecha_limite=(HOY - timedelta(days=1)).isoformat())
    t_ok = await _tarea(client, "límite futuro", HOY - timedelta(days=5), fecha_limite=(HOY + timedelta(days=2)).isoformat())
    hecha = await _tarea(client, "hecha", HOY - timedelta(days=2))
    await client.post(f"/api/seguimiento/tareas/{hecha['id']}/completar")

    hoy = (await client.get("/api/seguimiento/tareas/hoy")).json()
    assert [t["id"] for t in hoy] == [t_hoy["id"]]
    assert hoy[0]["semana_iso"] == 46 and not hoy[0]["demorada"]
    assert [t["id"] for t in (await client.get("/api/seguimiento/tareas/manana")).json()] == [t_man["id"]]

    dem = (await client.get("/api/seguimiento/tareas/demoradas")).json()
    ids = [t["id"] for t in dem]
    assert t_dem["id"] in ids and t_lim["id"] in ids
    assert t_ok["id"] not in ids and hecha["id"] not in ids
    assert next(t for t in dem if t["id"] == t_dem["id"])["dias_atraso"] == 3

    res = (await client.get("/api/seguimiento/resumen")).json()
    assert res["tareas_hoy"] == 1 and res["tareas_manana"] == 1 and res["demoradas"] == 2
    assert res["semana_iso"] == 46


async def test_completar_y_reabrir(client, usuarios):
    _como(usuarios["test_seg_uno"])
    t = await _tarea(client, "x", HOY - timedelta(days=1))
    c = (await client.post(f"/api/seguimiento/tareas/{t['id']}/completar")).json()
    assert c["estado"] == "completada" and c["completada_en"] and not c["demorada"]
    r = (await client.post(f"/api/seguimiento/tareas/{t['id']}/reabrir")).json()
    assert r["estado"] == "pendiente" and r["completada_en"] is None and r["demorada"]
    # mover de semana
    m = (await client.patch(f"/api/seguimiento/tareas/{t['id']}",
                            json={"fecha_programada": "2026-12-31"})).json()
    assert (m["anio_iso"], m["semana_iso"]) == (2026, 53)


async def test_semanas_anio_y_detalle(client, usuarios):
    _como(usuarios["test_seg_uno"])
    await _tarea(client, "a", HOY)
    await _tarea(client, "b", HOY - timedelta(days=7))
    await _tarea(client, "c", date(2026, 12, 31))
    data = (await client.get("/api/seguimiento/semanas", params={"anio": 2026})).json()
    assert len(data["semanas"]) == 53 and data["semana_actual"] == 46
    s = {x["semana"]: x for x in data["semanas"]}
    assert s[46]["total"] == 1 and s[46]["es_actual"]
    assert s[45]["demoradas"] == 1
    assert s[53]["total"] == 1 and s[53]["lunes"] == "2026-12-28"

    det = (await client.get("/api/seguimiento/semanas/2026/46")).json()
    assert det["lunes"] == "2026-11-09" and len(det["dias"]) == 7
    assert [len(d["tareas"]) for d in det["dias"]] == [0, 0, 0, 1, 0, 0, 0]
    assert (await client.get("/api/seguimiento/semanas/2027/53")).status_code == 400


async def test_visibilidad(client, usuarios):
    uno, dos, admin = usuarios["test_seg_uno"], usuarios["test_seg_dos"], usuarios["test_seg_admin"]
    _como(uno)
    propia = await _tarea(client, "de uno", HOY)
    asignada = await _tarea(client, "uno asigna a dos", HOY, responsable_id=dos["id"])
    _como(dos)
    ids = {t["id"] for t in (await client.get("/api/seguimiento/tareas/hoy")).json()}
    assert asignada["id"] in ids and propia["id"] not in ids
    assert (await client.post(f"/api/seguimiento/tareas/{propia['id']}/completar")).status_code == 403
    assert (await client.post(f"/api/seguimiento/tareas/{asignada['id']}/completar")).status_code == 200
    _como(admin)
    ids = {t["id"] for t in (await client.get("/api/seguimiento/tareas/hoy")).json()}
    assert {propia["id"], asignada["id"]} <= ids
    ids = {t["id"] for t in (await client.get("/api/seguimiento/tareas/hoy",
                                              params={"responsable_id": dos["id"]})).json()}
    assert propia["id"] not in ids and asignada["id"] in ids


async def test_proyecto_distribuir(client, usuarios):
    _como(usuarios["test_seg_uno"])
    r = await client.post("/api/seguimiento/proyectos", json={
        "nombre": f"{PREFIJO} Seguridad de la Información", "categoria": "seguridad_informacion",
        "fecha_inicio": "2026-11-16", "fecha_fin": "2027-01-10",
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    tareas = [{"titulo": f"{PREFIJO} control {i}", "esfuerzo_horas": 4} for i in range(10)]
    body = {"tareas": tareas, "aplicar": False}

    prev = (await client.post(f"/api/seguimiento/proyectos/{pid}/distribuir", json=body)).json()
    assert not prev["aplicado"] and prev["semanas"] == 8 and len(prev["propuesta"]) == 10
    assert max(prev["carga_por_semana"].values()) <= 8
    async with AsyncSessionLocal() as db:
        n = await db.scalar(select(func.count()).where(TareaSeguimiento.proyecto_id == pid))
    assert n == 0  # la previsualización no guarda

    body["aplicar"] = True
    body["secuencial"] = True
    ap = (await client.post(f"/api/seguimiento/proyectos/{pid}/distribuir", json=body)).json()
    assert ap["aplicado"]
    det = (await client.get(f"/api/seguimiento/proyectos/{pid}")).json()
    assert det["total_tareas"] == 10 and det["avance"] == 0
    assert sum(s["total"] for s in det["semanas"]) == 10
    await client.post(f"/api/seguimiento/tareas/{det['tareas'][0]['id']}/completar")
    lista = (await client.get("/api/seguimiento/proyectos", params={"categoria": "seguridad_informacion"})).json()
    p = next(x for x in lista if x["id"] == pid)
    assert p["completadas"] == 1 and p["avance"] == 10.0

    _como(usuarios["test_seg_dos"])  # no es responsable ni creador
    assert (await client.post(f"/api/seguimiento/proyectos/{pid}/distribuir", json=body)).status_code == 403


async def test_recurrentes_idempotente(client, usuarios):
    _como(usuarios["test_seg_uno"])
    r = await client.post("/api/seguimiento/recurrentes", json={
        "titulo": f"{PREFIJO} revisar backups", "frecuencia": "semanal", "dias_semana": [1, 4],
        "fecha_inicio": "2026-11-01",
    })
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    async def contar():
        async with AsyncSessionLocal() as db:
            return await db.scalar(select(func.count()).where(TareaSeguimiento.recurrente_id == rid))

    s1 = (await client.get("/api/seguimiento/semanas/2026/47")).json()  # 16-nov festivo → solo jueves 19
    assert [len(d["tareas"]) for d in s1["dias"]] == [0, 0, 0, 1, 0, 0, 0]
    n1 = await contar()
    await client.get("/api/seguimiento/semanas/2026/47")
    assert await contar() == n1
    hoy = (await client.get("/api/seguimiento/tareas/hoy")).json()
    assert len(hoy) == 1 and hoy[0]["recurrente_id"] == rid
    # las de antes de hoy sin hacer quedan demoradas
    assert len((await client.get("/api/seguimiento/tareas/demoradas")).json()) >= 1

    # borrar una tarea recurrente la cancela (no se regenera)
    await client.delete(f"/api/seguimiento/tareas/{hoy[0]['id']}")
    assert (await client.get("/api/seguimiento/tareas/hoy")).json() == []

    # cambiar a viernes regenera solo las futuras pendientes
    r = await client.put(f"/api/seguimiento/recurrentes/{rid}", json={
        "titulo": f"{PREFIJO} revisar backups", "frecuencia": "semanal", "dias_semana": [5],
        "fecha_inicio": "2026-11-01",
    })
    assert r.status_code == 200, r.text
    s = (await client.get("/api/seguimiento/semanas/2026/47")).json()
    assert [len(d["tareas"]) for d in s["dias"]] == [0, 0, 0, 0, 1, 0, 0]


async def test_validaciones(client, usuarios):
    _como(usuarios["test_seg_uno"])
    r = await client.post("/api/seguimiento/tareas", json={
        "titulo": f"{PREFIJO} x", "fecha_programada": HOY.isoformat(), "responsable_id": 999999})
    assert r.status_code == 400
    r = await client.post("/api/seguimiento/recurrentes", json={
        "titulo": f"{PREFIJO} x", "frecuencia": "semanal", "fecha_inicio": "2026-11-01"})
    assert r.status_code == 422
    r = await client.post("/api/seguimiento/proyectos", json={
        "nombre": f"{PREFIJO} x", "fecha_inicio": "2026-12-01", "fecha_fin": "2026-11-01"})
    assert r.status_code == 422
