"""Tests de integración para /api/clientes (usan la BD real)."""
import pytest

NIT_TEST = "TEST-900123456"


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def cliente_id(client, headers):
    """Crea un cliente de test y lo limpia al finalizar (hard-delete via BD)."""
    from app.database import AsyncSessionLocal
    from app.models.clientes import Cliente, PrecioCliente
    from sqlalchemy import delete, select

    # Limpiar si quedó de una corrida anterior
    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(Cliente).where(Cliente.nit == NIT_TEST))).scalar_one_or_none()
        if old:
            await db.execute(delete(PrecioCliente).where(PrecioCliente.cliente_id == old.id))
            await db.execute(delete(Cliente).where(Cliente.id == old.id))
            await db.commit()

    r = await client.post("/api/clientes/", json={
        "nombre_empresa": "Test ERP SA",
        "nit": NIT_TEST,
        "ciudad": "Bogotá",
        "plazo_pago_dias": 30,
    }, headers=headers)
    assert r.status_code == 201
    cid = r.json()["id"]
    yield cid

    async with AsyncSessionLocal() as db:
        await db.execute(delete(PrecioCliente).where(PrecioCliente.cliente_id == cid))
        await db.execute(delete(Cliente).where(Cliente.id == cid))
        await db.commit()


@pytest.mark.asyncio
async def test_list_clientes_sin_auth(client):
    r = await client.get("/api/clientes/")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_clientes(client, headers):
    r = await client.get("/api/clientes/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_cliente(client, headers, cliente_id):
    r = await client.get(f"/api/clientes/{cliente_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["nit"] == NIT_TEST
    assert data["precios"] == []


@pytest.mark.asyncio
async def test_update_cliente(client, headers, cliente_id):
    r = await client.put(f"/api/clientes/{cliente_id}", json={
        "plazo_pago_dias": 45,
        "contacto_nombre": "Juan Test",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["plazo_pago_dias"] == 45


@pytest.mark.asyncio
async def test_crud_precios(client, headers, cliente_id):
    # Crear precio
    r = await client.post(f"/api/clientes/{cliente_id}/precios", json={
        "tipo_servicio": "sobre",
        "ambito": "bogota",
        "precio_entrega": 3500,
        "precio_devolucion": 2000,
        "costo_mensajero_entrega": 1200,
        "costo_mensajero_devolucion": 800,
        "vigencia_desde": "2026-01-01",
    }, headers=headers)
    assert r.status_code == 201
    precio_id = r.json()["id"]
    assert float(r.json()["precio_entrega"]) == 3500.0

    # Listar precios
    r = await client.get(f"/api/clientes/{cliente_id}/precios", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Actualizar precio
    r = await client.put(f"/api/clientes/{cliente_id}/precios/{precio_id}",
                         json={"precio_entrega": 3800}, headers=headers)
    assert r.status_code == 200
    assert float(r.json()["precio_entrega"]) == 3800.0

    # Soft-delete precio
    r = await client.delete(f"/api/clientes/{cliente_id}/precios/{precio_id}", headers=headers)
    assert r.status_code == 204

    # Ya no aparece en lista de activos
    r = await client.get(f"/api/clientes/{cliente_id}/precios", headers=headers)
    assert len(r.json()) == 0


@pytest.mark.asyncio
async def test_get_cliente_no_existe(client, headers):
    r = await client.get("/api/clientes/999999", headers=headers)
    assert r.status_code == 404
