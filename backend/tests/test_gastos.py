"""Tests de integración para /api/gastos."""
import pytest


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
async def limpiar_gastos_test():
    """Elimina gastos de prueba antes y después de los tests del módulo."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM pagos_gastos_fijos WHERE gasto_fijo_id IN "
                 "(SELECT id FROM gastos_fijos_mensuales WHERE descripcion LIKE '%test%')")
        )
        await db.execute(
            text("DELETE FROM gastos_fijos_mensuales WHERE descripcion LIKE '%test%'")
        )
        await db.execute(
            text("DELETE FROM gastos_administrativos WHERE descripcion LIKE '%test%' "
                 "OR descripcion LIKE '%Test%' OR descripcion LIKE '%borrar%'")
        )
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM pagos_gastos_fijos WHERE gasto_fijo_id IN "
                 "(SELECT id FROM gastos_fijos_mensuales WHERE descripcion LIKE '%test%')")
        )
        await db.execute(
            text("DELETE FROM gastos_fijos_mensuales WHERE descripcion LIKE '%test%'")
        )
        await db.execute(
            text("DELETE FROM gastos_administrativos WHERE descripcion LIKE '%test%' "
                 "OR descripcion LIKE '%Test%' OR descripcion LIKE '%borrar%'")
        )
        await db.commit()


# ── Gastos administrativos ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_gastos(client, headers):
    r = await client.get("/api/gastos/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_crear_gasto(client, headers):
    payload = {
        "fecha": "2026-06-01",
        "categoria": "internet",
        "descripcion": "Internet fibra junio test",
        "monto": 150000,
        "estado": "pendiente",
    }
    r = await client.post("/api/gastos/", json=payload, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["categoria"] == "internet"
    assert data["monto"] == 150000
    assert data["estado"] == "pendiente"
    assert "id" in data
    return data["id"]


@pytest.mark.asyncio
async def test_actualizar_gasto(client, headers):
    # Crear gasto para actualizar
    r = await client.post("/api/gastos/", json={
        "fecha": "2026-06-02", "categoria": "aseo",
        "descripcion": "Aseo oficina test", "monto": 80000, "estado": "pendiente",
    }, headers=headers)
    assert r.status_code == 201
    gasto_id = r.json()["id"]

    r = await client.put(f"/api/gastos/{gasto_id}", json={"monto": 90000}, headers=headers)
    assert r.status_code == 200
    assert r.json()["monto"] == 90000


@pytest.mark.asyncio
async def test_marcar_pagado(client, headers):
    r = await client.post("/api/gastos/", json={
        "fecha": "2026-06-03", "categoria": "software",
        "descripcion": "Licencia software test", "monto": 200000, "estado": "pendiente",
    }, headers=headers)
    gasto_id = r.json()["id"]

    r = await client.put(f"/api/gastos/{gasto_id}", json={
        "estado": "pagado", "fecha_pago": "2026-06-03",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["estado"] == "pagado"
    assert r.json()["fecha_pago"] == "2026-06-03"


@pytest.mark.asyncio
async def test_eliminar_gasto(client, headers):
    r = await client.post("/api/gastos/", json={
        "fecha": "2026-06-04", "categoria": "papeleria",
        "descripcion": "Papelería test borrar", "monto": 30000, "estado": "pendiente",
    }, headers=headers)
    gasto_id = r.json()["id"]

    r = await client.delete(f"/api/gastos/{gasto_id}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/api/gastos/", params={"mes": 6, "anio": 2026}, headers=headers)
    ids = [g["id"] for g in r.json()]
    assert gasto_id not in ids


@pytest.mark.asyncio
async def test_gasto_no_encontrado(client, headers):
    r = await client.put("/api/gastos/999999", json={"monto": 1}, headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_filtro_por_categoria(client, headers):
    r = await client.get("/api/gastos/", params={"categoria": "internet"}, headers=headers)
    assert r.status_code == 200
    for g in r.json():
        assert g["categoria"] == "internet"


@pytest.mark.asyncio
async def test_resumen_gastos(client, headers):
    r = await client.get("/api/gastos/resumen", params={"mes": 6, "anio": 2026}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        assert "categoria" in row
        assert "total" in row
        assert "cantidad" in row
        assert row["total"] >= 0
        assert row["cantidad"] >= 1


# ── Gastos fijos ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_fijos(client, headers):
    r = await client.get("/api/gastos/fijos", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_crear_gasto_fijo(client, headers):
    r = await client.post("/api/gastos/fijos", json={
        "categoria": "arriendo",
        "descripcion": "Arriendo bodega test",
        "monto": 2500000,
        "dia_pago": 5,
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["categoria"] == "arriendo"
    assert data["monto"] == 2500000
    assert data["dia_pago"] == 5
    assert data["activo"] is True
    assert data["pagos"] == []


@pytest.mark.asyncio
async def test_actualizar_gasto_fijo(client, headers):
    r = await client.post("/api/gastos/fijos", json={
        "categoria": "internet", "descripcion": "Internet fijo test", "monto": 100000,
    }, headers=headers)
    fijo_id = r.json()["id"]

    r = await client.put(f"/api/gastos/fijos/{fijo_id}", json={"monto": 120000, "activo": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["monto"] == 120000
    assert r.json()["activo"] is False


@pytest.mark.asyncio
async def test_registrar_pago_fijo(client, headers):
    r = await client.post("/api/gastos/fijos", json={
        "categoria": "software", "descripcion": "Suscripción anual test", "monto": 500000,
    }, headers=headers)
    fijo_id = r.json()["id"]

    r = await client.post(f"/api/gastos/fijos/{fijo_id}/pagos", json={
        "mes": 6, "anio": 2026, "monto_pagado": 500000, "fecha_pago": "2026-06-05",
    }, headers=headers)
    assert r.status_code == 201
    pago = r.json()
    assert pago["gasto_fijo_id"] == fijo_id
    assert pago["mes"] == 6
    assert pago["monto_pagado"] == 500000


@pytest.mark.asyncio
async def test_pago_fijo_inexistente(client, headers):
    r = await client.post("/api/gastos/fijos/999999/pagos", json={
        "mes": 6, "anio": 2026, "monto_pagado": 1000, "fecha_pago": "2026-06-01",
    }, headers=headers)
    assert r.status_code == 404


# ── Sin autenticación ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url, method in [
        ("/api/gastos/", "get"),
        ("/api/gastos/resumen", "get"),
        ("/api/gastos/fijos", "get"),
    ]:
        r = await getattr(client, method)(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"
