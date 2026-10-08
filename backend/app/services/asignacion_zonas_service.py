"""Asignación de zonas a mensajeros (Pasos 3.1 y 3.2).

- 3.1: código del mensajero → nombre, desde la tabla `personal` (solo activos).
- 3.2: cada zona va completa a UN solo mensajero por día. Si una zona ya la tiene
  otro, se informa el choque y solo con reasignar=True se le pasa al nuevo.
- 3.2: también se reasigna serial por serial (código del mensajero + escanear
  seriales). El mensajero final de un paquete es el de su serial si lo tiene; si
  no, el de su zona.
"""
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignaciones_zona import AsignacionSerial, AsignacionZona
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.personal import Personal
from app.models.tulas import Tula, TulaSerial
from app.services.vista_zonas_service import zonas_disponibles

ZONA_HORARIA = ZoneInfo("America/Bogota")


class MensajeroNoEncontradoError(Exception):
    pass


class ZonasInvalidasError(Exception):
    def __init__(self, zonas: list[str]):
        self.zonas = zonas
        super().__init__(f"Zonas que no existen: {', '.join(zonas)}")


@dataclass(frozen=True)
class Choque:
    zona: str
    codigo: str
    nombre: str


class ZonasOcupadasError(Exception):
    def __init__(self, choques: list[Choque]):
        self.choques = choques
        super().__init__("Algunas zonas ya están asignadas a otro mensajero")


@dataclass(frozen=True)
class Mensajero:
    id: int
    codigo: str
    nombre: str


@dataclass(frozen=True)
class ZonaDelDia:
    zona: str
    paquetes_leidos: int
    mensajero: Mensajero | None


def hoy() -> date:
    return datetime.now(ZONA_HORARIA).date()


def _mensajero(p: Personal) -> Mensajero:
    return Mensajero(id=p.id, codigo=p.codigo.strip(), nombre=p.nombre_completo)


