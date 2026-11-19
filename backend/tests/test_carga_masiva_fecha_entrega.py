"""
Carga masiva iMile (flujo 2) con el informe Delivered: guarda 'Delivered time'
en seriales_gestion.fecha_entrega (migración 055).

Verifica que:
  1. Un serial nuevo queda con la fecha y hora de entrega (hora de Bogotá).
  2. Un serial ya liquidado, que el upsert no toca, recibe la hora de entrega
     si la tenía vacía, sin cambiar nada más.
  3. Un archivo de escáner sin 'Delivered time' no borra la hora ya guardada.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.ordenes_service import procesar_csv

_PREFIJO = "FE-TEST-"
_NUEVO = f"{_PREFIJO}001"
_LIQUIDADO = f"{_PREFIJO}002"
_BOGOTA = timezone(timedelta(hours=-5))

_COLUMNAS_DELIVERED = "Scan time,Waybill No.,Order No.,DA,Delivered time,Scan Station\n"


def _csv_delivered(filas: list[tuple[str, str]]) -> bytes:
    """filas = [(serial, 'AAAA-MM-DD HH:MM:SS')]; Scan time = Delivered time, como en iMile."""
    cuerpo = "".join(
        f"{hora},{serial},ORD-{serial},Mensajero Prueba,{hora},BOG-Prueba.DS\n"
        for serial, hora in filas
    )
    return (_COLUMNAS_DELIVERED + cuerpo).encode()


async def _limpiar(db) -> None:
    await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE :p"), {"p": f"{_PREFIJO}%"})
    await db.execute(text("DELETE FROM ordenes WHERE numero_orden = 'IM20261118'"))


@pytest.fixture(scope="module")
async def cliente_imile():
    async with AsyncSessionLocal() as db:
        await _limpiar(db)
        cid = (await db.execute(
            text("SELECT id FROM clientes WHERE lower(nombre_empresa) = 'imile sas'")
        )).scalar()
        creado = cid is None
        if creado:
            cid = (await db.execute(text("""
                INSERT INTO clientes (nombre_empresa, nit, ciudad, activo)
                VALUES ('Imile SAS', 'TEST-FE-IMILE', 'Bogotá', TRUE) RETURNING id
            """))).scalar_one()
        # Serial ya liquidado antes de que llegara el informe Delivered
        await db.execute(text("""
            INSERT INTO seriales_gestion
                (serial, orden, planilla, f_esc, cod_men, cliente_id,
                 tipo_gestion, tipo_envio, ambito, estado, origen)
            VALUES (:s, 'IM20261117', 'IM20261117', '2026-11-17', '0000', :cid,
                    'Entrega', 'paquete', 'bogota', 'liquidado', 'manual')
        """), {"s": _LIQUIDADO, "cid": cid})
        await db.commit()

    yield cid

    async with AsyncSessionLocal() as db:
        await _limpiar(db)
        if creado:
            await db.execute(text("DELETE FROM clientes WHERE id = :id"), {"id": cid})
        await db.commit()


async def _serial(serial: str) -> dict:
    async with AsyncSessionLocal() as db:
        fila = (await db.execute(
            text("SELECT estado, f_esc, planilla, fecha_entrega FROM seriales_gestion WHERE serial = :s"),
            {"s": serial},
        )).mappings().one()
    return dict(fila)


@pytest.mark.asyncio
async def test_informe_delivered_guarda_fecha_entrega(cliente_imile):
    archivo = _csv_delivered([
        (_NUEVO, "2026-11-18 09:03:56"),
        (_LIQUIDADO, "2026-11-18 09:14:38"),
    ])
    async with AsyncSessionLocal() as db:
        resultado = await procesar_csv(archivo, db, filename="delivered.csv")
        await db.commit()

    assert resultado.seriales_nuevos == 1, resultado.errores

    nuevo = await _serial(_NUEVO)
    assert nuevo["fecha_entrega"] == datetime(2026, 11, 18, 9, 3, 56, tzinfo=_BOGOTA)

    liquidado = await _serial(_LIQUIDADO)
    assert liquidado["fecha_entrega"] == datetime(2026, 11, 18, 9, 14, 38, tzinfo=_BOGOTA)
    # El resto del serial liquidado no cambia
    assert liquidado["estado"] == "liquidado"
    assert str(liquidado["f_esc"]) == "2026-11-17"
    assert liquidado["planilla"] == "IM20261117"


@pytest.mark.asyncio
async def test_archivo_sin_delivered_time_no_borra_la_hora(cliente_imile):
    # Export de escáner viejo: mismas columnas, pero sin 'Delivered time'
    archivo = f"Scan time,Waybill No.,DA\n2026-11-18 10:00:00,{_NUEVO},Mensajero Prueba\n".encode()
    async with AsyncSessionLocal() as db:
        await procesar_csv(archivo, db, filename="escaner.csv")
        await db.commit()

    nuevo = await _serial(_NUEVO)
    assert nuevo["fecha_entrega"] == datetime(2026, 11, 18, 9, 3, 56, tzinfo=_BOGOTA)
