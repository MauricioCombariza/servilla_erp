"""Registro de claves de sistemas fuera del ERP (app/routers/claves_externas.py)."""
from datetime import timedelta

import bcrypt
import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.claves_externas import ClaveExterna
from app.models.usuarios import Usuario
from app.routers.claves_externas import hoy as hoy_bogota

URL = "/api/admin/claves-externas"
APP = "test-app-externa"


@pytest.fixture
async def admin(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
async def limpiar():
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ClaveExterna).where(ClaveExterna.aplicacion.like("test-%")))
        await db.execute(delete(Usuario).where(Usuario.username == "test_no_admin_ce"))
        await db.commit()


async def _crear(client, h, **extra):
    datos = {"aplicacion": APP, "usuario": "root", "categoria": "correo_sql_hojas",
             "custodio_1": "Jefe de soporte", "sobre_no": "3", "cofre_no": "1"} | extra
    return await client.post(URL, headers=h, json=datos)


async def test_estados_por_vencimiento(client, admin):
    hoy = hoy_bogota()
    casos = {
        "sin": None,                                    # sin registro
        "vencida": hoy - timedelta(days=46),            # 45 días
        "por_vencer": hoy - timedelta(days=40),         # quedan 5 (aviso 7)
        "al_dia": hoy - timedelta(days=5),
    }
    for usuario, cambio in casos.items():
        r = await _crear(client, admin, usuario=usuario, categoria="dominio_admin",
                         ultimo_cambio=cambio.isoformat() if cambio else None)
        assert r.status_code == 201, r.text
        assert r.json()["estado"] == ("sin_registro" if usuario == "sin" else usuario)

    filas = [f for f in (await client.get(URL, headers=admin)).json() if f["aplicacion"] == APP]
    assert [f["estado"] for f in filas] == ["vencida", "sin_registro", "por_vencer", "al_dia"]

    res = (await client.get(f"{URL}/resumen", headers=admin)).json()
    assert res["vencidas"] >= 1 and res["por_vencer"] >= 1 and res["sin_registro"] >= 1


async def test_periodicidad_por_categoria_y_propia(client, admin):
    r = await _crear(client, admin, categoria="fortinet", ultimo_cambio=hoy_bogota().isoformat())
    assert r.json()["periodicidad_efectiva"] == 180
    r = await client.put(f"{URL}/{r.json()['id']}", headers=admin, json={"periodicidad_dias": 30})
    assert r.json()["periodicidad_efectiva"] == 30
    assert r.json()["dias_restantes"] == 30


async def test_registrar_cambio_actualiza_fecha_y_sobre(client, admin):
    cid = (await _crear(client, admin)).json()["id"]
    hoy = hoy_bogota().isoformat()
    r = await client.post(f"{URL}/{cid}/cambios", headers=admin,
                          json={"fecha": hoy, "responsable": "Jefe de soporte", "sobre_no": "7"})
    assert r.status_code == 201, r.text
    assert r.json()["ultimo_cambio"] == hoy
    assert r.json()["sobre_no"] == "7"
    assert r.json()["estado"] == "al_dia"

    # Un cambio con fecha anterior queda en el historial pero no retrocede la fecha
    viejo = (hoy_bogota() - timedelta(days=100)).isoformat()
    r = await client.post(f"{URL}/{cid}/cambios", headers=admin, json={"fecha": viejo, "responsable": "X"})
    assert r.json()["ultimo_cambio"] == hoy
    hist = (await client.get(f"{URL}/{cid}/cambios", headers=admin)).json()
    assert [h["fecha"] for h in hist] == [hoy, viejo]

    futuro = (hoy_bogota() + timedelta(days=1)).isoformat()
    r = await client.post(f"{URL}/{cid}/cambios", headers=admin, json={"fecha": futuro, "responsable": "X"})
    assert r.status_code == 422


@pytest.mark.parametrize("texto", ["clave: Secreta123", "password=abc", "Contraseña : x"])
async def test_no_deja_escribir_claves(client, admin, texto):
    r = await _crear(client, admin, notas=texto)
    assert r.status_code == 422
    cid = (await _crear(client, admin, usuario="otro")).json()["id"]
    r = await client.post(f"{URL}/{cid}/cambios", headers=admin,
                          json={"fecha": hoy_bogota().isoformat(), "responsable": "X", "observacion": texto})
    assert r.status_code == 422


async def test_duplicado_y_categoria_invalida(client, admin):
    assert (await _crear(client, admin)).status_code == 201
    assert (await _crear(client, admin)).status_code == 400
    assert (await _crear(client, admin, usuario="x", categoria="nada")).status_code == 422


async def test_solo_administradores(client):
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username="test_no_admin_ce", nombre_completo="No admin", rol="logistica",
                       password_hash=bcrypt.hashpw(b"clave-no-admin-1", bcrypt.gensalt()).decode()))
        await db.commit()
    r = await client.post("/api/auth/login", json={"username": "test_no_admin_ce", "password": "clave-no-admin-1"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(URL, headers=h)).status_code == 403
