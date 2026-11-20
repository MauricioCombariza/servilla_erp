"""Sesiones en el servidor, bloqueo por intentos fallidos y eventos (app/auth/sesiones.py, PR-12)."""
from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt
from sqlalchemy import delete, func, select, update

from app.auth.claves import hash_clave
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.usuarios import EventoSeguridad, Sesion, Usuario

USUARIO = "test_sesiones"
CLAVE = "Clave-sesiones-2026"
NUEVA = "Otra-clave-sesiones-88"


async def _borrar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(EventoSeguridad).where(EventoSeguridad.username == USUARIO))
        await db.execute(delete(Usuario).where(Usuario.username == USUARIO))
        await db.commit()


@pytest.fixture(autouse=True)
async def usuario():
    await _borrar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=hash_clave(CLAVE), nombre_completo="Prueba sesiones",
                       rol="logistica", activo=True, debe_cambiar_clave=False,
                       clave_cambiada_en=datetime.now(UTC)))
        await db.commit()
    yield
    await _borrar()


async def _login(client, clave=CLAVE, headers=None):
    return await client.post("/api/auth/login", json={"username": USUARIO, "password": clave},
                             headers=headers or {})


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def _admin(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return r.json()["access_token"]


async def _id_usuario():
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(Usuario.id).where(Usuario.username == USUARIO))


async def _eventos(tipo):
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(func.count()).select_from(EventoSeguridad)
                               .where(EventoSeguridad.username == USUARIO, EventoSeguridad.tipo == tipo))


async def test_login_crea_sesion_y_el_token_la_lleva(client):
    r = await _login(client, headers={"X-Real-IP": "190.1.2.3"})
    assert r.status_code == 200
    body = r.json()
    assert body["inactividad_minutos"] == settings.sesion_inactividad_minutos
    sid = jwt.get_unverified_claims(body["access_token"])["sid"]
    assert jwt.get_unverified_claims(body["refresh_token"])["sid"] == sid
    async with AsyncSessionLocal() as db:
        sesion = await db.get(Sesion, sid)
    assert sesion is not None and sesion.cerrada_en is None
    assert sesion.ip == "190.1.2.3"
    assert (await client.get("/api/auth/me", headers=_h(body["access_token"]))).status_code == 200
    assert await _eventos("login") == 1


async def test_token_sin_sesion_no_sirve(client):
    # Tokens emitidos antes de este cambio: sin sid
    viejo = jwt.encode({"sub": USUARIO, "rol": "logistica", "type": "access",
                        "exp": datetime.now(UTC) + timedelta(minutes=5)},
                       settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert (await client.get("/api/auth/me", headers=_h(viejo))).status_code == 401


async def test_bloqueo_tras_intentos_fallidos(client):
    for _ in range(settings.login_max_intentos - 1):
        assert (await _login(client, clave="mala")).status_code == 401
    r = await _login(client, clave="mala")
    assert r.status_code == 423
    # Con la clave correcta tampoco entra mientras dure el bloqueo
    r = await _login(client)
    assert r.status_code == 423
    assert "bloqueada" in r.json()["detail"]
    assert await _eventos("bloqueo") == 1
    assert await _eventos("login_bloqueado") == 1

    # El administrador la desbloquea
    admin = await _admin(client)
    r = await client.post(f"/api/admin/usuarios/{await _id_usuario()}/desbloquear", headers=_h(admin))
    assert r.status_code == 200
    assert r.json()["bloqueado"] is False
    assert (await _login(client)).status_code == 200


async def test_el_bloqueo_vence_solo(client):
    async with AsyncSessionLocal() as db:
        await db.execute(update(Usuario).where(Usuario.username == USUARIO)
                         .values(bloqueado_hasta=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()
    assert (await _login(client)).status_code == 200


async def test_un_login_correcto_reinicia_el_contador(client):
    for _ in range(settings.login_max_intentos - 1):
        await _login(client, clave="mala")
    assert (await _login(client)).status_code == 200
    for _ in range(settings.login_max_intentos - 1):
        assert (await _login(client, clave="mala")).status_code == 401
    assert (await _login(client)).status_code == 200


async def test_inactividad_cierra_la_sesion(client):
    body = (await _login(client)).json()
    sid = jwt.get_unverified_claims(body["access_token"])["sid"]
    async with AsyncSessionLocal() as db:
        await db.execute(update(Sesion).where(Sesion.id == sid).values(
            ultima_actividad=datetime.now(UTC) - timedelta(minutes=settings.sesion_inactividad_minutos + 1)))
        await db.commit()
    r = await client.get("/api/auth/me", headers=_h(body["access_token"]))
    assert r.status_code == 401
    assert "inactividad" in r.json()["detail"]
    assert (await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})).status_code == 401
    async with AsyncSessionLocal() as db:
        sesion = await db.get(Sesion, sid)
    assert sesion.motivo_cierre == "inactividad"


async def test_refresh_mantiene_viva_la_sesion(client):
    body = (await _login(client)).json()
    sid = jwt.get_unverified_claims(body["access_token"])["sid"]
    hace = datetime.now(UTC) - timedelta(minutes=settings.sesion_inactividad_minutos - 1)
    async with AsyncSessionLocal() as db:
        await db.execute(update(Sesion).where(Sesion.id == sid).values(ultima_actividad=hace))
        await db.commit()
    r = await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r.status_code == 200
    async with AsyncSessionLocal() as db:
        sesion = await db.get(Sesion, sid)
    assert sesion.ultima_actividad > hace + timedelta(minutes=1)


async def test_duracion_maxima(client):
    body = (await _login(client)).json()
    sid = jwt.get_unverified_claims(body["access_token"])["sid"]
    async with AsyncSessionLocal() as db:
        await db.execute(update(Sesion).where(Sesion.id == sid)
                         .values(expira_en=datetime.now(UTC) - timedelta(seconds=1)))
        await db.commit()
    assert (await client.get("/api/auth/me", headers=_h(body["access_token"]))).status_code == 401


async def test_logout_cierra_la_sesion(client):
    body = (await _login(client)).json()
    r = await client.post("/api/auth/logout", json={"refresh_token": body["refresh_token"],
                                                     "motivo": "inactividad"})
    assert r.status_code == 204
    assert (await client.get("/api/auth/me", headers=_h(body["access_token"]))).status_code == 401
    assert (await client.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})).status_code == 401
    # Repetirlo no falla
    assert (await client.post("/api/auth/logout", json={"refresh_token": body["refresh_token"]})).status_code == 204
    assert await _eventos("logout") == 1


