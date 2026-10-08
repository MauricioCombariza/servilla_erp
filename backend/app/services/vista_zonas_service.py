"""Vista por zonas (Paso 2.7): una persona escanea y las demás, sin iniciar sesión, ven
en su celular los paquetes de las zonas que eligieron.

Como la vista muestra direcciones de clientes, se abre con un enlace secreto del día
(uno por usuario que escanea y por día) que vence a la medianoche de Bogotá. Cada
celular pide solo lo nuevo desde el último paquete que recibió (`desde`).
"""
import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enlaces_vista import EnlaceVista
from app.models.paquetes_despacho import PaqueteDespacho
from app.models.sectorizacion import SectorizacionLimite
from app.models.tulas import Tula, TulaSerial
from app.services.paquetes_despacho_service import AVISO_FUERA_DE_ZONA
from app.services.sectorizacion_service import TIPO_ZONA

ZONA_HORARIA = ZoneInfo("America/Bogota")
_LIMITE_POR_CONSULTA = 200


class EnlaceInvalidoError(Exception):
    pass


@dataclass(frozen=True)
class PaqueteVista:
    id: int
    ultimos_4: str
    direccion: str | None
    zona: str | None
    fuera_de_zona: bool
    aviso: str | None
    fecha_escaneo: datetime


@dataclass(frozen=True)
class PaquetesNuevos:
    paquetes: list[PaqueteVista]
    ultimo_id: int  # el celular lo manda como `desde` en la siguiente consulta


def _ahora() -> datetime:
    return datetime.now(ZONA_HORARIA)


async def obtener_o_crear_enlace(db: AsyncSession, usuario: str, ahora: datetime | None = None) -> EnlaceVista:
    ahora = ahora or _ahora()
    hoy = ahora.astimezone(ZONA_HORARIA).date()
    result = await db.execute(
        select(EnlaceVista).where(EnlaceVista.usuario == usuario, EnlaceVista.fecha == hoy)
    )
    enlace = result.scalar_one_or_none()
    if enlace is not None:
        return enlace

    enlace = EnlaceVista(
        token=secrets.token_urlsafe(24),
        usuario=usuario,
        fecha=hoy,
        expira=datetime.combine(hoy + timedelta(days=1), time.min, tzinfo=ZONA_HORARIA),
    )
    db.add(enlace)
    await db.commit()
    await db.refresh(enlace)
    return enlace


async def validar_enlace(db: AsyncSession, token: str, ahora: datetime | None = None) -> EnlaceVista:
    result = await db.execute(select(EnlaceVista).where(EnlaceVista.token == token))
    enlace = result.scalar_one_or_none()
    if enlace is None or enlace.expira <= (ahora or _ahora()):
        raise EnlaceInvalidoError("Enlace inválido o vencido")
    return enlace


async def zonas_disponibles(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(SectorizacionLimite.nombre)
        .where(SectorizacionLimite.tipo == TIPO_ZONA, SectorizacionLimite.activo.is_(True))
        .order_by(SectorizacionLimite.orden)
    )
    return list(result.scalars().all())


async def paquetes_nuevos(
    db: AsyncSession, enlace: EnlaceVista, zonas: set[str], desde: int = 0
) -> PaquetesNuevos:
    """Paquetes leídos después de `desde` en las tulas del día de quien escanea. Se
    incluyen los de las zonas elegidas y, para todos, los que están fuera de zona."""
    result = await db.execute(
        select(TulaSerial, PaqueteDespacho)
        .join(Tula, Tula.id == TulaSerial.tula_id)
        .outerjoin(PaqueteDespacho, PaqueteDespacho.serial == TulaSerial.serial)
        .where(Tula.usuario == enlace.usuario, Tula.fecha == enlace.fecha, TulaSerial.id > desde)
        .order_by(TulaSerial.id)
        .limit(_LIMITE_POR_CONSULTA)
    )
    filas = result.all()

    paquetes = []
    for leido, paquete in filas:
        fuera = leido.zona is None
        if not fuera and leido.zona not in zonas:
            continue  # de otra zona: esta persona no ve nada
        direccion = None
        if paquete is not None:
            direccion = paquete.direccion_estandarizada or paquete.direccion
        paquetes.append(PaqueteVista(
            id=leido.id,
            ultimos_4=leido.serial[-4:],
            direccion=direccion,
            zona=leido.zona,
            fuera_de_zona=fuera,
            aviso=AVISO_FUERA_DE_ZONA if fuera else None,
            fecha_escaneo=leido.fecha_escaneo,
        ))

    ultimo_id = filas[-1][0].id if filas else desde
    return PaquetesNuevos(paquetes=paquetes, ultimo_id=ultimo_id)
