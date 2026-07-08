"""Tests de integración: módulo Pagos Ciudades (prefacturas + CxP couriers externos)."""
import pytest
from datetime import date, timedelta


@pytest.fixture(scope="module")
async def auth_headers(client):
    import bcrypt
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    pwd_hash = bcrypt.hashpw(b"test-pc-pw", bcrypt.gensalt()).decode()

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_pc_user'"))
        await db.execute(
            text("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                VALUES ('test_pc_user', :h, 'Test Pagos Ciudades', 'administrador', TRUE)
            """),
            {"h": pwd_hash},
        )
        await db.commit()

    r = await client.post(
        "/api/auth/login",
        json={"username": "test_pc_user", "password": "test-pc-pw"},
    )
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_pc_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def pc_data():
    """Courier externo con 2 planillas (una bogota+nacional mezclada), precio_mensajero ya seteado."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    PLANILLA_A = "TEST-PC-A"
    PLANILLA_B = "TEST-PC-B"
    COD = "PC01"

    async def _cleanup(db):
        await db.execute(
            text("DELETE FROM facturas_courier_cxp WHERE cod_mensajero = :c"), {"c": COD}
        )
        await db.execute(
            text("""
                DELETE FROM prefactura_planillas WHERE planilla IN (:a, :b)
            """),
            {"a": PLANILLA_A, "b": PLANILLA_B},
        )
        await db.execute(
            text("DELETE FROM prefacturas_courier WHERE cod_mensajero = :c"), {"c": COD}
        )
        await db.execute(
            text("DELETE FROM seriales_gestion WHERE planilla IN (:a, :b)"),
            {"a": PLANILLA_A, "b": PLANILLA_B},
        )
        await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": COD})
        await db.commit()

    async with AsyncSessionLocal() as db:
        await _cleanup(db)

        r = await db.execute(
            text("""
                INSERT INTO personal (codigo, nombre_completo, identificacion,
                                      tipo_personal, precio_local, precio_nacional, activo)
                VALUES (:cod, 'Courier Ciudades Test', '888888TEST',
                        'courier_externo', 500, 800, TRUE)
                RETURNING id
            """),
            {"cod": COD},
        )
        courier_id = r.scalar_one()
        await db.commit()

        seriales = [
            ("PC-A-1", PLANILLA_A, "bogota", 500),
            ("PC-A-2", PLANILLA_A, "nacional", 800),
            ("PC-B-1", PLANILLA_B, "bogota", 500),
            ("PC-B-2", PLANILLA_B, "bogota", 500),
        ]
        for serial, planilla, ambito, precio in seriales:
            await db.execute(
                text("""
                    INSERT INTO seriales_gestion
                        (serial, planilla, f_esc, cod_men, mensajero_id,
                         tipo_gestion, tipo_envio, ambito, estado,
                         precio_mensajero, precio_cliente, origen)
                    VALUES
                        (:serial, :planilla, '2026-06-10', :cod, :mid,
                         'Entrega', 'sobre', :ambito, 'pendiente', :precio, 0, 'manual')
                """),
                {"serial": serial, "planilla": planilla, "cod": COD, "mid": courier_id,
                 "ambito": ambito, "precio": precio},
            )
        await db.commit()

    yield {"cod_mensajero": COD, "planilla_a": PLANILLA_A, "planilla_b": PLANILLA_B}

    async with AsyncSessionLocal() as db:
        await _cleanup(db)


@pytest.mark.asyncio
async def test_planillas_disponibles_calcula_local_nacional(client, auth_headers, pc_data):
    r = await client.get(
        "/api/pagos-ciudades/planillas",
        params={"cod_mensajero": pc_data["cod_mensajero"], "desde": "2026-06-01", "hasta": "2026-06-30"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    rows = {row["planilla"]: row for row in r.json()}
    assert pc_data["planilla_a"] in rows
    assert pc_data["planilla_b"] in rows

    a = rows[pc_data["planilla_a"]]
    assert a["cantidad_local"] == 1
    assert a["cantidad_nacional"] == 1
    assert a["valor_total"] == 1300.0
    assert a["ya_incluida"] is False

    b = rows[pc_data["planilla_b"]]
    assert b["cantidad_local"] == 2
    assert b["cantidad_nacional"] == 0
    assert b["valor_total"] == 1000.0


@pytest.mark.asyncio
async def test_crear_prefactura_y_marca_planillas_incluidas(client, auth_headers, pc_data):
    r = await client.post(
        "/api/pagos-ciudades/prefacturas",
        json={
            "cod_mensajero": pc_data["cod_mensajero"],
            "periodo_desde": "2026-06-01",
            "periodo_hasta": "2026-06-30",
            "planillas": [pc_data["planilla_a"]],
            "notas": "prefactura de prueba",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["estado"] == "borrador"
    assert data["cantidad_planillas"] == 1
    assert data["valor_total"] == 1300.0
    assert len(data["planillas"]) == 1
    pc_data["prefactura_id"] = data["id"]

    # Duplicado -> 409
    r2 = await client.post(
        "/api/pagos-ciudades/prefacturas",
        json={
            "cod_mensajero": pc_data["cod_mensajero"],
            "periodo_desde": "2026-06-01",
            "periodo_hasta": "2026-06-30",
            "planillas": [pc_data["planilla_a"]],
        },
        headers=auth_headers,
    )
    assert r2.status_code == 409

    # ya_incluida debe reflejarse
    r3 = await client.get(
        "/api/pagos-ciudades/planillas",
        params={"cod_mensajero": pc_data["cod_mensajero"], "desde": "2026-06-01", "hasta": "2026-06-30"},
        headers=auth_headers,
    )
    rows = {row["planilla"]: row for row in r3.json()}
    assert rows[pc_data["planilla_a"]]["ya_incluida"] is True
    assert rows[pc_data["planilla_b"]]["ya_incluida"] is False


@pytest.mark.asyncio
async def test_ajustar_monto_prefactura(client, auth_headers, pc_data):
    prefactura_id = pc_data["prefactura_id"]

    r = await client.put(
        f"/api/pagos-ciudades/prefacturas/{prefactura_id}/ajuste",
        json={"valor_ajustado": 1100.0, "notas_ajuste": "Descuento acordado con el proveedor"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["valor_total"] == 1300.0  # el calculado no cambia
    assert data["valor_ajustado"] == 1100.0
    assert data["valor_a_pagar"] == 1100.0
    assert data["notas_ajuste"] == "Descuento acordado con el proveedor"

    # Se refleja en el listado
    r2 = await client.get("/api/pagos-ciudades/prefacturas", params={"cod_mensajero": pc_data["cod_mensajero"]}, headers=auth_headers)
    fila = next(p for p in r2.json() if p["id"] == prefactura_id)
    assert fila["valor_a_pagar"] == 1100.0

    # Revertir al monto calculado
    r3 = await client.put(
        f"/api/pagos-ciudades/prefacturas/{prefactura_id}/ajuste",
        json={"valor_ajustado": None, "notas_ajuste": None},
        headers=auth_headers,
    )
    assert r3.status_code == 200
    assert r3.json()["valor_ajustado"] is None
    assert r3.json()["valor_a_pagar"] == 1300.0


@pytest.mark.asyncio
async def test_flujo_aprobar_facturar_pagar(client, auth_headers, pc_data):
    prefactura_id = pc_data["prefactura_id"]

    # Eliminar en borrador está permitido, pero aquí seguimos el flujo de aprobación
    r = await client.post(f"/api/pagos-ciudades/prefacturas/{prefactura_id}/aprobar", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["estado"] == "aprobada"

    # Aprobar de nuevo -> 400
    r_dup = await client.post(f"/api/pagos-ciudades/prefacturas/{prefactura_id}/aprobar", headers=auth_headers)
    assert r_dup.status_code == 400

    # Ya aprobada -> ya no se puede ajustar el monto
    r_ajuste = await client.put(
        f"/api/pagos-ciudades/prefacturas/{prefactura_id}/ajuste",
        json={"valor_ajustado": 999.0, "notas_ajuste": None},
        headers=auth_headers,
    )
    assert r_ajuste.status_code == 400

    vencida = (date.today() - timedelta(days=1)).isoformat()
    r2 = await client.post(
        f"/api/pagos-ciudades/prefacturas/{prefactura_id}/registrar-factura",
        json={
            "numero_factura": "FAC-PC-001",
            "fecha_vencimiento": vencida,
            "valor_total": 1300.0,
        },
        headers=auth_headers,
    )
    assert r2.status_code == 200, r2.text
    cxp = r2.json()
    assert cxp["estado"] == "pendiente"
    cxp_id = cxp["id"]

    r3 = await client.get(f"/api/pagos-ciudades/prefacturas", params={"estado": "facturada"}, headers=auth_headers)
    assert any(p["id"] == prefactura_id for p in r3.json())

    # GET /cxp debe marcarla vencida automáticamente (fecha_vencimiento en el pasado)
    r4 = await client.get("/api/pagos-ciudades/cxp", headers=auth_headers)
    assert r4.status_code == 200
    cxp_row = next(c for c in r4.json() if c["id"] == cxp_id)
    assert cxp_row["estado"] == "vencida"

    hoy = date.today().isoformat()
    r5 = await client.post(
        f"/api/pagos-ciudades/cxp/{cxp_id}/pagar",
        json={"fecha_pago": hoy},
        headers=auth_headers,
    )
    assert r5.status_code == 200
    assert r5.json()["estado"] == "pagada"
    assert r5.json()["fecha_pago"] == hoy

    # Pagar de nuevo -> 400
    r6 = await client.post(
        f"/api/pagos-ciudades/cxp/{cxp_id}/pagar",
        json={"fecha_pago": hoy},
        headers=auth_headers,
    )
    assert r6.status_code == 400


@pytest.mark.asyncio
async def test_crear_prefactura_con_ajuste_inicial(client, auth_headers, pc_data):
    r = await client.post(
        "/api/pagos-ciudades/prefacturas",
        json={
            "cod_mensajero": pc_data["cod_mensajero"],
            "periodo_desde": "2026-06-01",
            "periodo_hasta": "2026-06-30",
            "planillas": [pc_data["planilla_b"]],
            "valor_ajustado": 900.0,
            "notas_ajuste": "Ajuste definido al generar",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["valor_total"] == 1000.0
    assert data["valor_ajustado"] == 900.0
    assert data["valor_a_pagar"] == 900.0
    assert data["notas_ajuste"] == "Ajuste definido al generar"

    r2 = await client.delete(f"/api/pagos-ciudades/prefacturas/{data['id']}", headers=auth_headers)
    assert r2.status_code == 204


@pytest.mark.asyncio
async def test_eliminar_prefactura_no_borrador_falla(client, auth_headers, pc_data):
    # La prefactura del test anterior ya está "facturada"
    r = await client.delete(f"/api/pagos-ciudades/prefacturas/{pc_data['prefactura_id']}", headers=auth_headers)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_eliminar_prefactura_en_borrador_ok(client, auth_headers, pc_data):
    r = await client.post(
        "/api/pagos-ciudades/prefacturas",
        json={
            "cod_mensajero": pc_data["cod_mensajero"],
            "periodo_desde": "2026-06-01",
            "periodo_hasta": "2026-06-30",
            "planillas": [pc_data["planilla_b"]],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201
    new_id = r.json()["id"]

    r2 = await client.delete(f"/api/pagos-ciudades/prefacturas/{new_id}", headers=auth_headers)
    assert r2.status_code == 204
