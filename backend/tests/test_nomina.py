"""Tests de integración para /api/nomina."""
import pytest


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
async def limpiar_empleados_test():
    """Elimina empleados de prueba antes y después de los tests del módulo."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async def _limpiar(db):
        # Borrar provisiones de TODOS los empleados de prueba (por id o nombre)
        await db.execute(
            text("DELETE FROM nomina_provisiones WHERE empleado_id IN "
                 "(SELECT id FROM nomina_empleados WHERE nombre_completo LIKE '%Test%')")
        )
        await db.execute(
            text("DELETE FROM nomina_empleados WHERE nombre_completo LIKE '%Test%'")
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        await _limpiar(db)
    yield
    async with AsyncSessionLocal() as db:
        await _limpiar(db)


# ── Empleados ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listar_empleados(client, headers):
    r = await client.get("/api/nomina/empleados", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_crear_empleado(client, headers):
    r = await client.post("/api/nomina/empleados", json={
        "nombre_completo": "Ana García Test",
        "identificacion": "99001122",
        "cargo": "Coordinadora",
        "salario_mensual": 2500000,
        "tiene_auxilio_transporte": True,
        "auxilio_no_salarial": 0,
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["nombre_completo"] == "Ana García Test"
    assert data["salario_mensual"] == 2500000
    assert data["tiene_auxilio_transporte"] is True
    assert data["activo"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_crear_empleado_campos_minimos(client, headers):
    r = await client.post("/api/nomina/empleados", json={
        "nombre_completo": "Carlos Mínimo Test",
        "salario_mensual": 1300606,
    }, headers=headers)
    assert r.status_code == 201
    assert r.json()["tiene_auxilio_transporte"] is False
    assert r.json()["auxilio_no_salarial"] == 0


@pytest.mark.asyncio
async def test_actualizar_empleado(client, headers):
    r = await client.post("/api/nomina/empleados", json={
        "nombre_completo": "Pedro Update Test",
        "salario_mensual": 1800000,
    }, headers=headers)
    emp_id = r.json()["id"]

    r = await client.put(f"/api/nomina/empleados/{emp_id}", json={
        "salario_mensual": 2000000,
        "cargo": "Auxiliar contable",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["salario_mensual"] == 2000000
    assert r.json()["cargo"] == "Auxiliar contable"


@pytest.mark.asyncio
async def test_desactivar_empleado(client, headers):
    r = await client.post("/api/nomina/empleados", json={
        "nombre_completo": "Inactivo Test", "salario_mensual": 1300606,
    }, headers=headers)
    emp_id = r.json()["id"]

    r = await client.put(f"/api/nomina/empleados/{emp_id}", json={"activo": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["activo"] is False


@pytest.mark.asyncio
async def test_empleado_no_encontrado(client, headers):
    r = await client.put("/api/nomina/empleados/999999", json={"salario_mensual": 1}, headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_filtro_solo_activos(client, headers):
    r = await client.get("/api/nomina/empleados", params={"activo": True}, headers=headers)
    assert r.status_code == 200
    for e in r.json():
        assert e["activo"] is True


# ── Provisiones ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_calcular_provisiones(client, headers):
    r = await client.post("/api/nomina/provisiones/calcular", json={
        "periodo_mes": 6, "periodo_anio": 2026,
    }, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["periodo_mes"] == 6
    assert data["periodo_anio"] == 2026
    assert data["total_empleados"] >= 1
    assert data["total_salarios"] > 0
    assert data["total_seguridad_social"] > 0
    assert data["total_provisiones"] > 0
    assert data["costo_total"] > data["total_salarios"]


@pytest.mark.asyncio
async def test_calcular_idempotente(client, headers):
    """Calcular dos veces el mismo período no duplica registros."""
    r1 = await client.post("/api/nomina/provisiones/calcular", json={
        "periodo_mes": 6, "periodo_anio": 2026,
    }, headers=headers)
    r2 = await client.post("/api/nomina/provisiones/calcular", json={
        "periodo_mes": 6, "periodo_anio": 2026,
    }, headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["total_empleados"] == r2.json()["total_empleados"]
    assert r1.json()["costo_total"] == r2.json()["costo_total"]


@pytest.mark.asyncio
async def test_listar_provisiones(client, headers):
    # Asegurar que hay provisiones calculadas
    await client.post("/api/nomina/provisiones/calcular", json={
        "periodo_mes": 6, "periodo_anio": 2026,
    }, headers=headers)

    r = await client.get("/api/nomina/provisiones", params={"mes": 6, "anio": 2026}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    prov = data[0]
    for campo in ("id", "empleado_id", "periodo_mes", "periodo_anio",
                  "salario_base", "arl", "eps", "afp", "caja_compensacion",
                  "prima", "cesantias", "vacaciones"):
        assert campo in prov, f"Falta campo: {campo}"
    assert prov["salario_base"] > 0
    assert prov["arl"] > 0


@pytest.mark.asyncio
async def test_provision_calculo_correcto(client, headers):
    """Verifica que ARL sea aprox. salario * 0.00522."""
    await client.post("/api/nomina/provisiones/calcular", json={
        "periodo_mes": 6, "periodo_anio": 2026,
    }, headers=headers)

    r = await client.get("/api/nomina/provisiones", params={"mes": 6, "anio": 2026}, headers=headers)
    for prov in r.json():
        sal = prov["salario_base"]
        if sal and sal > 0:
            arl_esperado = round(sal * 0.00522, 2)
            assert abs(prov["arl"] - arl_esperado) < 1, \
                f"ARL incorrecto: {prov['arl']} vs esperado {arl_esperado}"
            break


@pytest.mark.asyncio
async def test_listar_parametros(client, headers):
    r = await client.get("/api/nomina/parametros", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Sin autenticación ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_autenticacion(client):
    for url, method in [
        ("/api/nomina/empleados", "get"),
        ("/api/nomina/provisiones", "get"),
        ("/api/nomina/parametros", "get"),
    ]:
        r = await getattr(client, method)(url)
        assert r.status_code == 401, f"Esperaba 401 en {url}"

    r = await client.post("/api/nomina/provisiones/calcular", json={"periodo_mes": 6, "periodo_anio": 2026})
    assert r.status_code == 401
