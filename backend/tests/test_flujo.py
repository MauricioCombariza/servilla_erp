"""Tests de integración para /api/flujo."""
import pytest


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Flujo 60 días ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flujo_60dias_lista(client, headers):
    r = await client.get("/api/flujo/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_flujo_60dias_estructura(client, headers):
    r = await client.get("/api/flujo/", headers=headers)
    assert r.status_code == 200
    data = r.json()
    if data:
        row = data[0]
        for campo in ("fecha", "tipo", "descripcion", "monto", "categoria",
                      "dias_hasta_fecha", "periodo"):
            assert campo in row, f"Falta campo: {campo}"
        assert row["tipo"] in ("ingreso", "egreso")
        assert row["periodo"] in ("VENCIDO", "ESTA SEMANA", "ESTE MES", "PROXIMO MES")
        assert isinstance(row["monto"], (int, float))


@pytest.mark.asyncio
async def test_flujo_60dias_orden_fecha(client, headers):
    r = await client.get("/api/flujo/", headers=headers)
    fechas = [row["fecha"] for row in r.json()]
    assert fechas == sorted(fechas)


# ── Resumen mensual ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resumen_mensual_lista(client, headers):
    r = await client.get("/api/flujo/resumen-mensual", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_resumen_mensual_estructura(client, headers):
    r = await client.get("/api/flujo/resumen-mensual", headers=headers)
    data = r.json()
    if data:
        row = data[0]
        for campo in ("anio", "mes", "total_facturado", "cobrado", "por_cobrar",
                      "ingreso_bruto_seriales", "costo_mensajero",
                      "gastos_admin", "costo_nomina", "flujo_neto"):
            assert campo in row, f"Falta campo: {campo}"
        assert 1 <= row["mes"] <= 12
        assert row["anio"] >= 2024
        assert isinstance(row["flujo_neto"], (int, float))


@pytest.mark.asyncio
async def test_resumen_mensual_orden_descendente(client, headers):
    r = await client.get("/api/flujo/resumen-mensual", headers=headers)
    data = r.json()
    if len(data) >= 2:
        periodos = [(row["anio"], row["mes"]) for row in data]
        assert periodos == sorted(periodos, reverse=True)


@pytest.mark.asyncio
async def test_resumen_mensual_filtro_anio(client, headers):
    r = await client.get("/api/flujo/resumen-mensual", params={"anio": 2026}, headers=headers)
    assert r.status_code == 200
    # Con datos de gastos/nomina creados en otros tests debería devolver algo
    # o lista vacía — ambos son válidos
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_flujo_neto_coherente(client, headers):
    """flujo_neto = cobrado - costo_mensajero - gastos_admin - costo_nomina."""
    r = await client.get("/api/flujo/resumen-mensual", headers=headers)
    for row in r.json():
        esperado = round(
            row["cobrado"] - row["costo_mensajero"] - row["gastos_admin"] - row["costo_nomina"], 2
        )
        assert abs(row["flujo_neto"] - esperado) < 0.02, \
            f"flujo_neto incorrecto en {row['anio']}-{row['mes']}: {row['flujo_neto']} vs {esperado}"


# ── Sin autenticación ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url in ("/api/flujo/", "/api/flujo/resumen-mensual"):
        r = await client.get(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"
