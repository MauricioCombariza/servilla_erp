"""Paso 3.3: pasar a iMile los paquetes que le tocan al mensajero en el día.

Con el botón "Asignar en iMile" se mandan, uno por uno, los seriales de la lista del
mensajero (sus zonas + reasignados) que todavía no quedaron asignados a él en iMile.
El envío corre en segundo plano y cada resultado se guarda en `asignaciones_imile`
apenas llega, así la pantalla muestra el avance y nada se pierde si se corta.

En iMile el mensajero se busca por `personal.nombre_imile` o, si está vacío, por su
nombre en el ERP. Si no aparece (o aparece repetido) se detiene el envío y se avisa.
"""
import asyncio
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.asignaciones_zona import AsignacionImile
from app.models.personal import Personal
from app.services.asignacion_zonas_service import (
    Mensajero,
    SerialDelMensajero,
    buscar_mensajero,
    seriales_del_mensajero,
)
from app.services.imile_asignacion import MensajeroImileNoEncontradoError, imile_asignacion

# Estados de iMile con los que el paquete ya quedó con el mensajero: no se vuelven a mandar
YA_ASIGNADOS = {"ok", "repetido"}
# Lo que no se vuelve a mandar: lo ya asignado y las guías que iMile tiene cerradas
SIN_REENVIO = YA_ASIGNADOS | {"cerrada"}


class EnvioEnCursoError(Exception):
    pass


class ImileAsignacionApagadaError(Exception):
    pass


@dataclass
class EnvioImile:
    nombre_imile: str
    total: int
    hechos: int = 0
    asignados: int = 0
    fallidos: int = 0
    en_curso: bool = True
    error: str | None = None  # lo que detuvo el envío (p. ej. el mensajero no está en iMile)
    _tarea: asyncio.Task | None = field(default=None, repr=False)


_envios: dict[tuple[int, date], EnvioImile] = {}


def nombre_en_imile(m: Mensajero) -> str:
    return (m.nombre_imile or "").strip() or m.nombre


async def fijar_nombre_imile(db: AsyncSession, codigo: str, nombre_imile: str | None) -> Mensajero:
    m = await buscar_mensajero(db, codigo)
    valor = " ".join((nombre_imile or "").split()) or None
    await db.execute(update(Personal).where(Personal.id == m.id).values(nombre_imile=valor))
    await db.commit()
    return replace(m, nombre_imile=valor)


@dataclass(frozen=True)
class SerialConImile:
    serial: str
    ultimos_4: str
    zona: str | None
    origen: str
    imile_estado: str | None  # None: todavía no se ha mandado a iMile para este mensajero
    imile_mensaje: str | None


async def seriales_con_imile(db: AsyncSession, codigo: str, fecha: date) -> list[SerialConImile]:
    """La lista del mensajero (3.2) con lo que pasó en iMile con cada paquete."""
    m = await buscar_mensajero(db, codigo)
    seriales = await seriales_del_mensajero(db, codigo, fecha)
    registros = await _registros(db, fecha, [s.serial for s in seriales])
    nombres = await _nombres(db, {r.personal_id for r in registros.values()} - {m.id})
    return [_con_imile(s, registros.get(s.serial), m.id, nombres) for s in seriales]


def _con_imile(s: SerialDelMensajero, r: AsignacionImile | None, personal_id: int,
               nombres: dict[int, str]) -> SerialConImile:
    if r is None:
        estado = mensaje = None
    elif r.personal_id != personal_id:
        # Se mandó a otro mensajero y luego se le pasó a este: hay que volver a mandarlo
        estado, mensaje = None, f"En iMile quedó con {nombres.get(r.personal_id, 'otro mensajero')}"
    else:
        estado, mensaje = r.estado, r.mensaje
    return SerialConImile(s.serial, s.ultimos_4, s.zona, s.origen, estado, mensaje)


async def _registros(db: AsyncSession, fecha: date, seriales: list[str]) -> dict[str, AsignacionImile]:
    if not seriales:
        return {}
    result = await db.execute(
        select(AsignacionImile).where(AsignacionImile.fecha == fecha, AsignacionImile.serial.in_(seriales))
    )
    return {r.serial: r for r in result.scalars().all()}


async def _nombres(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    result = await db.execute(select(Personal.id, Personal.nombre_completo).where(Personal.id.in_(ids)))
    return dict(result.all())


async def pendientes(db: AsyncSession, codigo: str, fecha: date) -> list[str]:
    return [s.serial for s in await seriales_con_imile(db, codigo, fecha) if s.imile_estado not in SIN_REENVIO]


def envio_de(m: Mensajero, fecha: date) -> EnvioImile | None:
    return _envios.get((m.id, fecha))


async def iniciar_envio(db: AsyncSession, codigo: str, fecha: date, usuario: str) -> EnvioImile:
    """Arranca en segundo plano el envío a iMile de los pendientes del mensajero."""
    if not settings.imile_asignacion_activa:
        raise ImileAsignacionApagadaError("La asignación en iMile está apagada (IMILE_ASIGNACION_ACTIVA)")
    m = await buscar_mensajero(db, codigo)
    actual = envio_de(m, fecha)
    if actual and actual.en_curso:
        raise EnvioEnCursoError(f"Ya se están mandando a iMile los paquetes de {m.nombre}")

    seriales = await pendientes(db, codigo, fecha)
    envio = EnvioImile(nombre_imile=nombre_en_imile(m), total=len(seriales), en_curso=bool(seriales))
    _envios[(m.id, fecha)] = envio
    if seriales:
        envio._tarea = asyncio.create_task(_correr(envio, m.id, seriales, fecha, usuario))
    return envio


async def _correr(envio: EnvioImile, personal_id: int, seriales: list[str], fecha: date, usuario: str) -> None:
    try:
        async with AsyncSessionLocal() as db:
            for serial in seriales:
                try:
                    r = await imile_asignacion.asignar(envio.nombre_imile, serial)
                    estado, mensaje, codigo = r.estado.value, r.mensaje, r.codigo
                except MensajeroImileNoEncontradoError as exc:
                    envio.error = str(exc)
                    return
                # Cualquier otra falla de iMile (sesión caída, la página cambió…) queda en
                # ese serial como error y se sigue con el resto
                except Exception as exc:  # noqa: BLE001
                    estado, mensaje, codigo = "error", f"{type(exc).__name__}: {exc}"[:500], None
                await _guardar(db, fecha, serial, personal_id, estado, mensaje, codigo, usuario)
                envio.hechos += 1
                if estado in YA_ASIGNADOS:
                    envio.asignados += 1
                else:
                    envio.fallidos += 1
    except Exception as exc:  # noqa: BLE001
        envio.error = f"{type(exc).__name__}: {exc}"[:500]
    finally:
        envio.en_curso = False


async def _guardar(db: AsyncSession, fecha: date, serial: str, personal_id: int, estado: str,
                   mensaje: str | None, codigo: str | None, usuario: str) -> None:
    valores = dict(personal_id=personal_id, estado=estado, mensaje=mensaje, codigo=codigo,
                   usuario=usuario, fecha_envio=func.now())
    await db.execute(
        insert(AsignacionImile)
        .values(fecha=fecha, serial=serial, **valores)
        .on_conflict_do_update(constraint="uq_asignaciones_imile_fecha_serial", set_=valores)
    )
    await db.commit()
