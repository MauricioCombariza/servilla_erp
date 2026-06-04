"""Tests de integración para /api/reportes."""
import pytest


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Operacional ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_operacional_estructura(client, headers):
    r = await client.get("/api/reportes/operacional?anio=2026", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("cliente", "entregas", "devoluciones", "total_seriales",
                      "ingreso_cliente", "costo_mensajero", "margen"):
            assert campo in row, f"Falta campo: {campo}"


@pytest.mark.asyncio
async def test_operacional_mes(client, headers):
    r = await client.get("/api/reportes/operacional?anio=2026&mes=6", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_operacional_mes_invalido(client, headers):
    r = await client.get("/api/reportes/operacional?anio=2026&mes=13", headers=headers)
    assert r.status_code == 422


# ── Mensajeros ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mensajeros_estructura(client, headers):
    r = await client.get(
        "/api/reportes/mensajeros",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("cod_men", "planillas", "total_seriales", "entregas",
                      "devoluciones", "total_mensajero"):
            assert campo in row


# ── Órdenes ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ordenes_estructura(client, headers):
    r = await client.get(
        "/api/reportes/ordenes",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("numero_orden", "cliente", "fecha_recepcion", "cantidad_total",
                      "pendientes", "pct_gestionado", "estado"):
            assert campo in row


@pytest.mark.asyncio
async def test_ordenes_filtro_cliente(client, headers):
    r = await client.get(
        "/api/reportes/ordenes",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31", "cliente_id": 9999},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == []


# ── Facturación ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_facturacion_estructura(client, headers):
    r = await client.get(
        "/api/reportes/facturacion",
        params={"fecha_desde": "2026-01-01", "fecha_hasta": "2026-12-31"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("cliente", "num_facturas", "total_facturado", "total_cobrado", "pendiente"):
            assert campo in row


# ── Tendencias ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tendencias_estructura(client, headers):
    r = await client.get("/api/reportes/tendencias?meses=12", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("mes", "total_seriales", "entregas", "devoluciones",
                      "ingreso_estimado", "costo_mensajero"):
            assert campo in row
        assert len(row["mes"]) == 7  # "YYYY-MM"


@pytest.mark.asyncio
async def test_tendencias_orden_cronologico(client, headers):
    r = await client.get("/api/reportes/tendencias?meses=6", headers=headers)
    assert r.status_code == 200
    meses = [row["mes"] for row in r.json()]
    assert meses == sorted(meses)


@pytest.mark.asyncio
async def test_tendencias_limite_max(client, headers):
    r = await client.get("/api/reportes/tendencias?meses=37", headers=headers)
    assert r.status_code == 422


# ── Acceso sin auth ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url in [
        "/api/reportes/operacional?anio=2026",
        "/api/reportes/mensajeros",
        "/api/reportes/ordenes",
        "/api/reportes/facturacion",
        "/api/reportes/tendencias",
    ]:
        r = await client.get(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"
