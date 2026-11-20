"""Cambio periódico de contraseñas (app/auth/claves.py, SER-MNT-PR-02 §20.3)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.auth.claves import hash_clave
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.usuarios import Usuario

USUARIO = "test_vence_clave"
CLAVE = "Clave-inicial-2026"
NUEVA = "Otra-clave-segura-77"


async def _borrar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Usuario).where(Usuario.username.in_([USUARIO, "test_temporal"])))
        await db.commit()


async def _crear(dias_desde_cambio: int = 0, debe_cambiar: bool = False):
    await _borrar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=hash_clave(CLAVE), nombre_completo="Prueba vence",
                       rol="logistica", activo=True, debe_cambiar_clave=debe_cambiar,
                       clave_cambiada_en=datetime.now(UTC) - timedelta(days=dias_desde_cambio)))
        await db.commit()


@pytest.fixture(autouse=True)
async def limpiar():
    yield
    await _borrar()


async def _login(client, clave=CLAVE, usuario=USUARIO):
    return await client.post("/api/auth/login", json={"username": usuario, "password": clave})


async def _cambiar(client, token, actual, nueva):
    return await client.post("/api/auth/cambiar-clave", headers={"Authorization": f"Bearer {token}"},
                             json={"clave_actual": actual, "clave_nueva": nueva})


async def test_clave_vigente_entra_normal(client):
    await _crear(dias_desde_cambio=10)
    r = await _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["debe_cambiar_clave"] is False
    assert body["dias_para_vencer"] in (settings.clave_vigencia_dias - 11, settings.clave_vigencia_dias - 10)
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["dias_para_vencer"] is not None


async def test_clave_vencida_solo_deja_cambiarla(client):
    await _crear(dias_desde_cambio=settings.clave_vigencia_dias + 1)
    r = await _login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["debe_cambiar_clave"] is True
    assert body["page_keys"] == []
    token = body["access_token"]

    # Con el token de cambio no se puede usar el resto de la API
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401

    # El refresh tampoco lo saca del cambio obligatorio
    rf = await client.post("/api/auth/refresh", json={"refresh_token": r.cookies["servilla_refresh"]})
    assert rf.json()["debe_cambiar_clave"] is True

    r = await _cambiar(client, token, CLAVE, NUEVA)
    assert r.status_code == 200, r.text
    nuevo = r.json()
    assert nuevo["debe_cambiar_clave"] is False
    assert nuevo["dias_para_vencer"] >= settings.clave_vigencia_dias - 1
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {nuevo['access_token']}"})
    assert me.status_code == 200

    assert (await _login(client, CLAVE)).status_code == 401
    assert (await _login(client, NUEVA)).json()["debe_cambiar_clave"] is False


@pytest.mark.parametrize("mala,motivo", [
    ("Corta-1", "12 caracteres"),
    ("solo-letras-sin-numeros", "números"),
    ("123456789012345", "letras"),
    (f"x{USUARIO}2026", "nombre de usuario"),
])
async def test_reglas_de_fortaleza(client, mala, motivo):
    await _crear(debe_cambiar=True)
    token = (await _login(client)).json()["access_token"]
    r = await _cambiar(client, token, CLAVE, mala)
    assert r.status_code == 422
    assert motivo in r.json()["detail"]


async def test_no_repite_claves_anteriores(client):
    await _crear(debe_cambiar=True)
    token = (await _login(client)).json()["access_token"]
    assert (await _cambiar(client, token, CLAVE, CLAVE)).status_code == 422  # la misma

    token = (await _cambiar(client, token, CLAVE, NUEVA)).json()["access_token"]
    r = await _cambiar(client, token, NUEVA, CLAVE)  # volver a la anterior
    assert r.status_code == 422
    assert "últimas" in r.json()["detail"]


async def test_clave_actual_incorrecta(client):
    await _crear()
    token = (await _login(client)).json()["access_token"]
    r = await _cambiar(client, token, "no-es-la-clave-1", NUEVA)
    assert r.status_code == 400


async def test_clave_asignada_por_admin_es_temporal(client):
    admin = (await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})).json()
    h = {"Authorization": f"Bearer {admin['access_token']}"}
    base = {"username": "test_temporal", "nombre_completo": "Temporal", "rol": "logistica"}

    r = await client.post("/api/admin/usuarios", headers=h, json=base | {"password": "corta"})
    assert r.status_code == 422

    r = await client.post("/api/admin/usuarios", headers=h, json=base | {"password": CLAVE})
    assert r.status_code == 201, r.text
    assert r.json()["debe_cambiar_clave"] is True
    assert r.json()["clave_vence_en"] is not None
    uid = r.json()["id"]
    assert (await _login(client, CLAVE, "test_temporal")).json()["debe_cambiar_clave"] is True

    # Al restablecerla también queda temporal
    async with AsyncSessionLocal() as db:
        u = await db.scalar(select(Usuario).where(Usuario.id == uid))
        u.debe_cambiar_clave = False
        await db.commit()
    r = await client.put(f"/api/admin/usuarios/{uid}/password", headers=h, json={"password": NUEVA})
    assert r.status_code == 204
    assert (await _login(client, NUEVA, "test_temporal")).json()["debe_cambiar_clave"] is True


async def test_login_sin_distinguir_mayusculas(client):
    # El teclado del celular pone la primera letra en mayúscula ("Mariela")
    await _crear()
    r = await _login(client, CLAVE, f"  {USUARIO.capitalize()} ")
    assert r.status_code == 200
