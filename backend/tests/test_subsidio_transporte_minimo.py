"""Subsidio de transporte de /labores: con menos de 2 horas en el día no se paga
(decisión 2026-11-05). Se crea al llegar a 2 h y se quita si el día baja de 2 h."""
from datetime import date

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal

COD = "SB2H"
DIA = date(2026, 6, 15)


@pytest.fixture(scope="module")
async def admin_headers(client):
    import bcrypt

    pwd_hash = bcrypt.hashpw(b"test-sub-pw", bcrypt.gensalt()).decode()
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_sub_user'"))
        await db.execute(text("""
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
            VALUES ('test_sub_user', :h, 'Test Subsidio', 'administrador', TRUE)
        """), {"h": pwd_hash})
        await db.commit()
    r = await client.post("/api/auth/login", json={"username": "test_sub_user", "password": "test-sub-pw"})
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_sub_user'"))
        await db.commit()


async def _limpiar(db):
    for tabla in ("subsidio_transporte", "registro_horas"):
        await db.execute(text(f"""
            DELETE FROM {tabla} WHERE personal_id IN (SELECT id FROM personal WHERE codigo = :c)
        """), {"c": COD})
    await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": COD})
    await db.commit()


@pytest.fixture
async def persona_id():
    async with AsyncSessionLocal() as db:
        await _limpiar(db)
        r = await db.execute(text("""
            INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo)
            VALUES (:c, 'Alistamiento Subsidio Test', '777790TEST', 'alistamiento', TRUE)
            RETURNING id
        """), {"c": COD})
        pid = r.scalar_one()
        await db.commit()
    yield pid
    async with AsyncSessionLocal() as db:
        await _limpiar(db)


async def _subsidio(pid):
    async with AsyncSessionLocal() as db:
        r = await db.execute(text("""
            SELECT horas_totales, tarifa FROM subsidio_transporte WHERE personal_id = :p AND fecha = :f
        """), {"p": pid, "f": DIA})
        return r.mappings().one_or_none()


async def _registrar(client, headers, pid, horas):
    r = await client.post("/api/labores/horas", headers=headers, json={
        "personal_id": pid, "fecha": DIA.isoformat(), "horas_trabajadas": horas,
        "tarifa_hora": 6000, "tipo_trabajo": "alistamiento_sobres",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_menos_de_2_horas_no_tiene_subsidio(client, admin_headers, persona_id):
    await _registrar(client, admin_headers, persona_id, 1)
    assert await _subsidio(persona_id) is None


async def test_al_llegar_a_2_horas_en_el_dia_si_hay_subsidio(client, admin_headers, persona_id):
    await _registrar(client, admin_headers, persona_id, 1)
    await _registrar(client, admin_headers, persona_id, 1.5)
    sub = await _subsidio(persona_id)
    assert sub is not None and float(sub["horas_totales"]) == 2.5 and float(sub["tarifa"]) > 0


async def test_exactamente_2_horas_si_tiene_subsidio(client, admin_headers, persona_id):
    await _registrar(client, admin_headers, persona_id, 2)
    assert await _subsidio(persona_id) is not None


async def test_si_el_dia_baja_de_2_horas_se_quita_el_subsidio(client, admin_headers, persona_id):
    await _registrar(client, admin_headers, persona_id, 1)
    segundo = await _registrar(client, admin_headers, persona_id, 1.5)
    assert await _subsidio(persona_id) is not None

    r = await client.delete(f"/api/labores/horas/{segundo}", headers=admin_headers)
    assert r.status_code == 204, r.text
    assert await _subsidio(persona_id) is None


async def test_editar_horas_por_debajo_de_2_quita_el_subsidio(client, admin_headers, persona_id):
    hora = await _registrar(client, admin_headers, persona_id, 3)
    assert await _subsidio(persona_id) is not None

    r = await client.put(f"/api/labores/horas/{hora}", headers=admin_headers, json={"horas_trabajadas": 1.5})
    assert r.status_code == 200, r.text
    assert await _subsidio(persona_id) is None


async def test_subsidio_ya_liquidado_no_se_toca(client, admin_headers, persona_id):
    hora = await _registrar(client, admin_headers, persona_id, 3)
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE subsidio_transporte SET liquidado = TRUE WHERE personal_id = :p AND fecha = :f
        """), {"p": persona_id, "f": DIA})
        await db.commit()

    r = await client.put(f"/api/labores/horas/{hora}", headers=admin_headers, json={"horas_trabajadas": 1})
    assert r.status_code == 200, r.text
    assert await _subsidio(persona_id) is not None