async def buscar_mensajero(db: AsyncSession, codigo: str) -> Mensajero:
    result = await db.execute(
        select(Personal).where(Personal.codigo == codigo.strip(), Personal.activo.is_(True))
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        raise MensajeroNoEncontradoError("Mensajero no encontrado")
    return _mensajero(persona)


async def asignar_zonas(
    db: AsyncSession,
    codigo: str,
    zonas: list[str],
    fecha: date,
    usuario: str,
    reasignar: bool = False,
) -> list[str]:
    """Deja al mensajero con exactamente `zonas` en `fecha`. Devuelve sus zonas."""
    mensajero = await buscar_mensajero(db, codigo)
    pedidas = list(dict.fromkeys(z.strip() for z in zonas if z.strip()))

    validas = set(await zonas_disponibles(db))
    invalidas = [z for z in pedidas if z not in validas]
    if invalidas:
        raise ZonasInvalidasError(invalidas)

    result = await db.execute(
        select(AsignacionZona, Personal)
        .join(Personal, Personal.id == AsignacionZona.personal_id)
        .where(AsignacionZona.fecha == fecha, AsignacionZona.zona.in_(pedidas),
               AsignacionZona.personal_id != mensajero.id)
    )
    choques = [Choque(a.zona, p.codigo.strip(), p.nombre_completo) for a, p in result.all()]
    if choques and not reasignar:
        raise ZonasOcupadasError(choques)

    # Se quitan las zonas que el mensajero ya no tiene y las que se le pasan desde otros
    await db.execute(
        delete(AsignacionZona).where(
            AsignacionZona.fecha == fecha,
            (AsignacionZona.personal_id == mensajero.id) | AsignacionZona.zona.in_(pedidas),
        )
    )
    for zona in pedidas:
        db.add(AsignacionZona(fecha=fecha, zona=zona, personal_id=mensajero.id, usuario=usuario))
    await db.commit()
    return pedidas


async def zonas_de(db: AsyncSession, codigo: str, fecha: date) -> list[str]:
    mensajero = await buscar_mensajero(db, codigo)
    result = await db.execute(
        select(AsignacionZona.zona)
        .where(AsignacionZona.fecha == fecha, AsignacionZona.personal_id == mensajero.id)
        .order_by(AsignacionZona.zona)
    )
    return list(result.scalars().all())


async def tablero(db: AsyncSession, fecha: date) -> list[ZonaDelDia]:
    """Las zonas del día, con su mensajero y cuántos paquetes se leyeron en tulas de ese día."""
    leidos = dict((await db.execute(
        select(TulaSerial.zona, func.count())
        .join(Tula, Tula.id == TulaSerial.tula_id)
        .where(Tula.fecha == fecha, TulaSerial.zona.is_not(None))
        .group_by(TulaSerial.zona)
    )).all())
    asignadas = {
        a.zona: _mensajero(p)
        for a, p in (await db.execute(
            select(AsignacionZona, Personal)
            .join(Personal, Personal.id == AsignacionZona.personal_id)
            .where(AsignacionZona.fecha == fecha)
        )).all()
    }
    return [
        ZonaDelDia(zona=z, paquetes_leidos=leidos.get(z, 0), mensajero=asignadas.get(z))
        for z in await zonas_disponibles(db)
    ]


# ========== REASIGNACIÓN SERIAL POR SERIAL ==========

ORIGEN_ZONA = "zona"
ORIGEN_SERIAL = "serial"


@dataclass(frozen=True)
class ResultadoAsignacionSerial:
    serial: str
    ultimos_4: str
    zona: str | None
    mensajero_anterior: Mensajero | None
    ya_era_suyo: bool


@dataclass(frozen=True)
class SerialDelMensajero:
    serial: str
    ultimos_4: str
    zona: str | None
    origen: str  # "zona" | "serial"


async def _zona_del_serial(db: AsyncSession, serial: str, fecha: date) -> str | None:
    leido = (await db.execute(
        select(TulaSerial.zona)
        .join(Tula, Tula.id == TulaSerial.tula_id)
        .where(TulaSerial.serial == serial, Tula.fecha == fecha)
        .order_by(TulaSerial.id.desc())
        .limit(1)
    )).first()
    if leido is not None:
        return leido[0]
    paquete = (await db.execute(
        select(PaqueteDespacho.zona).where(PaqueteDespacho.serial == serial)
    )).first()
    return paquete[0] if paquete else None


async def _mensajero_actual(db: AsyncSession, serial: str, zona: str | None, fecha: date) -> Mensajero | None:
    por_serial = (await db.execute(
        select(Personal)
        .join(AsignacionSerial, AsignacionSerial.personal_id == Personal.id)
        .where(AsignacionSerial.fecha == fecha, AsignacionSerial.serial == serial)
    )).scalar_one_or_none()
    if por_serial is not None:
        return _mensajero(por_serial)
    if zona is None:
        return None
    por_zona = (await db.execute(
        select(Personal)
        .join(AsignacionZona, AsignacionZona.personal_id == Personal.id)
        .where(AsignacionZona.fecha == fecha, AsignacionZona.zona == zona)
    )).scalar_one_or_none()
    return _mensajero(por_zona) if por_zona else None


async def asignar_serial(
    db: AsyncSession, codigo: str, serial: str, fecha: date, usuario: str
) -> ResultadoAsignacionSerial:
    """Reasigna un paquete al mensajero, por encima de su zona. Dice a quién lo tenía."""
    mensajero = await buscar_mensajero(db, codigo)
    serial = serial.strip()
    zona = await _zona_del_serial(db, serial, fecha)
    anterior = await _mensajero_actual(db, serial, zona, fecha)

    await db.execute(
        delete(AsignacionSerial).where(AsignacionSerial.fecha == fecha, AsignacionSerial.serial == serial)
    )
    db.add(AsignacionSerial(fecha=fecha, serial=serial, personal_id=mensajero.id, usuario=usuario))
    await db.commit()
    return ResultadoAsignacionSerial(
        serial=serial,
        ultimos_4=serial[-4:],
        zona=zona,
        mensajero_anterior=anterior,
        ya_era_suyo=anterior is not None and anterior.id == mensajero.id,
    )


async def quitar_serial(db: AsyncSession, codigo: str, serial: str, fecha: date) -> bool:
    """Deshace la reasignación: el paquete vuelve al mensajero de su zona."""
    mensajero = await buscar_mensajero(db, codigo)
    result = await db.execute(
        delete(AsignacionSerial).where(
            AsignacionSerial.fecha == fecha,
            AsignacionSerial.serial == serial.strip(),
            AsignacionSerial.personal_id == mensajero.id,
        )
    )
    await db.commit()
    return result.rowcount > 0


async def seriales_del_mensajero(db: AsyncSession, codigo: str, fecha: date) -> list[SerialDelMensajero]:
    """Lo que le toca al mensajero en el día: los paquetes leídos de sus zonas que no se
    reasignaron a otro, más los que se le reasignaron uno a uno. Es la lista del 3.3."""
    mensajero = await buscar_mensajero(db, codigo)
    reasignados = {
        serial: personal_id
        for serial, personal_id in (await db.execute(
            select(AsignacionSerial.serial, AsignacionSerial.personal_id).where(AsignacionSerial.fecha == fecha)
        )).all()
    }
    sus_zonas = set(await zonas_de(db, codigo, fecha))
    leidos = (await db.execute(
        select(TulaSerial.serial, TulaSerial.zona)
        .join(Tula, Tula.id == TulaSerial.tula_id)
        .where(Tula.fecha == fecha)
        .order_by(TulaSerial.id)
    )).all()

    resultado: dict[str, SerialDelMensajero] = {}
    for serial, zona in leidos:
        if zona in sus_zonas and serial not in reasignados:
            resultado.setdefault(serial, SerialDelMensajero(serial, serial[-4:], zona, ORIGEN_ZONA))
    for serial, personal_id in reasignados.items():
        if personal_id == mensajero.id:
            resultado[serial] = SerialDelMensajero(
                serial, serial[-4:], await _zona_del_serial(db, serial, fecha), ORIGEN_SERIAL
            )
    return list(resultado.values())