async def test_logout_con_token_invalido_no_falla(client):
    assert (await client.post("/api/auth/logout", json={"refresh_token": "basura"})).status_code == 204


async def test_admin_cierra_todas_las_sesiones(client):
    a = (await _login(client)).json()
    b = (await _login(client)).json()
    admin = await _admin(client)
    r = await client.post(f"/api/admin/usuarios/{await _id_usuario()}/cerrar-sesiones", headers=_h(admin))
    assert r.status_code == 204
    for s in (a, b):
        assert (await client.get("/api/auth/me", headers=_h(s["access_token"]))).status_code == 401
    # La del administrador sigue
    assert (await client.get("/api/auth/me", headers=_h(admin))).status_code == 200


async def test_desactivar_cierra_las_sesiones(client):
    a = (await _login(client)).json()
    admin = await _admin(client)
    uid = await _id_usuario()
    assert (await client.put(f"/api/admin/usuarios/{uid}", headers=_h(admin), json={"activo": False})).status_code == 200
    async with AsyncSessionLocal() as db:
        abiertas = await db.scalar(select(func.count()).select_from(Sesion)
                                   .where(Sesion.usuario_id == uid, Sesion.cerrada_en.is_(None)))
    assert abiertas == 0
    assert (await client.get("/api/auth/me", headers=_h(a["access_token"]))).status_code == 401


async def test_cambiar_clave_cierra_las_otras_sesiones(client):
    otra = (await _login(client)).json()
    actual = (await _login(client)).json()
    r = await client.post("/api/auth/cambiar-clave", headers=_h(actual["access_token"]),
                          json={"clave_actual": CLAVE, "clave_nueva": NUEVA})
    assert r.status_code == 200
    assert (await client.get("/api/auth/me", headers=_h(r.json()["access_token"]))).status_code == 200
    assert (await client.get("/api/auth/me", headers=_h(otra["access_token"]))).status_code == 401


async def test_restablecer_clave_cierra_sesiones_y_desbloquea(client):
    a = (await _login(client)).json()
    async with AsyncSessionLocal() as db:
        await db.execute(update(Usuario).where(Usuario.username == USUARIO)
                         .values(bloqueado_hasta=datetime.now(UTC) + timedelta(minutes=10)))
        await db.commit()
    admin = await _admin(client)
    r = await client.put(f"/api/admin/usuarios/{await _id_usuario()}/password", headers=_h(admin),
                         json={"password": NUEVA})
    assert r.status_code == 204
    assert (await client.get("/api/auth/me", headers=_h(a["access_token"]))).status_code == 401
    r = await _login(client, clave=NUEVA)
    assert r.status_code == 200
    assert r.json()["debe_cambiar_clave"] is True


async def test_actividad(client):
    body = (await _login(client)).json()
    assert (await client.post("/api/auth/actividad", headers=_h(body["access_token"]))).status_code == 204
