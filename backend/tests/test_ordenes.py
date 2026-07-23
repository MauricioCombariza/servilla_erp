"""Tests de integración para /api/ordenes."""
import io
import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def setup_maestros(client, headers):
    """Crea cliente + precio de prueba. Devuelve (cliente_id)."""
    from app.database import AsyncSessionLocal
    from app.models.clientes import Cliente, PrecioCliente
    from sqlalchemy import delete, select

    NIT = "TEST-ORD-001"

    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(Cliente).where(Cliente.nit == NIT))).scalar_one_or_none()
        if old:
            await db.execute(delete(PrecioCliente).where(PrecioCliente.cliente_id == old.id))
            await db.execute(delete(Cliente).where(Cliente.id == old.id))
            await db.commit()

    r = await client.post("/api/clientes/", json={
        "nombre_empresa": "Cliente Ordenes Test",
        "nit": NIT,
        "ciudad": "Bogotá",
    }, headers=headers)
    assert r.status_code == 201
    cid = r.json()["id"]

    await client.post(f"/api/clientes/{cid}/precios", json={
        "tipo_servicio": "sobre",
        "ambito": "bogota",
        "precio_entrega": 4000,
        "precio_devolucion": 2500,
        "costo_mensajero_entrega": 1300,
        "costo_mensajero_devolucion": 900,
        "vigencia_desde": "2026-01-01",
    }, headers=headers)

    yield cid

    async with AsyncSessionLocal() as db:
        from app.models.ordenes import Orden
        from sqlalchemy import delete as sqldelete
        await db.execute(sqldelete(Orden).where(Orden.cliente_id == cid))
        await db.execute(sqldelete(PrecioCliente).where(PrecioCliente.cliente_id == cid))
        await db.execute(sqldelete(Cliente).where(Cliente.id == cid))
        await db.commit()


