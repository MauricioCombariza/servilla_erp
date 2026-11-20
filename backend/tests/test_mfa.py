"""Segundo factor con código del celular (app/auth/mfa.py y los pasos MFA del login)."""
import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.auth import mfa
from app.auth.claves import hash_clave
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.usuarios import EventoSeguridad, Usuario

USUARIO = "test_mfa"
CLAVE = "Clave-mfa-segura-2026"


# ── TOTP (RFC 6238, apéndice B, SHA1) ────────────────────────────────────────

SECRETO_RFC = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize("momento,esperado", [
    (59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037"),
])
def test_totp_vectores_rfc(momento, esperado):
    assert mfa.codigo_en(SECRETO_RFC, momento // 30) == esperado


def test_totp_ventana_y_repeticion():
    s = mfa.nuevo_secreto()
    t = 1_800_000_000.0
    paso = mfa.paso_actual(t)
    assert mfa.verificar_totp(s, mfa.codigo_en(s, paso), None, t) == paso
    assert mfa.verificar_totp(s, mfa.codigo_en(s, paso - 1), None, t) == paso - 1
    assert mfa.verificar_totp(s, mfa.codigo_en(s, paso + 2), None, t) is None
    # Ya usado: no sirve otra vez
    assert mfa.verificar_totp(s, mfa.codigo_en(s, paso), paso, t) is None
    assert mfa.verificar_totp(s, "12345", None, t) is None


def test_cifrado_del_secreto():
    s = mfa.nuevo_secreto()
    cifrado = mfa.cifrar(s)
    assert s not in cifrado
    assert mfa.descifrar(cifrado) == s
    assert mfa.descifrar("no-es-fernet") is None


def test_codigos_respaldo():
    codigos = mfa.nuevos_codigos_respaldo()
    assert len(codigos) == 10 and len(set(codigos)) == 10
    h = mfa.hash_respaldo(codigos[0])
    assert mfa.coincide_respaldo(codigos[0].lower().replace("-", ""), h)
    assert not mfa.coincide_respaldo(codigos[1], h)
    assert mfa.parece_respaldo(codigos[0]) and not mfa.parece_respaldo("123456")


# ── Login con MFA ────────────────────────────────────────────────────────────

async def _borrar():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(EventoSeguridad).where(EventoSeguridad.username == USUARIO))
        await db.execute(delete(Usuario).where(Usuario.username == USUARIO))
        await db.commit()


@pytest.fixture(autouse=True)
async def usuario(monkeypatch):
    monkeypatch.setattr(settings, "mfa_obligatorio", True)
    await _borrar()
    async with AsyncSessionLocal() as db:
        db.add(Usuario(username=USUARIO, password_hash=hash_clave(CLAVE), nombre_completo="Prueba MFA",
                       rol="logistica", activo=True, debe_cambiar_clave=False,
                       clave_cambiada_en=datetime.now(UTC)))
        await db.commit()
    yield
    await _borrar()


async def _login(client):
    r = await client.post("/api/auth/login", json={"username": USUARIO, "password": CLAVE})
    assert r.status_code == 200, r.text
    return r.json()


async def _secreto() -> str:
    async with AsyncSessionLocal() as db:
        cifrado = await db.scalar(select(Usuario.mfa_secreto).where(Usuario.username == USUARIO))
    return mfa.descifrar(cifrado)


async def _configurar(client) -> dict:
    """Configura el MFA y devuelve la respuesta de activar (tokens + códigos de respaldo)."""
    paso1 = await _login(client)
    assert paso1["mfa_paso"] == "configurar"
    assert "access_token" not in paso1
    conf = (await client.post("/api/auth/mfa/configurar", json={"mfa_token": paso1["mfa_token"]})).json()
    assert conf["uri"].startswith("otpauth://totp/Servilla%20ERP%3Atest_mfa?secret=")
    codigo = mfa.codigo_en(conf["secreto"], mfa.paso_actual())
    r = await client.post("/api/auth/mfa/activar", json={"mfa_token": paso1["mfa_token"], "codigo": codigo})
    assert r.status_code == 200, r.text
    return r.json()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


async def test_primer_ingreso_configura_y_entrega_codigos(client):
    body = await _configurar(client)
    assert len(body["codigos_respaldo"]) == 10
    assert (await client.get("/api/auth/me", headers=_h(body["access_token"]))).status_code == 200
    async with AsyncSessionLocal() as db:
        u = await db.scalar(select(Usuario).where(Usuario.username == USUARIO))
    assert u.mfa_activo is True


async def test_activar_con_codigo_malo(client):
    paso1 = await _login(client)
    await client.post("/api/auth/mfa/configurar", json={"mfa_token": paso1["mfa_token"]})
    r = await client.post("/api/auth/mfa/activar", json={"mfa_token": paso1["mfa_token"], "codigo": "000000"})
    assert r.status_code == 401


async def test_ingreso_con_codigo_y_sin_repetirlo(client):
    await _configurar(client)
    secreto = await _secreto()
    paso1 = await _login(client)
    assert paso1["mfa_paso"] == "verificar"
    # El código con el que se activó ya se usó: se acepta el del paso siguiente (ventana)
    async with AsyncSessionLocal() as db:
        ultimo = await db.scalar(select(Usuario.mfa_ultimo_paso).where(Usuario.username == USUARIO))
    usado = mfa.codigo_en(secreto, ultimo)
    siguiente = mfa.codigo_en(secreto, max(ultimo + 1, mfa.paso_actual()))
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": usado})
    assert r.status_code == 401
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": siguiente})
    assert r.status_code == 200
    assert (await client.get("/api/auth/me", headers=_h(r.json()["access_token"]))).status_code == 200


async def test_codigo_de_respaldo_sirve_una_vez(client):
    codigos = (await _configurar(client))["codigos_respaldo"]
    paso1 = await _login(client)
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": codigos[3]})
    assert r.status_code == 200
    paso1 = await _login(client)
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": codigos[3]})
    assert r.status_code == 401


async def test_codigos_malos_bloquean(client):
    await _configurar(client)
    paso1 = await _login(client)
    for _ in range(settings.login_max_intentos - 1):
        r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": "000000"})
        assert r.status_code == 401
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": "000000"})
    assert r.status_code == 423
    # Ya bloqueada: ni la clave pasa
    r = await client.post("/api/auth/login", json={"username": USUARIO, "password": CLAVE})
    assert r.status_code == 423


async def test_token_mfa_no_sirve_para_la_api_ni_para_otro_paso(client):
    paso1 = await _login(client)
    assert (await client.get("/api/auth/me", headers=_h(paso1["mfa_token"]))).status_code == 401
    r = await client.post("/api/auth/mfa/verificar", json={"mfa_token": paso1["mfa_token"], "codigo": "123456"})
    assert r.status_code == 401  # es de "configurar", no de "verificar"
    r = await client.post("/api/auth/mfa/configurar", json={"mfa_token": "basura"})
    assert r.status_code == 401


async def test_mfa_activo_se_pide_aunque_no_sea_obligatorio(client, monkeypatch):
    await _configurar(client)
    monkeypatch.setattr(settings, "mfa_obligatorio", False)
    assert (await _login(client))["mfa_paso"] == "verificar"


async def test_sin_mfa_y_no_obligatorio_entra_directo(client, monkeypatch):
    monkeypatch.setattr(settings, "mfa_obligatorio", False)
    r = await client.post("/api/auth/login", json={"username": USUARIO, "password": CLAVE})
    assert "access_token" in r.json()


async def test_admin_reinicia_el_mfa(client):
    body = await _configurar(client)
    admin_login = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    # El admin de pruebas no tiene MFA: con MFA obligatorio lo tendría que configurar
    admin_conf = await client.post("/api/auth/mfa/configurar", json={"mfa_token": admin_login.json()["mfa_token"]})
    codigo = mfa.codigo_en(admin_conf.json()["secreto"], mfa.paso_actual())
    admin = (await client.post("/api/auth/mfa/activar", json={"mfa_token": admin_login.json()["mfa_token"],
                                                              "codigo": codigo})).json()["access_token"]
    try:
        async with AsyncSessionLocal() as db:
            uid = await db.scalar(select(Usuario.id).where(Usuario.username == USUARIO))
        r = await client.post(f"/api/admin/usuarios/{uid}/reiniciar-mfa", headers=_h(admin))
        assert r.status_code == 200
        assert r.json()["mfa_activo"] is False
        assert (await client.get("/api/auth/me", headers=_h(body["access_token"]))).status_code == 401
        assert (await _login(client))["mfa_paso"] == "configurar"
    finally:
        # El admin de pruebas lo usan las demás pruebas sin MFA
        async with AsyncSessionLocal() as db:
            admin_u = await db.scalar(select(Usuario).where(Usuario.username == "admin"))
            admin_u.mfa_activo, admin_u.mfa_secreto, admin_u.mfa_ultimo_paso = False, None, None
            await db.commit()
