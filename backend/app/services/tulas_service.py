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

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.tulas import ESTADO_ABIERTA, ESTADO_CERRADA, Tula, TulaSerial
from app.services.imile_ingreso import imile_ingreso
from app.services.imile_tula import ConsultaTula, imile_tula
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


@dataclass(frozen=True)
class AperturaTula:
    tula: Tula
    # Paso 2.3: qué dijo iMile del total (None si no se consultó)
    imile_total: str | None = None


async def _consultar_imile(codigo: str) -> tuple[ConsultaTula | None, str]:
    """Paso 2.3: qué paquetes trae la tula según iMile. Cualquier falla devuelve None con
    el motivo: la tula se abre (o se cierra) igual y se puede contar sin total."""
    try:
        consulta = await imile_tula.consultar(codigo)
    except Exception as exc:  # noqa: BLE001
        return None, f"No se pudo consultar iMile ({type(exc).__name__}): escribe el total a mano"
    if not consulta.encontrada:
        return None, "iMile todavía no tiene esta tula descargada: escribe el total a mano"
    return consulta, f"iMile: la tula trae {consulta.total} paquetes"


async def abrir_tula(
    db: AsyncSession,
    usuario: str,
    codigo: str | None,
    total_esperado: int | None = None,
    cerrar_anterior: bool = False,
    hoy: date | None = None,
) -> AperturaTula:
    codigo = (codigo or "").strip() or None
    anterior = await tula_abierta(db, usuario)
    if anterior is not None:
        if codigo is not None and anterior.codigo == codigo:
            return AperturaTula(anterior)  # se volvió a escanear la misma tula: sigue abierta
        if not cerrar_anterior:
            raise TulaAbiertaError(anterior)
        await _cerrar(db, anterior)

    # El total escrito a mano manda; si no hay, se pregunta a iMile
    imile_total = None
    esperados = None
    if codigo is not None and total_esperado is None and settings.imile_consulta_tula_activa:
        consulta, imile_total = await _consultar_imile(codigo)
        if consulta is not None:
            total_esperado, esperados = consulta.total, list(consulta.seriales)

    tula = Tula(
        codigo=codigo,
        sin_etiqueta=codigo is None,
        total_esperado=total_esperado,
        seriales_esperados=esperados,
        estado=ESTADO_ABIERTA,
        usuario=usuario,
        fecha=hoy or datetime.now(_ZONA_HORARIA).date(),
    )
    db.add(tula)
    await db.commit()
    await db.refresh(tula)
    return AperturaTula(tula, imile_total)


async def fijar_total(db: AsyncSession, tula_id: int, total_esperado: int | None) -> ResumenTula:
    """Total escrito a mano después de abrir la tula (p. ej. si iMile no lo tenía)."""
    tula = await obtener_tula(db, tula_id)
    if tula.estado != ESTADO_ABIERTA:
        raise TulaCerradaError("La tula ya está cerrada")
    tula.total_esperado = total_esperado
    await db.commit()
    await db.refresh(tula)
    return await resumen(db, tula)


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
        # Si al abrirla iMile aún no la tenía (se descargó en la app mientras tanto), se
        # vuelve a preguntar para poder decir qué faltó. Si falla, se cierra igual.
        if tula.codigo and tula.seriales_esperados is None and settings.imile_consulta_tula_activa:
            consulta, _ = await _consultar_imile(tula.codigo)
            if consulta is not None:
                tula.seriales_esperados = list(consulta.seriales)
                if tula.total_esperado is None:
                    tula.total_esperado = consulta.total
        await _cerrar(db, tula)
    return await resumen(db, tula)


def comparar_con_esperados(tula: Tula, leidos: list[str]) -> tuple[list[str] | None, list[str] | None]:
    """(faltantes, no esperados) contra lo que iMile dice que trae la tula; (None, None) si no se sabe."""
    if tula.seriales_esperados is None:
        return None, None
    esperados, vistos = set(tula.seriales_esperados), set(leidos)
    return sorted(esperados - vistos), sorted(vistos - esperados)


async def paquetes_cargados_hoy(db: AsyncSession, hoy: date | None = None) -> int:
    """Paquetes de la base de despacho subidos (o reemplazados) hoy, en hora de Bogotá."""
    hoy = hoy or datetime.now(_ZONA_HORARIA).date()
    desde = datetime.combine(hoy, datetime.min.time(), tzinfo=_ZONA_HORARIA)
    return (
        await db.execute(select(func.count()).select_from(PaqueteDespacho).where(PaqueteDespacho.fecha_modificacion >= desde))
    ).scalar_one()


async def resumen_del_dia(db: AsyncSession, fecha: date | None = None) -> tuple[date, int, int]:
    """Tulas leídas en el día (de todos los usuarios) y paquetes leídos sin repetir serial."""
    fecha = fecha or datetime.now(_ZONA_HORARIA).date()
    tulas = (await db.execute(select(func.count()).select_from(Tula).where(Tula.fecha == fecha))).scalar_one()
    paquetes = (
        await db.execute(
            select(func.count(func.distinct(TulaSerial.serial)))
            .join(Tula, Tula.id == TulaSerial.tula_id)
            .where(Tula.fecha == fecha)
        )
    ).scalar_one()
    return fecha, tulas, paquetes


async def localidades_de(db: AsyncSession, seriales: list[str]) -> dict[str, str | None]:
    """Localidad de cada serial según la base de despacho (los que no están, no aparecen)."""
    if not seriales:
        return {}
    result = await db.execute(
        select(PaqueteDespacho.serial, PaqueteDespacho.localidad).where(PaqueteDespacho.serial.in_(seriales))
    )
    return dict(result.all())


async def seriales_de(db: AsyncSession, tula_id: int) -> list[TulaSerial]:
    result = await db.execute(
        select(TulaSerial).where(TulaSerial.tula_id == tula_id).order_by(TulaSerial.fecha_escaneo)
    )
    return list(result.scalars().all())


async def listar_tulas(db: AsyncSession, fecha: date) -> list[ResumenTula]:
    result = await db.execute(select(Tula).where(Tula.fecha == fecha).order_by(Tula.fecha_apertura))
    return [await resumen(db, t) for t in result.scalars().all()]


async def sin_leer(db: AsyncSession, fecha: date | None = None) -> tuple[date, list[PaqueteDespacho]]:
    """Paquetes de la base de despacho del día (f_emi) que no se han leído en ninguna tula."""
    fecha = fecha or datetime.now(_ZONA_HORARIA).date()
    result = await db.execute(
        select(PaqueteDespacho)
        .where(
            PaqueteDespacho.f_emi == fecha,
            ~exists().where(TulaSerial.serial == PaqueteDespacho.serial),
        )
        .order_by(PaqueteDespacho.zona.nulls_last(), PaqueteDespacho.serial)
    )
    return fecha, list(result.scalars().all())