@pytest.fixture(scope="module")
async def orden_id(client, headers, setup_maestros):
    cid = setup_maestros
    r = await client.post("/api/ordenes/", json={
        "numero_orden": "TEST-ORD-999",
        "cliente_id": cid,
        "fecha_recepcion": "2026-06-01",
        "tipo_servicio": "sobre",
        "cantidad_total": 50,
        "valor_total": 200000,
    }, headers=headers)
    assert r.status_code == 201
    oid = r.json()["id"]
    yield oid


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_ordenes(client, headers):
    r = await client.get("/api/ordenes/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_orden(client, headers, orden_id):
    r = await client.get(f"/api/ordenes/{orden_id}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["numero_orden"] == "TEST-ORD-999"
    assert data["cantidad_total"] == 50
    assert data["cliente"]["nombre_empresa"] == "Cliente Ordenes Test"
    # costo_total y utilidad_total son columnas GENERATED
    assert "costo_total" in data
    assert "utilidad_total" in data


@pytest.mark.asyncio
async def test_update_orden(client, headers, orden_id):
    r = await client.put(f"/api/ordenes/{orden_id}", json={
        "cantidad_entregados": 30,
        "cantidad_devolucion": 10,
    }, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["cantidad_entregados"] == 30
    assert data["cantidad_devolucion"] == 10


@pytest.mark.asyncio
async def test_filtro_cliente(client, headers, setup_maestros):
    cid = setup_maestros
    r = await client.get(f"/api/ordenes/?cliente_id={cid}", headers=headers)
    assert r.status_code == 200
    for o in r.json():
        assert o["cliente_id"] == cid


@pytest.mark.asyncio
async def test_carga_masiva_csv(client, headers, setup_maestros):
    """Test del endpoint de carga masiva con CSV en memoria."""
    csv_content = (
        "orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito\n"
        "ORD-CM-001,SER-001,2026-06-01,Cliente Ordenes Test,sobre,bogota\n"
        "ORD-CM-001,SER-002,2026-06-01,Cliente Ordenes Test,sobre,bogota\n"
        "ORD-CM-002,SER-003,2026-06-01,Cliente Ordenes Test,sobre,bogota\n"
    )
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("ordenes.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_filas"] == 3
    assert data["seriales_nuevos"] >= 0   # puede ser 0 si ya existían
    assert data["ordenes_nuevas"] + data["ordenes_actualizadas"] >= 0
    assert isinstance(data["errores"], list)


@pytest.mark.asyncio
async def test_carga_masiva_cliente_inexistente(client, headers):
    """Filas con cliente desconocido → errores, no excepción."""
    csv_content = (
        "orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito\n"
        "ORD-XX-001,SER-XX-001,2026-06-01,ClienteQueNoExiste,sobre,bogota\n"
    )
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("bad.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["errores"]) > 0
    assert "ClienteQueNoExiste" in data["errores"][0]


@pytest.mark.asyncio
async def test_carga_masiva_columnas_faltantes(client, headers):
    csv_content = "numero,cliente\nORD-01,Test\n"
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("bad.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert any("faltantes" in e.lower() for e in data["errores"])


@pytest.mark.asyncio
async def test_carga_masiva_excluye_couriers_lecta_prindel(client, headers, setup_maestros):
    """Filas con courrier Lecta/Prindel deben excluirse y reportarse en errores."""
    csv_content = (
        "orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito,courrier\n"
        "ORD-LP-001,SER-LP-001,2026-06-01,Cliente Ordenes Test,sobre,bogota,Lecta\n"
        "ORD-LP-001,SER-LP-002,2026-06-01,Cliente Ordenes Test,sobre,bogota,PRINDEL\n"
        "ORD-LP-001,SER-LP-003,2026-06-01,Cliente Ordenes Test,sobre,bogota,OtroCourier\n"
    )
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("ordenes_lp.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["seriales_nuevos"] <= 1, "Solo la fila OtroCourier puede insertarse"
    assert any("excluidas" in e and "courier" in e.lower() for e in data["errores"]), (
        f"Se esperaba mensaje de exclusión por courier, errores: {data['errores']}"
    )


@pytest.mark.asyncio
async def test_carga_masiva_agrega_entre_chunks(client, headers, setup_maestros, monkeypatch):
    """El archivo se lee por chunks: una orden repartida en varios debe quedar completa.

    Con CHUNK_FILAS reducido a 100, las 250 filas de ORD-CHUNK-001 caen en 3 chunks
    distintos; si el resumen de órdenes no se acumulara entre chunks, cantidad_total
    quedaría en 50 (el último chunk) en vez de 250.
    """
    from sqlalchemy import text as sqltext

    from app.database import AsyncSessionLocal
    from app.services import ordenes_service

    monkeypatch.setattr(ordenes_service, "CHUNK_FILAS", 100)
    filas = 250

    csv_content = (
        "orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito\n"
        + "".join(
            f"ORD-CHUNK-001,SER-CHUNK-{i:05d},2026-06-02,Cliente Ordenes Test,sobre,bogota\n"
            for i in range(filas)
        )
    )
    try:
        r = await client.post(
            "/api/ordenes/carga-masiva",
            files={"file": ("chunks.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total_filas"] == filas
        assert data["seriales_nuevos"] == filas
        assert data["filas_ignoradas"] == 0

        async with AsyncSessionLocal() as db:
            total = (
                await db.execute(
                    sqltext("SELECT cantidad_total FROM ordenes WHERE numero_orden = 'ORD-CHUNK-001'")
                )
            ).scalar_one()
            n_seriales = (
                await db.execute(
                    sqltext("SELECT count(*) FROM seriales_gestion WHERE serial LIKE 'SER-CHUNK-%'")
                )
            ).scalar_one()
        assert total == filas, "la orden debe sumar las filas de todos los chunks"
        assert n_seriales == filas
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(sqltext("DELETE FROM seriales_gestion WHERE serial LIKE 'SER-CHUNK-%'"))
            await db.execute(sqltext("DELETE FROM ordenes WHERE numero_orden = 'ORD-CHUNK-001'"))
            await db.commit()


@pytest.mark.asyncio
async def test_carga_masiva_planilla_texto_nan_no_se_guarda(client, headers, setup_maestros):
    """planilla='nan'/'NA' (texto literal, no celda vacía) no debe guardarse tal cual.

    Regresión: el .fillna("") de _derivar_valores solo cubre NaN real de pandas
    (celda ausente); un CSV que trae el texto literal "nan"/"NA" ya escrito pasaba
    intacto y quedaba guardado como planilla en seriales_gestion.
    """
    from sqlalchemy import text as sqltext

    from app.database import AsyncSessionLocal

    csv_content = (
        "orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito,planilla\n"
        "ORD-NAN-001,SER-NAN-001,2026-06-01,Cliente Ordenes Test,sobre,bogota,nan\n"
        "ORD-NAN-002,SER-NAN-002,2026-06-01,Cliente Ordenes Test,sobre,bogota,NA\n"
    )
    try:
        r = await client.post(
            "/api/ordenes/carga-masiva",
            files={"file": ("nan.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        assert r.status_code == 200

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    sqltext(
                        "SELECT serial, planilla FROM seriales_gestion "
                        "WHERE serial IN ('SER-NAN-001', 'SER-NAN-002')"
                    )
                )
            ).fetchall()
        assert len(rows) == 2
        for _, planilla in rows:
            assert planilla == "", f"planilla debía quedar vacía, quedó {planilla!r}"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(
                sqltext("DELETE FROM seriales_gestion WHERE serial IN ('SER-NAN-001', 'SER-NAN-002')")
            )
            await db.execute(sqltext("DELETE FROM ordenes WHERE numero_orden LIKE 'ORD-NAN-%'"))
            await db.commit()


@pytest.mark.asyncio
async def test_carga_masiva_no_csv(client, headers):
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("doc.xlsx", b"fake", "application/vnd.ms-excel")},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_orden_no_existe(client, headers):
    r = await client.get("/api/ordenes/999999", headers=headers)
    assert r.status_code == 404
