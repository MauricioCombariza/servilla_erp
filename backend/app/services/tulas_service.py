"""Descarga de tulas (Pasos 2.4 y 2.8): abrir una tula, leer sus paquetes y cerrarla.

- Contador: con total esperado N empieza en N y baja con cada paquete leído (puede
  quedar negativo); "Sin etiqueta" o sin total empieza en 0 y sube.
- Un serial ya leído en la misma tula no se vuelve a contar.
- Cada lectura se guarda en el momento: si el celular se apaga no se pierde nada.
- Una sola tula abierta por usuario. Si hay una abierta y se abre otra, se pide
  confirmación (cerrar_anterior=True) antes de cerrarla.
"""
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tulas import ESTADO_ABIERTA, ESTADO_CERRADA, Tula, TulaSerial
from app.services.imile_ingreso import imile_ingreso
from app.services.paquetes_despacho_service import Destino, buscar_destino

AVISO_YA_ESCANEADO = "Ya escaneado en esta tula"
# El servidor corre en UTC: después de las 7 p. m. en Bogotá date.today() ya sería mañana
_ZONA_HORARIA = ZoneInfo("America/Bogota")


class TulaAbiertaError(Exception):
    """Hay otra tula abierta y no se confirmó cerrarla."""

    def __init__(self, tula: Tula):
        self.tula = tula
        super().__init__("Hay una tula abierta. ¿Cerrarla y abrir la nueva?")


class TulaNoEncontradaError(Exception):
    pass


class TulaCerradaError(Exception):
    pass


@dataclass(frozen=True)
class ResumenTula:
    tula: Tula
    leidos: int

    @property
    def contador(self) -> int:
        if self.tula.total_esperado is None:
            return self.leidos
        return self.tula.total_esperado - self.leidos

    @property
    def diferencia(self) -> int | None:
        """Positiva: faltan paquetes. Negativa: llegaron más de los esperados."""
        if self.tula.total_esperado is None:
            return None
        return self.tula.total_esperado - self.leidos


@dataclass(frozen=True)
class ResultadoEscaneo:
    resumen: ResumenTula
    destino: Destino
    ya_escaneado: bool
    imile_estado: str | None
    imile_mensaje: str | None


async def _leidos(db: AsyncSession, tula_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(TulaSerial).where(TulaSerial.tula_id == tula_id)
    )
    return result.scalar_one()


async def resumen(db: AsyncSession, tula: Tula) -> ResumenTula:
    return ResumenTula(tula=tula, leidos=await _leidos(db, tula.id))


async def tula_abierta(db: AsyncSession, usuario: str) -> Tula | None:
    result = await db.execute(
        select(Tula).where(Tula.usuario == usuario, Tula.estado == ESTADO_ABIERTA)
    )
    return result.scalar_one_or_none()


async def obtener_tula(db: AsyncSession, tula_id: int) -> Tula:
    tula = await db.get(Tula, tula_id)
    if tula is None:
        raise TulaNoEncontradaError(f"Tula {tula_id} no encontrada")
    return tula


async def abrir_tula(
    db: AsyncSession,
    usuario: str,
    codigo: str | None,
    total_esperado: int | None = None,
    cerrar_anterior: bool = False,
    hoy: date | None = None,
) -> Tula:
    codigo = (codigo or "").strip() or None
    anterior = await tula_abierta(db, usuario)
    if anterior is not None:
        if codigo is not None and anterior.codigo == codigo:
            return anterior  # se volvió a escanear la misma tula: sigue abierta
        if not cerrar_anterior:
            raise TulaAbiertaError(anterior)
        await _cerrar(db, anterior)

    tula = Tula(
        codigo=codigo,
        sin_etiqueta=codigo is None,
        total_esperado=total_esperado,
        estado=ESTADO_ABIERTA,
        usuario=usuario,
        fecha=hoy or datetime.now(_ZONA_HORARIA).date(),
    )
    db.add(tula)
    await db.commit()
    await db.refresh(tula)
    return tula


