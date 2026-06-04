"""Tests de integración para /api/labores."""
import pytest


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def personal_id(client, headers):
    """Crea (o reutiliza) un personal de tipo alistamiento para los tests."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM registro_horas  WHERE personal_id IN "
                 "(SELECT id FROM personal WHERE codigo = 'T999')")
        )
        await db.execute(
            text("DELETE FROM registro_labores WHERE personal_id IN "
                 "(SELECT id FROM personal WHERE codigo = 'T999')")
        )
        await db.execute(text("DELETE FROM personal WHERE codigo = 'T999'"))
        await db.commit()

    r = await client.post("/api/personal/", json={
        "codigo": "T999",
        "nombre_completo": "Alistador Test Labores",
        "identificacion": "88001199",
        "tipo_personal": "alistamiento",
    }, headers=headers)
    assert r.status_code == 201
    pid = r.json()["id"]
    yield pid

    # Limpieza al final del módulo
    from app.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM registro_horas  WHERE personal_id = :pid"), {"pid": pid})
        await db.execute(text("DELETE FROM registro_labores WHERE personal_id = :pid"), {"pid": pid})
        await db.execute(text("DELETE FROM personal WHERE id = :pid"), {"pid": pid})
        await db.commit()


# ── Registro de horas ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_horas(client, headers):
    r = await client.get("/api/labores/horas", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_crear_hora(client, headers, personal_id):
    r = await client.post("/api/labores/horas", json={
        "personal_id": personal_id,
        "fecha": "2026-06-10",
        "horas_trabajadas": 8.0,
        "tarifa_hora": 7960.90,
        "tipo_trabajo": "alistamiento_sobres",
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["personal_id"] == personal_id
    assert data["horas_trabajadas"] == 8.0
    assert data["aprobado"] is False
    assert data["liquidado"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_aprobar_hora(client, headers, personal_id):
    r = await client.post("/api/labores/horas", json={
        "personal_id": personal_id,
        "fecha": "2026-06-11",
        "horas_trabajadas": 4.5,
        "tarifa_hora": 7960.90,
        "tipo_trabajo": "alistamiento_paquetes",
    }, headers=headers)
    hora_id = r.json()["id"]

    r = await client.post(f"/api/labores/horas/{hora_id}/aprobar", headers=headers)
    assert r.status_code == 200
    assert r.json()["aprobado"] is True
    assert r.json()["fecha_aprobacion"] is not None


@pytest.mark.asyncio
async def test_editar_hora_aprobada_falla(client, headers, personal_id):
    r = await client.post("/api/labores/horas", json={
        "personal_id": personal_id,
        "fecha": "2026-06-12",
        "horas_trabajadas": 3.0,
        "tarifa_hora": 7960.90,
        "tipo_trabajo": "alistamiento_sobres",
    }, headers=headers)
    hora_id = r.json()["id"]

    await client.post(f"/api/labores/horas/{hora_id}/aprobar", headers=headers)

    r = await client.put(f"/api/labores/horas/{hora_id}", json={"horas_trabajadas": 5.0}, headers=headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_actualizar_hora_pendiente(client, headers, personal_id):
    r = await client.post("/api/labores/horas", json={
        "personal_id": personal_id,
        "fecha": "2026-06-13",
        "horas_trabajadas": 2.0,
        "tarifa_hora": 7960.90,
        "tipo_trabajo": "alistamiento_sobres",
    }, headers=headers)
    hora_id = r.json()["id"]

    r = await client.put(f"/api/labores/horas/{hora_id}", json={"horas_trabajadas": 6.0}, headers=headers)
    assert r.status_code == 200
    assert r.json()["horas_trabajadas"] == 6.0


@pytest.mark.asyncio
async def test_eliminar_hora(client, headers, personal_id):
    r = await client.post("/api/labores/horas", json={
        "personal_id": personal_id,
        "fecha": "2026-06-14",
        "horas_trabajadas": 1.0,
        "tarifa_hora": 7960.90,
        "tipo_trabajo": "alistamiento_sobres",
    }, headers=headers)
    hora_id = r.json()["id"]

    r = await client.delete(f"/api/labores/horas/{hora_id}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_hora_no_encontrada(client, headers):
    r = await client.put("/api/labores/horas/999999", json={"horas_trabajadas": 1}, headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_filtro_horas_por_mes(client, headers, personal_id):
    r = await client.get("/api/labores/horas", params={"mes": 6, "anio": 2026}, headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Registro de labores ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_labores(client, headers):
    r = await client.get("/api/labores/labores", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_crear_labor(client, headers, personal_id):
    r = await client.post("/api/labores/labores", json={
        "personal_id": personal_id,
        "fecha": "2026-06-10",
        "tipo_labor": "pegado_guia",
        "cantidad": 150,
        "tarifa_unitaria": 11.54,
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["personal_id"] == personal_id
    assert data["tipo_labor"] == "pegado_guia"
    assert data["cantidad"] == 150
    assert data["aprobado"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_aprobar_labor(client, headers, personal_id):
    r = await client.post("/api/labores/labores", json={
        "personal_id": personal_id,
        "fecha": "2026-06-11",
        "tipo_labor": "transporte_completo",
        "cantidad": 1,
        "tarifa_unitaria": 8333.33,
    }, headers=headers)
    labor_id = r.json()["id"]

    r = await client.post(f"/api/labores/labores/{labor_id}/aprobar", headers=headers)
    assert r.status_code == 200
    assert r.json()["aprobado"] is True


@pytest.mark.asyncio
async def test_editar_labor_aprobada_falla(client, headers, personal_id):
    r = await client.post("/api/labores/labores", json={
        "personal_id": personal_id,
        "fecha": "2026-06-12",
        "tipo_labor": "pegado_guia",
        "cantidad": 50,
        "tarifa_unitaria": 11.54,
    }, headers=headers)
    labor_id = r.json()["id"]

    await client.post(f"/api/labores/labores/{labor_id}/aprobar", headers=headers)

    r = await client.put(f"/api/labores/labores/{labor_id}", json={"cantidad": 100}, headers=headers)
    assert r.status_code == 400


# ── Resumen ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resumen_labores(client, headers, personal_id):
    r = await client.get("/api/labores/resumen", params={"mes": 6, "anio": 2026}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        for campo in ("personal_id", "nombre_completo", "total_horas",
                      "total_horas_monto", "total_labores", "total_labores_monto", "total_general"):
            assert campo in row, f"Falta campo: {campo}"
        assert row["total_general"] >= 0

        ids = [r["personal_id"] for r in data]
        assert personal_id in ids


@pytest.mark.asyncio
async def test_resumen_orden_descendente(client, headers, personal_id):
    r = await client.get("/api/labores/resumen", params={"mes": 6, "anio": 2026}, headers=headers)
    totales = [row["total_general"] for row in r.json()]
    assert totales == sorted(totales, reverse=True)


# ── Sin autenticación ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url, method in [
        ("/api/labores/horas", "get"),
        ("/api/labores/labores", "get"),
        ("/api/labores/resumen", "get"),
    ]:
        r = await getattr(client, method)(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"
