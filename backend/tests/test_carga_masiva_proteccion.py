"""
Tests de protección en carga-masiva.

Verifica que:
  1. Seriales bloqueados (editado_manualmente=TRUE) NO son sobrescritos.
  2. El contador seriales_bloqueados se reporta correctamente.
  3. Seriales desbloqueados pendientes SÍ se actualizan.
  4. Nuevos seriales de courier_externo toman precio de personal, no de precios_cliente.
  5. Escenario completo: planilla bloqueada sobrevive a una carga-masiva sin perder precios.
"""
import io
import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal

# ── Constantes de test ────────────────────────────────────────────────────────

_CLIENTE_NIT  = "TEST-PROT-NIT-001"
_CLIENTE_NAME = "Cliente Proteccion Test"
_COD_CE       = "CE99"          # courier_externo de test
_PLANILLA     = "TEST-PROT-PLA"
_FECHA_CSV    = "2026-06-15"    # >= DATE_CORTE (2026-01-01)

_SERIALES = [
    "PROT-SER-001",  # serial bloqueado con precio
    "PROT-SER-002",  # serial desbloqueado
    "PROT-SER-003",  # serial nuevo (no existe en DB antes del test)
]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def auth_headers(client):
    import bcrypt
    pwd_hash = bcrypt.hashpw(b"prot-test-pw", bcrypt.gensalt()).decode()
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'prot_test_user'"))
        await db.execute(
            text("""
                INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
                VALUES ('prot_test_user', :h, 'Prot Test', 'administrador', TRUE)
            """),
            {"h": pwd_hash},
        )
        await db.commit()

    r = await client.post("/api/auth/login",
                          json={"username": "prot_test_user", "password": "prot-test-pw"})
    token = r.json()["access_token"]
    yield {"Authorization": f"Bearer {token}"}

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'prot_test_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def maestros():
    """
    Crea:
     - cliente  (_CLIENTE_NAME)
     - precio   (para que precio_cli tenga valor; precio_mensajero NO configurado → 0)
     - courier_externo (cod=CE99, precio_local=1200, precio_nacional=1800)
    Limpia todo al final.
    """
    async with AsyncSessionLocal() as db:
        # Limpiar restos de corridas anteriores
        await db.execute(text(
            "DELETE FROM seriales_gestion WHERE serial LIKE 'PROT-SER-%'"
        ))
        await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": _COD_CE})
        await db.execute(
            text("DELETE FROM clientes WHERE nit = :n"), {"n": _CLIENTE_NIT}
        )
        await db.commit()

        # Crear cliente
        r = await db.execute(
            text("""
                INSERT INTO clientes (nombre_empresa, nit, ciudad, activo)
                VALUES (:nom, :nit, 'Bogotá', TRUE)
                RETURNING id
            """),
            {"nom": _CLIENTE_NAME, "nit": _CLIENTE_NIT},
        )
        cliente_id = r.scalar_one()

        # Crear precio para ese cliente (precio_mensajero_entrega = 0 intencional
        # → prueba que courier_externo NO usa este campo)
        await db.execute(
            text("""
                INSERT INTO precios_cliente
                    (cliente_id, tipo_servicio, ambito,
                     precio_entrega, precio_devolucion,
                     costo_mensajero_entrega, costo_mensajero_devolucion,
                     vigencia_desde, activo)
                VALUES (:cid, 'sobre', 'bogota', 4000, 2500, 0, 0, '2026-01-01', TRUE)
            """),
            {"cid": cliente_id},
        )
        await db.execute(
            text("""
                INSERT INTO precios_cliente
                    (cliente_id, tipo_servicio, ambito,
                     precio_entrega, precio_devolucion,
                     costo_mensajero_entrega, costo_mensajero_devolucion,
                     vigencia_desde, activo)
                VALUES (:cid, 'sobre', 'nacional', 4500, 3000, 0, 0, '2026-01-01', TRUE)
            """),
            {"cid": cliente_id},
        )

        # Crear courier_externo con precios configurados
        r2 = await db.execute(
            text("""
                INSERT INTO personal
                    (codigo, nombre_completo, identificacion,
                     tipo_personal, precio_local, precio_nacional, activo)
                VALUES (:cod, 'Courier Externo Prot', '0000099TEST',
                        'courier_externo', 1200, 1800, TRUE)
                RETURNING id
            """),
            {"cod": _COD_CE},
        )
        courier_id = r2.scalar_one()
        await db.commit()

    yield {"cliente_id": cliente_id, "courier_id": courier_id}

    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "DELETE FROM seriales_gestion WHERE serial LIKE 'PROT-SER-%'"
        ))
        await db.execute(
            text("DELETE FROM precios_cliente WHERE cliente_id = :cid"),
            {"cid": cliente_id},
        )
        await db.execute(text("DELETE FROM personal WHERE codigo = :c"), {"c": _COD_CE})
        await db.execute(
            text("DELETE FROM clientes WHERE id = :cid"), {"cid": cliente_id}
        )
        await db.commit()


