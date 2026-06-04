"""Tests de integración para /api/facturacion."""
import pytest


# ── Fixtures base ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def setup(client, headers):
    from app.database import AsyncSessionLocal
    from app.models.clientes import Cliente
    from app.models.personal import Personal
    from sqlalchemy import delete, select

    for nit in ("TEST-FAC-CLI",):
        async with AsyncSessionLocal() as db:
            old = (await db.execute(select(Cliente).where(Cliente.nit == nit))).scalar_one_or_none()
            if old:
                await db.execute(delete(Cliente).where(Cliente.id == old.id))
                await db.commit()

    rc = await client.post("/api/clientes/", json={
        "nombre_empresa": "Cliente Facturacion Test", "nit": "TEST-FAC-CLI",
    }, headers=headers)
    assert rc.status_code == 201
    cid = rc.json()["id"]

    async with AsyncSessionLocal() as db:
        old = (await db.execute(select(Personal).where(Personal.codigo == "F001"))).scalar_one_or_none()
        if old:
            await db.execute(delete(Personal).where(Personal.id == old.id))
            await db.commit()

    rp = await client.post("/api/personal/", json={
        "codigo": "F001", "nombre_completo": "Courier Test",
        "identificacion": "TEST-FAC-PER", "tipo_personal": "courier_externo",
    }, headers=headers)
    assert rp.status_code == 201
    pid = rp.json()["id"]

    yield cid, pid

    async with AsyncSessionLocal() as db:
        from app.models.facturacion import (
            DetalleFacturaEmitida, FacturaEmitida,
            FacturaRecibida, PagoRecibido, PagoRealizado
        )
        from sqlalchemy import delete as d
        fes = (await db.execute(select(FacturaEmitida.id).where(FacturaEmitida.cliente_id == cid))).scalars().all()
        for fid in fes:
            await db.execute(d(PagoRecibido).where(PagoRecibido.factura_id == fid))
            await db.execute(d(DetalleFacturaEmitida).where(DetalleFacturaEmitida.factura_id == fid))
        await db.execute(d(FacturaEmitida).where(FacturaEmitida.cliente_id == cid))
        frs = (await db.execute(select(FacturaRecibida.id).where(FacturaRecibida.personal_id == pid))).scalars().all()
        for fid in frs:
            await db.execute(d(PagoRealizado).where(PagoRealizado.factura_id == fid))
        await db.execute(d(FacturaRecibida).where(FacturaRecibida.personal_id == pid))
        await db.execute(d(Personal).where(Personal.id == pid))
        await db.execute(d(Cliente).where(Cliente.id == cid))
        await db.commit()


@pytest.fixture(scope="module")
async def factura_emitida_id(client, headers, setup):
    """Crea UNA factura y devuelve su id — fixture independiente del test."""
    cid, _ = setup
    r = await client.post("/api/facturacion/emitidas", json={
        "numero_factura": "FAC-TEST-PAGO",
        "cliente_id": cid,
        "fecha_emision": "2026-06-01",
        "fecha_vencimiento": "2026-07-01",
        "periodo_mes": 6, "periodo_anio": 2026,
        "cantidad_items": 100,
        "subtotal": 500000, "total": 500000,
    }, headers=headers)
    assert r.status_code == 201, r.text
    yield r.json()["id"]


@pytest.fixture(scope="module")
async def factura_recibida_id(client, headers, setup):
    _, pid = setup
    r = await client.post("/api/facturacion/recibidas", json={
        "numero_factura": "EXT-TEST-PAGO",
        "personal_id": pid,
        "tipo": "courier",
        "fecha_recepcion": "2026-06-01",
        "fecha_vencimiento": "2026-06-30",
        "periodo_mes": 6, "periodo_anio": 2026,
        "subtotal": 120000, "total": 120000,
        "detalles": [{"descripcion": "Servicios courier", "cantidad": 1,
                      "precio_unitario": 120000, "subtotal": 120000}],
    }, headers=headers)
    assert r.status_code == 201, r.text
    yield r.json()["id"]


