"""Tests de integración para /api/devoluciones."""
import io

import pandas as pd
import pytest
from sqlalchemy import delete

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def limpiar_devoluciones():
    """Borra los seriales de prueba antes y después de cada test."""
    from app.database import AsyncSessionLocal
    from app.models.devoluciones import Devolucion

    seriales = ["DEV-TEST-001", "DEV-TEST-002"]

    async def _limpiar():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Devolucion).where(Devolucion.serial.in_(seriales)))
            await db.commit()

    await _limpiar()
    yield
    await _limpiar()


def _xlsx(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ── Carga masiva ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_carga_masiva_inserta_nuevas_con_estado_transito(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {
            "serial": "DEV-TEST-001",
            "nombre": "Juan Perez",
            "telefono": "573001112233",
            "direccion": "CLL 1 2 3",
            "localidad": "Chapinero",
        },
    ])
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_filas"] == 1
    assert data["nuevas"] == 1
    assert data["actualizadas"] == 0
    assert data["errores"] == []

    r = await client.get("/api/devoluciones/", params={"q": "DEV-TEST-001"}, headers=headers)
    filas = r.json()
    assert len(filas) == 1
    assert filas[0]["estado"] == "transito"
    assert filas[0]["nombre"] == "Juan Perez"


@pytest.mark.asyncio
async def test_carga_masiva_reupload_actualiza_contacto_sin_pisar_estado(
    client, headers, limpiar_devoluciones
):
    contenido = _xlsx([
        {
            "serial": "DEV-TEST-002",
            "nombre": "Ana Gomez",
            "telefono": "573004445566",
            "direccion": "KRA 5 6 7",
            "localidad": "Usaquen",
        },
    ])
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    devolucion_id = (
        await client.get("/api/devoluciones/", params={"q": "DEV-TEST-002"}, headers=headers)
    ).json()[0]["id"]

    r = await client.patch(
        f"/api/devoluciones/{devolucion_id}", json={"estado": "entregado"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "entregado"

    contenido_actualizado = _xlsx([
        {
            "serial": "DEV-TEST-002",
            "nombre": "Ana Gomez Actualizada",
            "telefono": "573009998877",
            "direccion": "KRA 5 6 7 APTO 8",
            "localidad": "Usaquen",
        },
    ])
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido_actualizado),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nuevas"] == 0
    assert data["actualizadas"] == 1

    fila = (
        await client.get("/api/devoluciones/", params={"q": "DEV-TEST-002"}, headers=headers)
    ).json()[0]
    assert fila["nombre"] == "Ana Gomez Actualizada"
    assert fila["direccion"] == "KRA 5 6 7 APTO 8"
    assert fila["estado"] == "entregado"


@pytest.mark.asyncio
async def test_carga_masiva_solo_acepta_xlsx(client, headers):
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.csv", io.BytesIO(b"serial,nombre\nA,B\n"), "text/csv")},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_carga_masiva_columnas_faltantes(client, headers):
    contenido = _xlsx([{"serial": "DEV-TEST-999", "nombre": "X"}])
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert r.status_code == 400
    assert "faltantes" in r.json()["detail"].lower()


# ── PATCH estado ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_estado_devolucion_inexistente(client, headers):
    r = await client.patch("/api/devoluciones/999999999", json={"estado": "entregado"}, headers=headers)
    assert r.status_code == 404


# ── Listado con filtro por estado ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_filtra_por_estado(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    r = await client.get("/api/devoluciones/", params={"estado": "transito", "q": "DEV-TEST-001"}, headers=headers)
    assert any(f["serial"] == "DEV-TEST-001" for f in r.json())

    r = await client.get("/api/devoluciones/", params={"estado": "entregado", "q": "DEV-TEST-001"}, headers=headers)
    assert all(f["serial"] != "DEV-TEST-001" for f in r.json())
