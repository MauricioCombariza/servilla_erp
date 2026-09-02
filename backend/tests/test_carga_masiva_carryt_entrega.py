"""
Tests del flujo 4 de carga-masiva: confirmación de entrega Carryt.

Formato: Cliente, fecha, serial, cod_men, nombre_mensajero — solo actualiza
seriales_gestion ya existentes (nunca crea seriales/órdenes nuevos).
"""
import io
from datetime import date

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.ordenes_service import _es_flujo_carryt_entrega

_CLIENTE_NIT = "TEST-CARRYT-NIT-001"
_CLIENTE_NOMBRE = "Carryt Test"
_OTRO_CLIENTE_NIT = "TEST-CARRYT-OTRO-NIT"
_OTRO_CLIENTE_NOMBRE = "Otro Cliente Carryt Test"
_COD_MEN = "0209"
_MENSAJERO_NOMBRE = "Elber Jimenez Test"
_FECHA = "2026-08-11"
_FECHA_VIEJA = "2025-12-31"  # < DATE_CORTE


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def auth_headers(client):
    import bcrypt
    pwd_hash = bcrypt.hashpw(b"carryt-test-pw", bcrypt.gensalt()).decode()
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'carryt_test_user'"))
        await db.execute(
            text("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                VALUES ('carryt_test_user', :h, 'Carryt Test', 'administrador', TRUE)
            """),
            {"h": pwd_hash},
        )
        await db.commit()

    r = await client.post("/api/auth/login",
                          json={"username": "carryt_test_user", "password": "carryt-test-pw"})
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'carryt_test_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def maestros():
    """Cliente Carryt Test, un segundo cliente (para el caso de mismatch) y un
    mensajero activo con código _COD_MEN."""
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": _COD_MEN})
        await db.execute(text("DELETE FROM clientes WHERE nit IN (:n1, :n2)"),
                         {"n1": _CLIENTE_NIT, "n2": _OTRO_CLIENTE_NIT})
        await db.commit()

        r = await db.execute(
            text("""
                INSERT INTO clientes (nombre_empresa, nit, ciudad, activo)
                VALUES (:nom, :nit, 'Bogotá', TRUE) RETURNING id
            """),
            {"nom": _CLIENTE_NOMBRE, "nit": _CLIENTE_NIT},
        )
        cliente_id = r.scalar_one()

        r2 = await db.execute(
            text("""
                INSERT INTO clientes (nombre_empresa, nit, ciudad, activo)
                VALUES (:nom, :nit, 'Bogotá', TRUE) RETURNING id
            """),
            {"nom": _OTRO_CLIENTE_NOMBRE, "nit": _OTRO_CLIENTE_NIT},
        )
        otro_cliente_id = r2.scalar_one()

        r3 = await db.execute(
            text("""
                INSERT INTO personal
                    (codigo, nombre_completo, identificacion, tipo_personal, activo)
                VALUES (:cod, :nom, '0000098TEST', 'mensajero', TRUE)
                RETURNING id
            """),
            {"cod": _COD_MEN, "nom": _MENSAJERO_NOMBRE},
        )
        mensajero_id = r3.scalar_one()
        await db.commit()

    yield {"cliente_id": cliente_id, "otro_cliente_id": otro_cliente_id, "mensajero_id": mensajero_id}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'ctst%'"))
        await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": _COD_MEN})
        await db.execute(text("DELETE FROM clientes WHERE nit IN (:n1, :n2)"),
                         {"n1": _CLIENTE_NIT, "n2": _OTRO_CLIENTE_NIT})
        await db.commit()


@pytest.fixture(autouse=True)
async def limpiar_seriales_por_test(maestros):
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'ctst%'"))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'ctst%'"))
        await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _insertar_serial(
    serial: str,
    *,
    cliente_id: int,
    tipo_gestion: str = "Devolucion",
    estado: str = "pendiente",
    editado_manualmente: bool = False,
    cod_men: str = "0000",
):
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO seriales_gestion
                    (serial, planilla, f_esc, cod_men, cliente_id,
                     tipo_gestion, tipo_envio, ambito, estado,
                     editado_manualmente, origen)
                VALUES
                    (:serial, 'CTST-PLA', :fecha, :cod, :cid,
                     :tg, 'sobre', 'bogota', :estado, :em, 'manual')
            """),
            {
                "serial": serial, "fecha": date.fromisoformat(_FECHA), "cod": cod_men, "cid": cliente_id,
                "tg": tipo_gestion, "estado": estado, "em": editado_manualmente,
            },
        )
        await db.commit()


async def _leer_serial(serial: str):
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("""
                SELECT tipo_gestion, cod_men, mensajero_id, estado, editado_manualmente
                FROM seriales_gestion WHERE serial = :s
            """),
            {"s": serial},
        )).one_or_none()
    return row


