"""Tests de integración para /api/personal."""
import pytest

CODIGO_TEST = "T999"


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def personal_id(client, headers):
    from app.database import AsyncSessionLocal
    from app.models.personal import Personal, PersonalCiudad
    from sqlalchemy import delete, select

    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(Personal).where(Personal.codigo == CODIGO_TEST))).scalar_one_or_none()
        if old:
            await db.execute(delete(PersonalCiudad).where(PersonalCiudad.personal_id == old.id))
            await db.execute(delete(Personal).where(Personal.id == old.id))
            await db.commit()

    r = await client.post("/api/personal/", json={
        "codigo": CODIGO_TEST,
        "nombre_completo": "Test Mensajero",
        "identificacion": "TEST-9999999",
        "tipo_personal": "mensajero",
        "precio_local": 1200,
        "precio_nacional": 1800,
    }, headers=headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    yield pid

    async with AsyncSessionLocal() as db:
        await db.execute(delete(PersonalCiudad).where(PersonalCiudad.personal_id == pid))
        await db.execute(delete(Personal).where(Personal.id == pid))
        await db.commit()


@pytest.mark.asyncio
async def test_list_personal(client, headers):
    r = await client.get("/api/personal/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_personal_filtro_tipo(client, headers):
    r = await client.get("/api/personal/?tipo=mensajero", headers=headers)
    assert r.status_code == 200
    for p in r.json():
        assert p["tipo_personal"] == "mensajero"


@pytest.mark.asyncio
async def test_get_personal(client, headers, personal_id):
    r = await client.get(f"/api/personal/{personal_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["codigo"] == CODIGO_TEST
    assert data["ciudades"] == []


@pytest.mark.asyncio
async def test_update_personal(client, headers, personal_id):
    r = await client.put(f"/api/personal/{personal_id}",
                         json={"telefono": "3001234567", "precio_local": 1400},
                         headers=headers)
    assert r.status_code == 200
    assert r.json()["telefono"] == "3001234567"
    assert float(r.json()["precio_local"]) == 1400.0


@pytest.mark.asyncio
async def test_ciudades_endpoint(client, headers):
    r = await client.get("/api/personal/ciudades", headers=headers)
    assert r.status_code == 200
    ciudades = r.json()
    assert any(c["es_bogota"] for c in ciudades)


@pytest.mark.asyncio
async def test_crud_ciudades_personal(client, headers, personal_id):
    # Obtener ID de Bogotá
    r = await client.get("/api/personal/ciudades", headers=headers)
    bogota = next(c for c in r.json() if c["es_bogota"])
    ciudad_id = bogota["id"]

    # Agregar tarifa ciudad
    r = await client.post(f"/api/personal/{personal_id}/ciudades", json={
        "ciudad_id": ciudad_id,
        "tarifa_entrega": 1200,
        "tarifa_devolucion": 800,
        "vigencia_desde": "2026-01-01",
    }, headers=headers)
    assert r.status_code == 201
    assert float(r.json()["tarifa_entrega"]) == 1200.0

    # Actualizar tarifa
    r = await client.put(f"/api/personal/{personal_id}/ciudades/{ciudad_id}",
                         json={"tarifa_entrega": 1400}, headers=headers)
    assert r.status_code == 200
    assert float(r.json()["tarifa_entrega"]) == 1400.0

    # Eliminar tarifa (soft-delete)
    r = await client.delete(f"/api/personal/{personal_id}/ciudades/{ciudad_id}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_personal_no_existe(client, headers):
    r = await client.get("/api/personal/999999", headers=headers)
    assert r.status_code == 404
