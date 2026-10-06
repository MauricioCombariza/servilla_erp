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


# ── P&L completo ──────────────────────────────────────────────────────────────

_GASTOS_PL = ("costo_mensajeros", "alistamiento", "subsidio", "ajustes_liquidacion", "fletes",
              "nomina", "gastos_admin", "gastos_fijos", "facturas_proveedores")


@pytest.mark.asyncio
async def test_pl_completo_cuadra(client, headers):
    r = await client.get("/api/reportes/pl-completo?anio=2026", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["anio"] == 2026
    assert [m["mes"] for m in data["meses"]] == list(range(1, 13))
    for row in [*data["meses"], data["total"]]:
        total_gastos = sum(row[c] for c in _GASTOS_PL)
        assert row["total_gastos"] == pytest.approx(total_gastos, abs=0.05)
        assert row["utilidad_neta"] == pytest.approx(row["ingresos"] - total_gastos, abs=0.05)
    for campo in ("ingresos", "total_gastos", "utilidad_neta"):
        assert data["total"][campo] == pytest.approx(sum(m[campo] for m in data["meses"]), abs=0.5)


@pytest.mark.asyncio
async def test_pl_completo_excel(client, headers):
    r = await client.get("/api/reportes/pl-completo/excel?anio=2026", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.content[:2] == b"PK"


# ── Acceso sin auth ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url in [
        "/api/reportes/operacional?anio=2026",
        "/api/reportes/mensajeros",
        "/api/reportes/ordenes",
        "/api/reportes/facturacion",
        "/api/reportes/tendencias",
        "/api/reportes/pl-completo",
    ]:
        r = await client.get(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"
