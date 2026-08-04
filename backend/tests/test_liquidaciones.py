"""Tests de integración: módulo Liquidaciones (/pagos-mensajeros) — selección
explícita de planillas/días y ajuste de monto a pagar."""
import pytest
from datetime import date


@pytest.fixture(scope="module")
async def auth_headers(client):
    import bcrypt
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    pwd_hash = bcrypt.hashpw(b"test-liq-pw", bcrypt.gensalt()).decode()

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_liq_user'"))
        await db.execute(
            text("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                VALUES ('test_liq_user', :h, 'Test Liquidaciones', 'administrador', TRUE)
            """),
            {"h": pwd_hash},
        )
        await db.commit()

    r = await client.post(
        "/api/auth/login",
        json={"username": "test_liq_user", "password": "test-liq-pw"},
    )
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_liq_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def liq_data():
    """Tres personas de prueba:
    - LQ01 (mensajero): 2 planillas pendientes (A: 2 seriales x 300, B: 1 serial x 400).
    - LQ02 (alistamiento): 2 días de horas/labores aprobados y no liquidados.
    - LQ03 (mensajero): 1 planilla pendiente, usada solo para el camino legado (sin selección).
    """
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    PLANILLA_A = "TEST-LQ-A"
    PLANILLA_B = "TEST-LQ-B"
    PLANILLA_C = "TEST-LQ-C"
    COD_MEN = "LQ01"
    COD_ALIST = "LQ02"
    COD_MEN_LEGADO = "LQ03"
    DIA_1 = date(2026, 6, 5)
    DIA_2 = date(2026, 6, 10)

    async def _cleanup(db):
        codigos = [COD_MEN, COD_ALIST, COD_MEN_LEGADO]
        await db.execute(text("""
            DELETE FROM registro_horas WHERE personal_id IN (SELECT id FROM personal WHERE codigo = ANY(:c))
        """), {"c": codigos})
        await db.execute(text("""
            DELETE FROM registro_labores WHERE personal_id IN (SELECT id FROM personal WHERE codigo = ANY(:c))
        """), {"c": codigos})
        await db.execute(text("""
            DELETE FROM subsidio_transporte WHERE personal_id IN (SELECT id FROM personal WHERE codigo = ANY(:c))
        """), {"c": codigos})
        await db.execute(text("""
            DELETE FROM liquidaciones WHERE personal_id IN (SELECT id FROM personal WHERE codigo = ANY(:c))
        """), {"c": codigos})
        await db.execute(
            text("DELETE FROM seriales_gestion WHERE planilla IN (:a, :b, :c2)"),
            {"a": PLANILLA_A, "b": PLANILLA_B, "c2": PLANILLA_C},
        )
        await db.execute(text("DELETE FROM personal WHERE codigo = ANY(:c)"), {"c": codigos})
        await db.commit()

    async with AsyncSessionLocal() as db:
        await _cleanup(db)

        r = await db.execute(
            text("""
                INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo)
                VALUES (:cod, 'Mensajero Liquidaciones Test', '777701TEST', 'mensajero', TRUE)
                RETURNING id
            """),
            {"cod": COD_MEN},
        )
        mensajero_id = r.scalar_one()

        r = await db.execute(
            text("""
                INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo)
                VALUES (:cod, 'Alistamiento Liquidaciones Test', '777702TEST', 'alistamiento', TRUE)
                RETURNING id
            """),
            {"cod": COD_ALIST},
        )
        alistamiento_id = r.scalar_one()

        r = await db.execute(
            text("""
                INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo)
                VALUES (:cod, 'Mensajero Legado Test', '777703TEST', 'mensajero', TRUE)
                RETURNING id
            """),
            {"cod": COD_MEN_LEGADO},
        )
        mensajero_legado_id = r.scalar_one()
        await db.commit()

        seriales = [
            ("LQ-A-1", PLANILLA_A, mensajero_id, 300),
            ("LQ-A-2", PLANILLA_A, mensajero_id, 300),
            ("LQ-B-1", PLANILLA_B, mensajero_id, 400),
            ("LQ-C-1", PLANILLA_C, mensajero_legado_id, 700),
        ]
        for serial, planilla, pid, precio in seriales:
            await db.execute(
                text("""
                    INSERT INTO seriales_gestion
                        (serial, planilla, f_esc, cod_men, mensajero_id,
                         tipo_gestion, tipo_envio, ambito, estado,
                         precio_mensajero, precio_cliente, origen)
                    VALUES
                        (:serial, :planilla, '2026-06-08', :cod, :pid,
                         'Entrega', 'sobre', 'bogota', 'pendiente', :precio, 0, 'manual')
                """),
                {"serial": serial, "planilla": planilla, "cod": COD_MEN, "pid": pid, "precio": precio},
            )
        await db.commit()

        for dia in (DIA_1, DIA_2):
            await db.execute(
                text("""
                    INSERT INTO registro_horas
                        (personal_id, fecha, horas_trabajadas, tarifa_hora, tipo_trabajo, aprobado)
                    VALUES (:pid, :fecha, 4, 2000, 'alistamiento_sobres', TRUE)
                """),
                {"pid": alistamiento_id, "fecha": dia},
            )
        await db.execute(
            text("""
                INSERT INTO registro_labores
                    (personal_id, fecha, tipo_labor, cantidad, tarifa_unitaria, aprobado)
                VALUES (:pid, :fecha, 'pegado_guia', 10, 100, TRUE)
            """),
            {"pid": alistamiento_id, "fecha": DIA_1},
        )
        await db.commit()

    yield {
        "mensajero_id": mensajero_id,
        "alistamiento_id": alistamiento_id,
        "mensajero_legado_id": mensajero_legado_id,
        "planilla_a": PLANILLA_A,
        "planilla_b": PLANILLA_B,
        "planilla_c": PLANILLA_C,
        "dia_1": DIA_1.isoformat(),
        "dia_2": DIA_2.isoformat(),
    }

    async with AsyncSessionLocal() as db:
        await _cleanup(db)


@pytest.mark.asyncio
async def test_planillas_pendientes_mensajero_agrupa_por_planilla(client, auth_headers, liq_data):
    r = await client.get(
        f"/api/liquidaciones/planillas/{liq_data['mensajero_id']}",
        params={"mes": 6, "anio": 2026},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    rows = {row["planilla"]: row for row in r.json()}
    assert liq_data["planilla_a"] in rows
    assert liq_data["planilla_b"] in rows

    a = rows[liq_data["planilla_a"]]
    assert a["total_seriales"] == 2
    assert a["total_mensajero"] == 600.0

    b = rows[liq_data["planilla_b"]]
    assert b["total_seriales"] == 1
    assert b["total_mensajero"] == 400.0


@pytest.mark.asyncio
async def test_generar_con_planillas_explicitas_deja_resto_pendiente(client, auth_headers, liq_data):
    r = await client.post(
        "/api/liquidaciones/generar",
        json={
            "personal_id": liq_data["mensajero_id"],
            "periodo_mes": 6, "periodo_anio": 2026,
            "fecha_pago_programada": "2026-07-08",
            "planillas": [liq_data["planilla_a"]],
            "fechas_alistamiento": [],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["cantidad_entregas"] == 2
    assert data["total_entregas"] == 600.0
    assert data["total_a_pagar"] == 600.0
    liq_data["liq_id_planillas"] = data["id"]

    # La planilla B sigue pendiente y reaparece en el endpoint de selección
    r2 = await client.get(
        f"/api/liquidaciones/planillas/{liq_data['mensajero_id']}",
        params={"mes": 6, "anio": 2026},
        headers=auth_headers,
    )
    rows = {row["planilla"]: row for row in r2.json()}
    assert liq_data["planilla_a"] not in rows
    assert liq_data["planilla_b"] in rows
    assert rows[liq_data["planilla_b"]]["total_mensajero"] == 400.0

    # Selección explícita permite otra liquidación en el mismo período (no choca con la anterior)
    r3 = await client.post(
        "/api/liquidaciones/generar",
        json={
            "personal_id": liq_data["mensajero_id"],
            "periodo_mes": 6, "periodo_anio": 2026,
            "fecha_pago_programada": "2026-07-08",
            "planillas": [liq_data["planilla_b"]],
            "fechas_alistamiento": [],
        },
        headers=auth_headers,
    )
    assert r3.status_code == 201, r3.text
    assert r3.json()["total_entregas"] == 400.0


@pytest.mark.asyncio
async def test_generar_con_fechas_alistamiento_explicitas(client, auth_headers, liq_data):
    r = await client.post(
        "/api/liquidaciones/generar",
        json={
            "personal_id": liq_data["alistamiento_id"],
            "periodo_mes": 6, "periodo_anio": 2026,
            "fecha_pago_programada": "2026-07-08",
            "planillas": [],
            "fechas_alistamiento": [liq_data["dia_1"]],
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    # dia_1: 4h x 2000 = 8000 horas, + 10 x 100 = 1000 labores
    assert data["total_horas"] == 8000.0
    assert data["total_labores"] == 1000.0
    assert data["total_a_pagar"] == 9000.0
    liq_data["liq_id_fechas"] = data["id"]

    # El día 2 sigue pendiente (no liquidado)
    r2 = await client.get(
        "/api/labores/resumen/diario",
        params={"personal_id": liq_data["alistamiento_id"], "mes": 6, "anio": 2026, "aprobado": True, "liquidado": False},
        headers=auth_headers,
    )
    fechas_pendientes = {row["fecha"] for row in r2.json()}
    assert liq_data["dia_2"] in fechas_pendientes
    assert liq_data["dia_1"] not in fechas_pendientes


@pytest.mark.asyncio
async def test_generar_legado_sin_seleccion_reproduce_total_legado(client, auth_headers, liq_data):
    r = await client.post(
        "/api/liquidaciones/generar",
        json={
            "personal_id": liq_data["mensajero_legado_id"],
            "periodo_mes": 6, "periodo_anio": 2026,
            "fecha_pago_programada": "2026-07-08",
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["cantidad_entregas"] == 1
    assert data["total_entregas"] == 700.0
    assert data["total_a_pagar"] == 700.0

    # Segunda llamada legado para el mismo período -> 400 (restricción de unicidad se mantiene)
    r2 = await client.post(
        "/api/liquidaciones/generar",
        json={
            "personal_id": liq_data["mensajero_legado_id"],
            "periodo_mes": 6, "periodo_anio": 2026,
            "fecha_pago_programada": "2026-07-08",
        },
        headers=auth_headers,
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_ajustar_monto_liquidacion(client, auth_headers, liq_data):
    liq_id = liq_data["liq_id_planillas"]

    r = await client.put(
        f"/api/liquidaciones/{liq_id}/ajuste",
        json={"valor_ajustado": 550.0, "notas_ajuste": "Descuento por novedad"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_a_pagar"] == 600.0  # el calculado no cambia
    assert data["valor_ajustado"] == 550.0
    assert data["valor_a_pagar"] == 550.0
    assert data["notas_ajuste"] == "Descuento por novedad"

    # Revertir
    r2 = await client.put(
        f"/api/liquidaciones/{liq_id}/ajuste",
        json={"valor_ajustado": None, "notas_ajuste": None},
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["valor_ajustado"] is None
    assert r2.json()["valor_a_pagar"] == 600.0

    # Aprobar y confirmar que ya no se puede ajustar
    r3 = await client.post(f"/api/liquidaciones/{liq_id}/aprobar", headers=auth_headers)
    assert r3.status_code == 200
    r4 = await client.put(
        f"/api/liquidaciones/{liq_id}/ajuste",
        json={"valor_ajustado": 100.0, "notas_ajuste": None},
        headers=auth_headers,
    )
    assert r4.status_code == 400


@pytest.mark.asyncio
async def test_eliminar_liquidacion_revierte_solo_el_subconjunto_seleccionado(client, auth_headers, liq_data):
    liq_id = liq_data["liq_id_fechas"]

    r = await client.delete(f"/api/liquidaciones/{liq_id}", headers=auth_headers)
    assert r.status_code == 204

    # El día 1 vuelve a estar pendiente (no liquidado)
    r2 = await client.get(
        "/api/labores/resumen/diario",
        params={"personal_id": liq_data["alistamiento_id"], "mes": 6, "anio": 2026, "aprobado": True, "liquidado": False},
        headers=auth_headers,
    )
    fechas_pendientes = {row["fecha"] for row in r2.json()}
    assert liq_data["dia_1"] in fechas_pendientes
    assert liq_data["dia_2"] in fechas_pendientes


@pytest.mark.asyncio
async def test_pendientes_reporta_monto_sin_aprobar_y_lo_excluye_del_subtotal(client, auth_headers):
    """Horas/labores sin aprobar no deben poder liquidarse, pero /pendientes debe
    reportar cuánto quedó excluido (total_sin_aprobar) para que la UI pueda advertirlo
    en vez de mostrar un subtotal bajo sin explicación."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM registro_horas WHERE personal_id IN "
                               "(SELECT id FROM personal WHERE codigo = 'LQ04')"))
        await db.execute(text("DELETE FROM registro_labores WHERE personal_id IN "
                               "(SELECT id FROM personal WHERE codigo = 'LQ04')"))
        await db.execute(text("DELETE FROM personal WHERE codigo = 'LQ04'"))
        r = await db.execute(text("""
            INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo)
            VALUES ('LQ04', 'Alistamiento Sin Aprobar Liq Test', '777704TEST', 'alistamiento', TRUE)
            RETURNING id
        """))
        pid = r.scalar_one()
        await db.execute(text("""
            INSERT INTO registro_horas (personal_id, fecha, horas_trabajadas, tarifa_hora, tipo_trabajo, aprobado)
            VALUES (:pid, '2026-05-05', 4, 2000, 'alistamiento_sobres', FALSE)
        """), {"pid": pid})
        await db.execute(text("""
            INSERT INTO registro_labores (personal_id, fecha, tipo_labor, cantidad, tarifa_unitaria, aprobado)
            VALUES (:pid, '2026-05-05', 'pegado_guia', 5, 100, FALSE)
        """), {"pid": pid})
        await db.commit()

    try:
        r = await client.get(
            "/api/liquidaciones/pendientes",
            params={"mes": 5, "anio": 2026},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        row = next(row for row in r.json() if row["personal_id"] == pid)
        assert row["total_horas_monto"] == 0.0
        assert row["total_labores_monto"] == 0.0
        assert row["total_pendiente"] == 0.0
        assert row["total_sin_aprobar"] == 8500.0  # 4*2000 + 5*100
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM registro_horas WHERE personal_id = :pid"), {"pid": pid})
            await db.execute(text("DELETE FROM registro_labores WHERE personal_id = :pid"), {"pid": pid})
            await db.execute(text("DELETE FROM personal WHERE id = :pid"), {"pid": pid})
            await db.commit()
