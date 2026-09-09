"""Tests de integración para /api/devoluciones."""
import io
from datetime import date

import pandas as pd
import pytest
from docx import Document
from openpyxl import load_workbook
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


@pytest.mark.asyncio
async def test_carga_masiva_telefono_demasiado_largo(client, headers):
    """Un campo que excede el límite de columna se reporta por fila (200 +
    errores[]), no debe tumbar toda la carga con un 500."""
    contenido = _xlsx([{
        "serial": "DEV-TEST-LARGO",
        "nombre": "X",
        "telefono": "3001234567 / 3009876543",  # 24 chars, excede VARCHAR(20)
        "direccion": "Cra 1",
        "localidad": "Bogota",
    }])
    r = await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nuevas"] == 0
    assert data["actualizadas"] == 0
    assert any("telefono" in e.lower() for e in data["errores"])


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


# ── Escaneo por serial ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_escanear_serial_actualiza_estado_devolucion(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )

    r = await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "devolucion"

    fila = (
        await client.get("/api/devoluciones/", params={"q": "DEV-TEST-001"}, headers=headers)
    ).json()[0]
    assert fila["estado"] == "devolucion"


@pytest.mark.asyncio
async def test_escanear_serial_inexistente_404(client, headers):
    r = await client.patch(
        "/api/devoluciones/serial/DEV-NO-EXISTE", json={"estado": "devolucion"}, headers=headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_escanear_serial_avisa_ya_escaneado(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )

    r1 = await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )
    assert r1.status_code == 200, r1.text
    data1 = r1.json()
    assert data1["estado"] == "devolucion"
    assert data1["ya_escaneado"] is False
    assert data1["escaneado_previamente_en"] is None
    assert data1["fecha_escaneo"] is not None

    r2 = await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["estado"] == "devolucion"
    assert data2["ya_escaneado"] is True
    assert data2["escaneado_previamente_en"] == data1["fecha_escaneo"]


# ── Reporte del día (JSON + exportaciones) ─────────────────────────────────

@pytest.mark.asyncio
async def test_escaneados_dia_filtra_por_fecha_y_estado(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )

    r = await client.get("/api/devoluciones/escaneados-dia", headers=headers)
    assert r.status_code == 200, r.text
    assert any(f["serial"] == "DEV-TEST-001" for f in r.json())

    r = await client.get(
        "/api/devoluciones/escaneados-dia", params={"fecha": "2020-01-01"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert all(f["serial"] != "DEV-TEST-001" for f in r.json())


@pytest.mark.asyncio
async def test_reporte_dia_word(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )

    r = await client.get(
        "/api/devoluciones/reporte-dia/word",
        params={"fecha": date.today().isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    doc = Document(io.BytesIO(r.content))
    seriales = [row.cells[0].text for row in doc.tables[0].rows[1:]]
    assert "DEV-TEST-001" in seriales


@pytest.mark.asyncio
async def test_reporte_dia_word_404_sin_datos(client, headers):
    r = await client.get(
        "/api/devoluciones/reporte-dia/word", params={"fecha": "1999-01-01"}, headers=headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reporte_dia_excel(client, headers, limpiar_devoluciones):
    contenido = _xlsx([
        {"serial": "DEV-TEST-001", "nombre": "Juan", "telefono": "1", "direccion": "A", "localidad": "B"},
    ])
    await client.post(
        "/api/devoluciones/carga-masiva",
        files={"file": ("dev.xlsx", io.BytesIO(contenido),
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=headers,
    )
    await client.patch(
        "/api/devoluciones/serial/DEV-TEST-001", json={"estado": "devolucion"}, headers=headers
    )

    r = await client.get(
        "/api/devoluciones/reporte-dia/excel",
        params={"fecha": date.today().isoformat()},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    valores = [c.value for row in ws.iter_rows() for c in row]
    assert "DEV-TEST-001" in valores


@pytest.mark.asyncio
async def test_reporte_dia_excel_404_sin_datos(client, headers):
    r = await client.get(
        "/api/devoluciones/reporte-dia/excel", params={"fecha": "1999-01-01"}, headers=headers
    )
    assert r.status_code == 404


# ── Generación de acta .docx ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generar_documento_devolucion(client, headers):
    body = {
        "items": [
            {"serial": "DEV-TEST-001", "nombre": "Juan Perez", "direccion": "CLL 1 2 3", "localidad": "Chapinero"},
            {"serial": "DEV-TEST-002", "nombre": "Ana Gomez", "direccion": "KRA 5 6 7", "localidad": "Usaquen"},
        ]
    }
    r = await client.post("/api/devoluciones/documento", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    doc = Document(io.BytesIO(r.content))
    assert doc.paragraphs[0].text == "ACTA DE DEVOLUCIÓN"
    tabla = doc.tables[0]
    assert len(tabla.rows) == 3  # encabezado + 2 items
    assert tabla.rows[1].cells[0].text == "DEV-TEST-001"


@pytest.mark.asyncio
async def test_generar_documento_items_vacios_422(client, headers):
    r = await client.post("/api/devoluciones/documento", json={"items": []}, headers=headers)
    assert r.status_code == 422