# ── Facturas emitidas ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crear_factura_emitida(client, headers, setup):
    cid, _ = setup
    r = await client.post("/api/facturacion/emitidas", json={
        "numero_factura": "FAC-TEST-001",
        "cliente_id": cid,
        "fecha_emision": "2026-06-01",
        "fecha_vencimiento": "2026-07-01",
        "periodo_mes": 6, "periodo_anio": 2026,
        "cantidad_items": 100,
        "subtotal": 500000, "total": 500000,
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["numero_factura"] == "FAC-TEST-001"
    assert float(data["saldo_pendiente"]) == 500000.0
    assert data["estado"] == "pendiente"
    assert data["cliente"]["nombre_empresa"] == "Cliente Facturacion Test"


@pytest.mark.asyncio
async def test_list_facturas_emitidas(client, headers, setup):
    cid, _ = setup
    r = await client.get(f"/api/facturacion/emitidas?cliente_id={cid}", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_registrar_pago_parcial(client, headers, factura_emitida_id):
    fid = factura_emitida_id
    r = await client.post(f"/api/facturacion/emitidas/{fid}/pagos", json={
        "fecha_pago": "2026-06-15",
        "monto": 200000,
        "metodo_pago": "transferencia",
        "referencia": "TRF-001",
    }, headers=headers)
    assert r.status_code == 201
    assert float(r.json()["monto"]) == 200000.0

    r = await client.get(f"/api/facturacion/emitidas/{fid}", headers=headers)
    data = r.json()
    assert float(data["saldo_pendiente"]) == 300000.0
    assert data["estado"] == "parcial"


@pytest.mark.asyncio
async def test_registrar_pago_total(client, headers, factura_emitida_id):
    fid = factura_emitida_id
    r = await client.post(f"/api/facturacion/emitidas/{fid}/pagos", json={
        "fecha_pago": "2026-06-20",
        "monto": 300000,
        "metodo_pago": "efectivo",
    }, headers=headers)
    assert r.status_code == 201

    r = await client.get(f"/api/facturacion/emitidas/{fid}", headers=headers)
    assert r.json()["estado"] == "pagada"
    assert float(r.json()["saldo_pendiente"]) == 0.0


@pytest.mark.asyncio
async def test_pago_en_factura_pagada_rechazado(client, headers, factura_emitida_id):
    fid = factura_emitida_id
    r = await client.post(f"/api/facturacion/emitidas/{fid}/pagos", json={
        "fecha_pago": "2026-06-25",
        "monto": 1000,
        "metodo_pago": "efectivo",
    }, headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_anular_factura(client, headers, setup):
    cid, _ = setup
    r = await client.post("/api/facturacion/emitidas", json={
        "numero_factura": "FAC-TEST-ANULAR",
        "cliente_id": cid,
        "fecha_emision": "2026-06-01",
        "fecha_vencimiento": "2026-07-01",
        "periodo_mes": 6, "periodo_anio": 2026,
        "cantidad_items": 10,
        "subtotal": 50000, "total": 50000,
    }, headers=headers)
    fid = r.json()["id"]

    r = await client.delete(f"/api/facturacion/emitidas/{fid}", headers=headers)
    assert r.status_code == 204

    r = await client.get(f"/api/facturacion/emitidas/{fid}", headers=headers)
    assert r.json()["estado"] == "anulada"


# ── Facturas recibidas ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crear_factura_recibida(client, headers, setup):
    _, pid = setup
    r = await client.post("/api/facturacion/recibidas", json={
        "numero_factura": "EXT-TEST-001",
        "personal_id": pid,
        "tipo": "courier",
        "fecha_recepcion": "2026-06-01",
        "fecha_vencimiento": "2026-06-30",
        "periodo_mes": 6, "periodo_anio": 2026,
        "subtotal": 120000, "total": 120000,
        "detalles": [{"descripcion": "Servicios courier junio", "cantidad": 1,
                      "precio_unitario": 120000, "subtotal": 120000}],
    }, headers=headers)
    assert r.status_code == 201
    assert float(r.json()["saldo_pendiente"]) == 120000.0
    assert r.json()["personal"]["nombre_completo"] == "Courier Test"


@pytest.mark.asyncio
async def test_pago_factura_recibida(client, headers, factura_recibida_id):
    fid = factura_recibida_id
    r = await client.post(f"/api/facturacion/recibidas/{fid}/pagos", json={
        "fecha_pago": "2026-06-15",
        "monto": 120000,
        "metodo_pago": "transferencia",
    }, headers=headers)
    assert r.status_code == 201

    r = await client.get(f"/api/facturacion/recibidas/{fid}", headers=headers)
    assert r.json()["estado"] == "pagada"


# ── Resumen y cuentas ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resumen_financiero(client, headers):
    r = await client.get("/api/facturacion/resumen", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_por_cobrar" in data
    assert "total_por_pagar" in data
    assert "facturas_emitidas_mes" in data


@pytest.mark.asyncio
async def test_cuentas_por_cobrar(client, headers):
    r = await client.get("/api/facturacion/cuentas-por-cobrar", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_cuentas_por_pagar(client, headers):
    r = await client.get("/api/facturacion/cuentas-por-pagar", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
