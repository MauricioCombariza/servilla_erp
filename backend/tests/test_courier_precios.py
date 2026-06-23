"""Tests de integración: precios de courier_externo en planillas."""
import pytest
from datetime import date


@pytest.fixture(scope="module")
async def auth_headers(client):
    """Crea usuario de test temporal y retorna sus headers de autorización."""
    import bcrypt
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    pwd_hash = bcrypt.hashpw(b"test-courier-pw", bcrypt.gensalt()).decode()

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_courier_user'"))
        await db.execute(
            text("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                VALUES ('test_courier_user', :h, 'Test Courier', 'administrador', TRUE)
            """),
            {"h": pwd_hash},
        )
        await db.commit()

    r = await client.post(
        "/api/auth/login",
        json={"username": "test_courier_user", "password": "test-courier-pw"},
    )
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'test_courier_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def courier_data():
    """Crea courier_externo + 4 seriales (2 bogota, 2 nacional). Limpia al final."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    PLANILLA = "TEST-COU-001"

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE planilla = :p"), {"p": PLANILLA})
        await db.execute(text("DELETE FROM personal WHERE codigo = 'CT01'"))
        await db.commit()

        r = await db.execute(
            text("""
                INSERT INTO personal (codigo, nombre_completo, identificacion,
                                      tipo_personal, precio_local, precio_nacional, activo)
                VALUES ('CT01', 'Courier Test', '999999TEST',
                        'courier_externo', 500, 800, TRUE)
                RETURNING id
            """)
        )
        courier_id = r.scalar_one()
        await db.commit()

        for serial, ambito in [
            ("COU-001", "bogota"),
            ("COU-002", "bogota"),
            ("COU-003", "nacional"),
            ("COU-004", "nacional"),
        ]:
            await db.execute(
                text("""
                    INSERT INTO seriales_gestion
                        (serial, planilla, f_esc, cod_men, mensajero_id,
                         tipo_gestion, tipo_envio, ambito, estado,
                         precio_mensajero, precio_cliente, origen)
                    VALUES
                        (:serial, :planilla, '2026-06-10', 'CT01', :mid,
                         'Entrega', 'sobre', :ambito, 'pendiente', 0, 0, 'manual')
                """),
                {"serial": serial, "planilla": PLANILLA, "mid": courier_id, "ambito": ambito},
            )
        await db.commit()

    yield {"planilla": PLANILLA, "courier_id": courier_id}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE planilla = :p"), {"p": PLANILLA})
        await db.execute(text("DELETE FROM personal WHERE codigo = 'CT01'"))
        await db.commit()


@pytest.mark.asyncio
async def test_precio_courier_actualiza_cada_serial(client, auth_headers, courier_data):
    """Cada serial recibe el precio correcto según su ambito (bogota→local, resto→nacional)."""
    planilla = courier_data["planilla"]

    r = await client.post(
        f"/api/gestiones/planillas/{planilla}/precio-courier",
        json={"precio_local": 650, "precio_nacional": 950},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["bogota"] == 2
    assert data["nacional"] == 2
    assert data["seriales_actualizados"] == 4

    r2 = await client.get(f"/api/gestiones/?planilla={planilla}", headers=auth_headers)
    assert r2.status_code == 200
    seriales = r2.json()
    assert len(seriales) == 4
    for sg in seriales:
        assert sg["editado_manualmente"] is True
        if sg["ambito"] == "bogota":
            assert sg["precio_mensajero"] == 650.0, f"{sg['serial']} bogota debería ser 650"
        else:
            assert sg["precio_mensajero"] == 950.0, f"{sg['serial']} nacional debería ser 950"


@pytest.mark.asyncio
async def test_precio_courier_actualiza_personal(client, auth_headers, courier_data):
    """El campo personal.precio_local/precio_nacional queda actualizado tras guardar."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    planilla = courier_data["planilla"]
    courier_id = courier_data["courier_id"]

    await client.post(
        f"/api/gestiones/planillas/{planilla}/precio-courier",
        json={"precio_local": 700, "precio_nacional": 1000},
        headers=auth_headers,
    )

    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT precio_local, precio_nacional FROM personal WHERE id = :id"),
            {"id": courier_id},
        )).mappings().one()

    assert int(row["precio_local"]) == 700, "personal.precio_local no se actualizó"
    assert int(row["precio_nacional"]) == 1000, "personal.precio_nacional no se actualizó"


@pytest.mark.asyncio
async def test_precio_courier_resumen_refleja_nuevas_tarifas(client, auth_headers, courier_data):
    """El resumen de planillas refleja los nuevos precios local/nacional tras guardar."""
    planilla = courier_data["planilla"]

    await client.post(
        f"/api/gestiones/planillas/{planilla}/precio-courier",
        json={"precio_local": 720, "precio_nacional": 1050},
        headers=auth_headers,
    )

    r = await client.get(
        "/api/gestiones/planillas/resumen",
        params={"planilla": planilla},
        headers=auth_headers,
    )
    assert r.status_code == 200
    grupo = next(d for d in r.json() if d["planilla"] == planilla)
    assert grupo["precio_local_mensajero"] == 720.0
    assert grupo["precio_nacional_mensajero"] == 1050.0