@pytest.fixture(autouse=True)
async def limpiar_seriales_por_test(maestros):
    """Limpia seriales PROT-SER-* antes de cada test para evitar interferencias."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "DELETE FROM seriales_gestion WHERE serial LIKE 'PROT-SER-%'"
        ))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            "DELETE FROM seriales_gestion WHERE serial LIKE 'PROT-SER-%'"
        ))
        await db.commit()


# ── Helper ────────────────────────────────────────────────────────────────────

async def _insertar_serial(
    serial: str,
    *,
    planilla: str = _PLANILLA,
    precio_mensajero: float = 750,
    editado_manualmente: bool = False,
    estado: str = "pendiente",
    courier_id: int | None = None,
    ambito: str = "bogota",
):
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("""
                INSERT INTO seriales_gestion
                    (serial, planilla, f_esc, cod_men, mensajero_id,
                     tipo_gestion, tipo_envio, ambito, estado,
                     precio_mensajero, precio_cliente,
                     editado_manualmente, origen)
                VALUES
                    (:serial, :planilla, '2026-06-15', :cod, :mid,
                     'Entrega', 'sobre', :ambito, :estado,
                     :pm, 0, :em, 'manual')
            """),
            {
                "serial": serial,
                "planilla": planilla,
                "cod": _COD_CE,
                "mid": courier_id,
                "ambito": ambito,
                "estado": estado,
                "pm": precio_mensajero,
                "em": editado_manualmente,
            },
        )
        await db.commit()


def _csv(serial: str, planilla: str = _PLANILLA, ambito: str = "bogota") -> bytes:
    """CSV mínimo válido con UN serial para courier_externo."""
    return (
        f"orden,serial,fecha_recepcion,nombre_cliente,tipo_servicio,ambito,planilla,cod_men\n"
        f"ORD-PROT-001,{serial},{_FECHA_CSV},{_CLIENTE_NAME},sobre,{ambito},{planilla},{_COD_CE}\n"
    ).encode()


async def _precio_en_db(serial: str) -> float:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT precio_mensajero FROM seriales_gestion WHERE serial = :s"),
            {"s": serial},
        )).one_or_none()
    return float(row[0]) if row else -1.0


async def _editado_en_db(serial: str) -> bool | None:
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT editado_manualmente FROM seriales_gestion WHERE serial = :s"),
            {"s": serial},
        )).one_or_none()
    return bool(row[0]) if row is not None else None


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_serial_bloqueado_no_se_sobrescribe(client, auth_headers, maestros):
    """
    REGRESIÓN: un serial con editado_manualmente=TRUE y precio_mensajero=750
    NO debe ser sobreescrito por carga-masiva.
    Antes del fix (83873d8) este test fallaba.
    """
    serial = _SERIALES[0]
    await _insertar_serial(serial, precio_mensajero=750, editado_manualmente=True,
                           courier_id=maestros["courier_id"])

    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial)), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()

    # El precio debe conservarse
    assert await _precio_en_db(serial) == 750.0, (
        f"El precio fue sobreescrito. Resultado de carga-masiva: {data}"
    )
    assert await _editado_en_db(serial) is True, "editado_manualmente fue cambiado"


@pytest.mark.asyncio
async def test_seriales_bloqueados_se_cuentan_en_resultado(client, auth_headers, maestros):
    """
    El campo seriales_bloqueados del resultado debe reflejar cuántos seriales
    fueron omitidos por estar bloqueados.
    """
    serial = _SERIALES[0]
    await _insertar_serial(serial, precio_mensajero=750, editado_manualmente=True,
                           courier_id=maestros["courier_id"])

    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial)), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert "seriales_bloqueados" in data, "El campo seriales_bloqueados no existe en la respuesta"
    assert data["seriales_bloqueados"] == 1, (
        f"Se esperaba seriales_bloqueados=1, got: {data['seriales_bloqueados']}"
    )
    assert data["seriales_actualizados"] == 0


@pytest.mark.asyncio
async def test_serial_desbloqueado_pendiente_si_actualizado(client, auth_headers, maestros):
    """
    Un serial con editado_manualmente=FALSE y estado='pendiente' SÍ debe
    ser procesado por carga-masiva (comportamiento normal correcto).
    """
    serial = _SERIALES[1]
    await _insertar_serial(serial, precio_mensajero=0, editado_manualmente=False,
                           courier_id=maestros["courier_id"])

    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial)), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["seriales_bloqueados"] == 0
    assert data["seriales_actualizados"] == 1


@pytest.mark.asyncio
async def test_courier_externo_nuevo_serial_usa_precio_personal(client, auth_headers, maestros):
    """
    REGRESIÓN (bug bf9b7c8): un nuevo serial de courier_externo debe tomar
    precio_mensajero de personal.precio_local/precio_nacional, NO de precios_cliente
    (que retorna 0 para courier_externo).

    courier_externo CE99 tiene precio_local=1200, precio_nacional=1800.
    Serial nuevo en bogota → precio_mensajero debe ser 1200.
    """
    serial = _SERIALES[2]  # serial no existe en DB

    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial, ambito="bogota")), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["seriales_nuevos"] == 1, f"Se esperaba 1 serial nuevo, got: {data}"

    precio = await _precio_en_db(serial)
    assert precio == 1200.0, (
        f"Precio incorrecto para courier_externo bogota: {precio} (esperado 1200). "
        f"carga-masiva usó precios_cliente en vez de personal.precio_local."
    )


@pytest.mark.asyncio
async def test_courier_externo_nuevo_serial_nacional_usa_precio_nacional(
    client, auth_headers, maestros
):
    """Serial nuevo de courier_externo con ámbito nacional → precio de personal.precio_nacional."""
    serial = _SERIALES[2]

    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial, ambito="nacional")), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    precio = await _precio_en_db(serial)
    assert precio == 1800.0, (
        f"Precio incorrecto para courier_externo nacional: {precio} (esperado 1800)."
    )


@pytest.mark.asyncio
async def test_planilla_bloqueada_precio_conservado_tras_carga(client, auth_headers, maestros):
    """
    Escenario completo del incidente:
      1. Serial existe en planilla PROT con precio=750 y bloqueado.
      2. Se corre carga-masiva con ese serial.
      3. El precio y el bloqueo deben conservarse intactos.
    """
    serial = _SERIALES[0]
    await _insertar_serial(serial, precio_mensajero=750, editado_manualmente=True,
                           courier_id=maestros["courier_id"])

    # carga-masiva con el mismo serial, planilla idéntica
    r = await client.post(
        "/api/ordenes/carga-masiva",
        files={"file": ("test.csv", io.BytesIO(_csv(serial)), "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()

    precio_post = await _precio_en_db(serial)
    editado_post = await _editado_en_db(serial)

    assert precio_post == 750.0, (
        f"Precio sobreescrito tras carga-masiva: {precio_post} "
        f"(bloqueados={data.get('seriales_bloqueados')}, "
        f"actualizados={data.get('seriales_actualizados')})"
    )
    assert editado_post is True, "editado_manualmente fue cambiado a False"
    assert data["seriales_bloqueados"] >= 1, (
        f"El serial bloqueado no fue contado en seriales_bloqueados: {data}"
    )