async def registrar_serial(db: AsyncSession, tula_id: int, serial: str) -> ResultadoEscaneo:
    tula = await obtener_tula(db, tula_id)
    if tula.estado != ESTADO_ABIERTA:
        raise TulaCerradaError("La tula ya está cerrada")

    destino = await buscar_destino(db, serial)
    stmt = (
        insert(TulaSerial)
        .values(tula_id=tula.id, serial=destino.serial, en_tabla=destino.en_tabla, zona=destino.zona)
        .on_conflict_do_nothing(constraint="uq_tula_seriales_tula_serial")
        .returning(TulaSerial.id)
    )
    nuevo_id = (await db.execute(stmt)).scalar_one_or_none()
    # Se guarda la lectura ANTES de ir a iMile: si iMile falla o tarda, el paquete ya cuenta
    await db.commit()

    if nuevo_id is not None:
        # Paso 2.5: el ingreso en iMile se hace siempre, aunque el serial no esté en la tabla
        await _ingresar_en_imile(db, nuevo_id, destino.serial)

    registro = (
        await db.execute(
            select(TulaSerial).where(TulaSerial.tula_id == tula.id, TulaSerial.serial == destino.serial)
        )
    ).scalar_one()
    return ResultadoEscaneo(
        resumen=await resumen(db, tula),
        destino=destino,
        ya_escaneado=nuevo_id is None,
        imile_estado=registro.imile_estado,
        imile_mensaje=registro.imile_mensaje,
    )


async def _ingresar_en_imile(db: AsyncSession, tula_serial_id: int, serial: str) -> None:
    if not settings.imile_ingreso_activo:
        estado, mensaje = "omitido", "Ingreso en iMile apagado (IMILE_INGRESO_ACTIVO)"
    else:
        try:
            r = await imile_ingreso.ingresar(serial)
            estado, mensaje = r.estado.value, r.mensaje
        # Cualquier falla de iMile (sesión caída, no responde, la página cambió…) se guarda
        # como error: nunca debe hacer perder la lectura del paquete en la tula
        except Exception as exc:  # noqa: BLE001
            estado, mensaje = "error", f"{type(exc).__name__}: {exc}"[:500]
    await db.execute(
        update(TulaSerial)
        .where(TulaSerial.id == tula_serial_id)
        .values(imile_estado=estado, imile_mensaje=mensaje, imile_fecha=func.now())
    )
    await db.commit()


async def reintentar_imile(db: AsyncSession, tula_id: int, serial: str) -> TulaSerial:
    """Vuelve a ingresar en iMile un paquete ya leído (p. ej. si la primera vez falló)."""
    result = await db.execute(
        select(TulaSerial).where(TulaSerial.tula_id == tula_id, TulaSerial.serial == serial.strip())
    )
    registro = result.scalar_one_or_none()
    if registro is None:
        raise TulaNoEncontradaError(f"El serial {serial} no está leído en la tula {tula_id}")
    await _ingresar_en_imile(db, registro.id, registro.serial)
    await db.refresh(registro)
    return registro


async def _cerrar(db: AsyncSession, tula: Tula) -> None:
    tula.estado = ESTADO_CERRADA
    tula.fecha_cierre = func.now()
    await db.commit()
    await db.refresh(tula)


async def cerrar_tula(db: AsyncSession, tula_id: int) -> ResumenTula:
    tula = await obtener_tula(db, tula_id)
    if tula.estado != ESTADO_CERRADA:
        await _cerrar(db, tula)
    return await resumen(db, tula)


async def seriales_de(db: AsyncSession, tula_id: int) -> list[TulaSerial]:
    result = await db.execute(
        select(TulaSerial).where(TulaSerial.tula_id == tula_id).order_by(TulaSerial.fecha_escaneo)
    )
    return list(result.scalars().all())


async def listar_tulas(db: AsyncSession, fecha: date) -> list[ResumenTula]:
    result = await db.execute(select(Tula).where(Tula.fecha == fecha).order_by(Tula.fecha_apertura))
    return [await resumen(db, t) for t in result.scalars().all()]