def _excel_carryt(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    """rows = [(cliente, fecha, serial, cod_men, nombre_mensajero), ...]"""
    lineas = ["Cliente,fecha,serial,cod_men,nombre_mensajero"]
    lineas += [",".join(r) for r in rows]
    return ("\n".join(lineas) + "\n").encode()


async def _subir(client, auth_headers, rows):
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("carryt.csv", io.BytesIO(_excel_carryt(rows)), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Tests de detección (unitarios, sin DB) ─────────────────────────────────────

def test_deteccion_flujo_carryt_entrega():
    assert _es_flujo_carryt_entrega({"cliente", "fecha", "serial", "cod_men", "nombre_mensajero"})


def test_deteccion_no_confunde_csv_manual():
    assert not _es_flujo_carryt_entrega(
        {"orden", "serial", "fecha_recepcion", "nombre_cliente", "tipo_servicio", "ambito"}
    )


def test_deteccion_no_confunde_csv_manual_con_cod_men_opcional():
    """CSV manual puede traer cod_men opcional; sigue sin confundirse porque trae 'orden'."""
    assert not _es_flujo_carryt_entrega(
        {"orden", "serial", "fecha_recepcion", "nombre_cliente", "tipo_servicio", "ambito", "cod_men"}
    )


# ── Tests end-to-end ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_exitoso_marca_entrega_y_asigna_mensajero(client, auth_headers, maestros):
    serial = "ctst0001-aaaa-bbbb"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"], tipo_gestion="Devolucion")

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, "ctst0001-xxxx-yyyy", _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 1
    assert data["seriales_nuevos"] == 0
    assert data["ordenes_nuevas"] == 0

    row = await _leer_serial(serial)
    assert row is not None
    assert row.tipo_gestion == "Entrega"
    assert row.cod_men == _COD_MEN
    assert row.mensajero_id == maestros["mensajero_id"]
    assert row.estado == "pendiente"  # no se toca


@pytest.mark.asyncio
async def test_normalizacion_serial_ya_corto_en_db(client, auth_headers, maestros):
    """El serial en DB ya está normalizado (sin guion); el archivo trae uno con
    sufijo distinto → debe matchear igual por el primer segmento."""
    serial = "ctst0002"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"])

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, "ctst0002-suffix-nuevo", _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 1
    row = await _leer_serial(serial)
    assert row.tipo_gestion == "Entrega"


@pytest.mark.asyncio
async def test_sin_match_no_crea_nada_y_reporta_advertencia(client, auth_headers, maestros):
    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, "ctst0003-noexiste", _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 0
    assert data["seriales_nuevos"] == 0
    assert any("sin coincidencia" in e for e in data["errores"])


@pytest.mark.asyncio
async def test_match_ambiguo_no_actualiza_ninguno(client, auth_headers, maestros):
    await _insertar_serial("ctst0004-uno", cliente_id=maestros["cliente_id"])
    await _insertar_serial("ctst0004-dos", cliente_id=maestros["cliente_id"])

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, "ctst0004-tres", _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 0
    assert any("ambiguos" in e for e in data["errores"])
    for s in ("ctst0004-uno", "ctst0004-dos"):
        row = await _leer_serial(s)
        assert row.tipo_gestion == "Devolucion"  # sin cambios


@pytest.mark.asyncio
async def test_serial_editado_manualmente_queda_bloqueado(client, auth_headers, maestros):
    serial = "ctst0005"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"], editado_manualmente=True)

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, serial, _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_bloqueados"] == 1
    assert data["seriales_actualizados"] == 0
    row = await _leer_serial(serial)
    assert row.tipo_gestion == "Devolucion"


@pytest.mark.asyncio
async def test_serial_no_pendiente_queda_bloqueado(client, auth_headers, maestros):
    serial = "ctst0006"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"], estado="liquidado")

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, serial, _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_bloqueados"] == 1
    assert data["seriales_actualizados"] == 0


@pytest.mark.asyncio
async def test_cod_men_no_resuelto_no_actualiza(client, auth_headers, maestros):
    serial = "ctst0007"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"])

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, serial, "9999", "Nadie Registrado"),
    ])
    assert data["seriales_actualizados"] == 0
    assert any("cod_men no resuelto" in e for e in data["errores"])
    row = await _leer_serial(serial)
    assert row.tipo_gestion == "Devolucion"  # no hubo actualización parcial


@pytest.mark.asyncio
async def test_cliente_no_coincide_no_actualiza(client, auth_headers, maestros):
    serial = "ctst0008"
    await _insertar_serial(serial, cliente_id=maestros["otro_cliente_id"])

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA, serial, _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 0
    assert any("no coincide" in e for e in data["errores"])
    row = await _leer_serial(serial)
    assert row.tipo_gestion == "Devolucion"


@pytest.mark.asyncio
async def test_cliente_no_encontrado_no_actualiza(client, auth_headers, maestros):
    serial = "ctst0009"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"])

    data = await _subir(client, auth_headers, [
        ("Cliente Que No Existe", _FECHA, serial, _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["seriales_actualizados"] == 0
    assert any("cliente no encontrado" in e for e in data["errores"])


@pytest.mark.asyncio
async def test_fecha_antes_de_corte_se_ignora(client, auth_headers, maestros):
    serial = "ctst0010"
    await _insertar_serial(serial, cliente_id=maestros["cliente_id"])

    data = await _subir(client, auth_headers, [
        (_CLIENTE_NOMBRE, _FECHA_VIEJA, serial, _COD_MEN, _MENSAJERO_NOMBRE),
    ])
    assert data["filas_ignoradas"] == 1
    assert data["seriales_actualizados"] == 0
    row = await _leer_serial(serial)
    assert row.tipo_gestion == "Devolucion"
