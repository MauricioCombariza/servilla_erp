"""Tests de integración para /api/gestiones."""
import pytest
from datetime import date, datetime

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
async def seriales_test(headers):
    """Inserta seriales de prueba directamente en BD. Limpia al final."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    PLANILLA_A = "TEST-PLA-001"
    PLANILLA_B = "TEST-PLA-002"
    D1 = date(2026, 6, 1)
    D2 = date(2026, 6, 2)
    seriales = [
        # planilla A — cod_men MN01 — desbloqueados
        dict(serial="TST-001", planilla=PLANILLA_A, f_esc=D1, cod_men="MN01",
             tipo_gestion="Entrega", precio_mensajero=1300, precio_cliente=4000),
        dict(serial="TST-002", planilla=PLANILLA_A, f_esc=D1, cod_men="MN01",
             tipo_gestion="Devolucion", precio_mensajero=900, precio_cliente=2500),
        dict(serial="TST-003", planilla=PLANILLA_A, f_esc=D1, cod_men="MN01",
             tipo_gestion="Entrega", precio_mensajero=0, precio_cliente=0),
        # planilla B — cod_men MN02 — uno bloqueado
        dict(serial="TST-004", planilla=PLANILLA_B, f_esc=D2, cod_men="MN02",
             tipo_gestion="Entrega", precio_mensajero=1500, precio_cliente=4500,
             editado_manualmente=True),
        dict(serial="TST-005", planilla=PLANILLA_B, f_esc=D2, cod_men="MN02",
             tipo_gestion="Entrega", precio_mensajero=1500, precio_cliente=4500),
    ]

    async with AsyncSessionLocal() as db:
        # Limpiar posibles restos de corridas anteriores
        await db.execute(
            text("DELETE FROM seriales_gestion WHERE serial LIKE 'TST-%'")
        )
        await db.commit()

        for s in seriales:
            await db.execute(
                text("""
                    INSERT INTO seriales_gestion
                        (serial, planilla, f_esc, cod_men, tipo_gestion,
                         precio_mensajero, precio_cliente,
                         editado_manualmente, origen)
                    VALUES
                        (:serial, :planilla, :f_esc, :cod_men, :tipo_gestion,
                         :precio_mensajero, :precio_cliente,
                         :editado, 'manual')
                """),
                {
                    "serial": s["serial"],
                    "planilla": s["planilla"],
                    "f_esc": s["f_esc"],
                    "cod_men": s["cod_men"],
                    "tipo_gestion": s["tipo_gestion"],
                    "precio_mensajero": s.get("precio_mensajero", 0),
                    "precio_cliente": s.get("precio_cliente", 0),
                    "editado": s.get("editado_manualmente", False),
                },
            )
        await db.commit()

    yield {"planilla_a": PLANILLA_A, "planilla_b": PLANILLA_B}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'TST-%'"))
        await db.commit()


# ── Tests de seriales ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_seriales(client, headers, seriales_test):
    r = await client.get("/api/gestiones/", headers=headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_list_filtro_planilla(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]
    r = await client.get(f"/api/gestiones/?planilla={planilla}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert all(d["planilla"] == planilla for d in data)


@pytest.mark.asyncio
async def test_get_serial(client, headers, seriales_test):
    # Obtener ID del primer serial
    planilla = seriales_test["planilla_a"]
    r = await client.get(f"/api/gestiones/?planilla={planilla}", headers=headers)
    serial_id = r.json()[0]["id"]

    r2 = await client.get(f"/api/gestiones/{serial_id}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["planilla"] == planilla


@pytest.mark.asyncio
async def test_patch_serial(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]
    r = await client.get(f"/api/gestiones/?planilla={planilla}", headers=headers)
    serial_id = r.json()[0]["id"]

    r2 = await client.patch(
        f"/api/gestiones/{serial_id}",
        json={"observaciones": "Test observacion"},
        headers=headers,
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["observaciones"] == "Test observacion"
    assert data["editado_manualmente"] is True  # se bloquea automáticamente


@pytest.mark.asyncio
async def test_serial_no_existe(client, headers):
    r = await client.get("/api/gestiones/999999", headers=headers)
    assert r.status_code == 404


# ── Tests de planillas resumen ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_planillas_resumen(client, headers, seriales_test):
    r = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"fecha_desde": "2026-06-01", "fecha_hasta": "2026-06-02"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    planillas = {d["planilla"] for d in data}
    assert seriales_test["planilla_a"] in planillas
    assert seriales_test["planilla_b"] in planillas


@pytest.mark.asyncio
async def test_resumen_con_precio_cero(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]
    r = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"fecha_desde": "2026-06-01", "fecha_hasta": "2026-06-01"},
        headers=headers,
    )
    assert r.status_code == 200
    grupo = next(d for d in r.json() if d["planilla"] == planilla)
    assert grupo["con_precio_cero"] == 1  # TST-003 tiene precio_mensajero=0
    assert grupo["entregas"] == 2
    assert grupo["devoluciones"] == 1


@pytest.mark.asyncio
async def test_resumen_bloqueada(client, headers, seriales_test):
    planilla = seriales_test["planilla_b"]
    r = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"fecha_desde": "2026-06-02", "fecha_hasta": "2026-06-02"},
        headers=headers,
    )
    assert r.status_code == 200
    grupo = next(d for d in r.json() if d["planilla"] == planilla)
    assert grupo["bloqueada"] is False  # TST-005 sigue desbloqueado


# ── Tests de operaciones en lote ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cambiar_precio_planilla(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]

    # Desbloquear primero (por si test anterior bloqueó alguno)
    await client.delete(f"/api/gestiones/planillas/{planilla}/bloquear", headers=headers)

    r = await client.patch(
        f"/api/gestiones/planillas/{planilla}/precio",
        json={"precio_mensajero": 1400},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["seriales_actualizados"] >= 1

    # Verificar que los seriales no bloqueados actualizaron precio
    r2 = await client.get(f"/api/gestiones/?planilla={planilla}", headers=headers)
    for sg in r2.json():
        if sg["editado_manualmente"]:
            assert sg["precio_mensajero"] == 1400.0


@pytest.mark.asyncio
async def test_bloquear_planilla(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]
    r = await client.post(f"/api/gestiones/planillas/{planilla}/bloquear", headers=headers)
    assert r.status_code == 200
    assert r.json()["seriales_actualizados"] >= 0

    # Ahora el resumen debe mostrar bloqueada=True
    r2 = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"fecha_desde": "2026-06-01", "fecha_hasta": "2026-06-01"},
        headers=headers,
    )
    grupo = next(d for d in r2.json() if d["planilla"] == planilla)
    assert grupo["bloqueada"] is True


@pytest.mark.asyncio
async def test_desbloquear_planilla(client, headers, seriales_test):
    planilla = seriales_test["planilla_a"]
    r = await client.delete(f"/api/gestiones/planillas/{planilla}/bloquear", headers=headers)
    assert r.status_code == 200

    r2 = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"fecha_desde": "2026-06-01", "fecha_hasta": "2026-06-01"},
        headers=headers,
    )
    grupo = next(d for d in r2.json() if d["planilla"] == planilla)
    assert grupo["bloqueada"] is False


@pytest.mark.asyncio
async def test_cambiar_precio_no_toca_bloqueados(client, headers, seriales_test):
    planilla = seriales_test["planilla_b"]
    r = await client.patch(
        f"/api/gestiones/planillas/{planilla}/precio",
        json={"precio_mensajero": 999},
        headers=headers,
    )
    assert r.status_code == 200
    # TST-004 está bloqueado → no se actualiza; TST-005 sí
    assert r.json()["seriales_actualizados"] == 1

    # TST-004 debe seguir con precio original
    r2 = await client.get(f"/api/gestiones/?planilla={planilla}", headers=headers)
    bloqueado = next(s for s in r2.json() if s["editado_manualmente"])
    assert bloqueado["precio_mensajero"] == 1500.0
