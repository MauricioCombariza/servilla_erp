"""Tests de integración para /api/devoluciones."""
import io
from datetime import date

import pandas as pd
import pytest
from docx import Document
from openpyxl import load_workbook
from sqlalchemy import delete, select

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


# ── Cancelados por la aplicación ──────────────────────────────────────────────

CANC_NUEVO = "9990000001001"     # en la base de despacho, no en devoluciones
CANC_EXISTE = "9990000001002"    # ya en devoluciones como transito
CANC_SIN_BASE = "9990000001003"  # ni en la base ni en devoluciones


@pytest.fixture
async def limpiar_cancelados():
    from app.database import AsyncSessionLocal
    from app.models.devoluciones import Devolucion
    from app.models.paquetes_despacho import PaqueteDespacho

    seriales = [CANC_NUEVO, CANC_EXISTE, CANC_SIN_BASE]

    async def _borrar():
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Devolucion).where(Devolucion.serial.in_(seriales)))
            await db.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.in_(seriales)))
            await db.commit()

    await _borrar()
    async with AsyncSessionLocal() as db:
        db.add(PaqueteDespacho(serial=CANC_NUEVO, nombre="Cliente Cancelado", telefono="3001234567",
                               direccion="CL 1 # 2-3", localidad="Suba", zona="70_1", f_emi=date(2026, 11, 1)))
        db.add(Devolucion(serial=CANC_EXISTE, estado="transito"))
        await db.commit()
    yield
    await _borrar()


async def test_cancelados_crea_actualiza_y_rechaza_invalidos(client, headers, limpiar_cancelados):
    r = await client.post(
        "/api/devoluciones/cancelados",
        json={"seriales": [CANC_NUEVO, f" {CANC_EXISTE} ", CANC_SIN_BASE, CANC_NUEVO, "2610212648301", "21"]},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert {i["serial"]: (i["resultado"], i["estado_anterior"], i["en_base"]) for i in body["items"]} == {
        CANC_NUEVO: ("nuevo", None, True),
        CANC_EXISTE: ("actualizado", "transito", False),
        CANC_SIN_BASE: ("nuevo", None, False),
        "2610212648301": ("invalido", None, False),  # código de tula
        "21": ("invalido", None, False),             # lectura cortada
    }
    assert (body["nuevos"], body["actualizados"], body["ya_cancelados"], body["invalidos"]) == (2, 1, 0, 2)

    from app.database import AsyncSessionLocal
    from app.models.devoluciones import Devolucion

    async with AsyncSessionLocal() as db:
        devs = {d.serial: d for d in (await db.execute(
            select(Devolucion).where(Devolucion.serial.in_([CANC_NUEVO, CANC_EXISTE, CANC_SIN_BASE, "21"]))
        )).scalars()}
    assert set(devs) == {CANC_NUEVO, CANC_EXISTE, CANC_SIN_BASE}
    assert all(d.estado == "cancelado" and d.fecha_escaneo is not None for d in devs.values())
    assert (devs[CANC_NUEVO].nombre, devs[CANC_NUEVO].localidad) == ("Cliente Cancelado", "Suba")

    # Repetir no cambia nada
    r = await client.post("/api/devoluciones/cancelados", json={"seriales": [CANC_NUEVO]}, headers=headers)
    assert r.json()["items"][0]["resultado"] == "ya_cancelado"


async def test_cancelado_cuenta_como_devolucion_al_verificar(client, headers, limpiar_cancelados):
    await client.post("/api/devoluciones/cancelados", json={"seriales": [CANC_SIN_BASE]}, headers=headers)
    r = await client.post("/api/devoluciones/verificar-seriales", json={"seriales": [CANC_SIN_BASE]}, headers=headers)
    item = r.json()["items"][0]
    assert (item["clasificacion"], item["estado_detalle"]) == ("devolucion", "cancelado")
