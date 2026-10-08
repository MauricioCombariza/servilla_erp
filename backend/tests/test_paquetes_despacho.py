"""Tests de integración de guardar_paquetes (Paso 1.2): necesitan la BD con las
migraciones 031 (sectorizacion_limites) y 032 (paquetes_despacho) aplicadas."""
from datetime import date

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.models.paquetes_despacho import ESTADO_DANADO, ESTADO_SIN_GESTION, PaqueteDespacho
from app.services.paquetes_despacho_service import PaqueteEntrada, guardar_paquetes

PREFIJO = "TEST12-"
HOY = date(2026, 10, 8)


@pytest.fixture
async def db():
    async with AsyncSessionLocal() as session:
        await _limpiar(session)
        yield session
        await session.rollback()
        await _limpiar(session)


async def _limpiar(session):
    await session.execute(delete(PaqueteDespacho).where(PaqueteDespacho.serial.like(f"{PREFIJO}%")))
    await session.commit()


async def _paquete(session, serial) -> PaqueteDespacho:
    session.expire_all()
    result = await session.execute(select(PaqueteDespacho).where(PaqueteDespacho.serial == serial))
    return result.scalar_one()


async def _contar(session) -> int:
    result = await session.execute(
        select(func.count()).select_from(PaqueteDespacho).where(PaqueteDespacho.serial.like(f"{PREFIJO}%"))
    )
    return result.scalar_one()


async def test_guarda_paquetes_sectorizados_en_sin_gestion(db):
    r = await guardar_paquetes(db, [
        PaqueteEntrada(f"{PREFIJO}1", "Ana", "3001112233", "calle 95 # 49-22 clinica del pie y spa"),
        PaqueteEntrada(f"{PREFIJO}2", "Luis", "3004445566", "CR 20 # 66-15"),
        PaqueteEntrada(f"{PREFIJO}3", "Eva", None, "direccion rara"),
    ], HOY)

    assert (r.creados, r.reemplazados, r.total) == (3, 0, 3)
    assert r.seriales_sin_sector == [f"{PREFIJO}3"]

    p1 = await _paquete(db, f"{PREFIJO}1")
    assert (p1.nombre, p1.telefono, p1.f_emi, p1.estado) == ("Ana", "3001112233", HOY, ESTADO_SIN_GESTION)
    assert (p1.direccion_estandarizada, p1.codigo_postal) == ("CL 95 49 22", "111211")
    assert (p1.localidad, p1.zona) == ("Barrios Unidos", "90_2")

    p2 = await _paquete(db, f"{PREFIJO}2")
    assert (p2.localidad, p2.zona) == ("Chapinero", "60_4")

    p3 = await _paquete(db, f"{PREFIJO}3")
    assert (p3.localidad, p3.zona, p3.estado) == (None, None, ESTADO_SIN_GESTION)


async def test_serial_repetido_se_reemplaza_y_vuelve_a_sin_gestion(db):
    await guardar_paquetes(db, [
        PaqueteEntrada(f"{PREFIJO}1", "Ana", "300", "calle 95 # 49-22"),
        PaqueteEntrada(f"{PREFIJO}2", "Luis", "301", "CR 20 # 66-15"),
        PaqueteEntrada(f"{PREFIJO}3", "Eva", "302", "CL 82 38 10"),
    ], HOY)
    await db.execute(
        update(PaqueteDespacho).where(PaqueteDespacho.serial == f"{PREFIJO}2").values(estado=ESTADO_DANADO)
    )
    await db.commit()

    nuevo_dia = date(2026, 10, 9)
    r = await guardar_paquetes(db, [PaqueteEntrada(f"{PREFIJO}2", "Luis P", "309", "CR 17 # 63-49")], nuevo_dia)

    assert (r.creados, r.reemplazados) == (0, 1)
    assert await _contar(db) == 3
    p2 = await _paquete(db, f"{PREFIJO}2")
    assert (p2.nombre, p2.telefono, p2.direccion, p2.f_emi) == ("Luis P", "309", "CR 17 # 63-49", nuevo_dia)
    assert (p2.zona, p2.estado) == ("60_2", ESTADO_SIN_GESTION)


async def test_serial_repetido_en_el_mismo_archivo_se_queda_el_ultimo(db):
    r = await guardar_paquetes(db, [
        PaqueteEntrada(f"{PREFIJO}1", "Primero", None, "calle 95 # 49-22"),
        PaqueteEntrada(f" {PREFIJO}1 ", "Ultimo", None, "CL 82 38 10"),
    ], HOY)

    assert (r.creados, r.reemplazados) == (1, 0)
    p1 = await _paquete(db, f"{PREFIJO}1")
    assert (p1.nombre, p1.zona) == ("Ultimo", "80_3")


async def test_ignora_filas_sin_serial(db):
    r = await guardar_paquetes(db, [PaqueteEntrada(""), PaqueteEntrada("   ")], HOY)
    assert r.total == 0


async def test_despacho_grande_se_guarda_completo(db):
    paquetes = [PaqueteEntrada(f"{PREFIJO}G{i}", None, None, "CL 82 38 10") for i in range(2500)]
    r = await guardar_paquetes(db, paquetes, HOY)
    assert r.creados == 2500
    assert await _contar(db) == 2500


async def test_estado_solo_acepta_sin_gestion_o_danado(db):
    await guardar_paquetes(db, [PaqueteEntrada(f"{PREFIJO}1", None, None, "CL 82 38 10")], HOY)
    with pytest.raises(IntegrityError):
        await db.execute(
            update(PaqueteDespacho).where(PaqueteDespacho.serial == f"{PREFIJO}1").values(estado="entregado")
        )
        await db.commit()
