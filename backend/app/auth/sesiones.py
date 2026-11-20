"""Sesiones en el servidor, bloqueo por intentos fallidos y eventos de seguridad (PR-12).

- Cada inicio de sesión crea una fila en `sesiones`; los tokens llevan su id (`sid`).
- La sesión muere a los SESION_INACTIVIDAD_MINUTOS sin peticiones, a las SESION_MAX_HORAS
  de creada, o cuando se cierra (salida, administrador, cambio o reinicio de clave).
- La inactividad que cuenta es la de la persona: el navegador la mide (teclado, toque,
  lecturas de pistola) y llama a /api/auth/logout al cumplirse. Lo de aquí es el respaldo
  para el navegador cerrado o un token robado.
"""
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.usuarios import EventoSeguridad, Sesion, Usuario

# ultima_actividad se escribe como mucho una vez por minuto por sesión
_TOQUE = timedelta(seconds=60)


def ahora() -> datetime:
    return datetime.now(UTC)


def ip_de(request: Request | None) -> str | None:
    """IP del cliente. nginx pone X-Real-IP (con real_ip desde Caddy)."""
    if request is None:
        return None
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    return ip[:45] if ip else None


async def registrar_evento(
    db: AsyncSession, tipo: str, *, usuario: Usuario | None = None,
    username: str | None = None, ip: str | None = None, detalle: str | None = None,
) -> None:
    """Agrega el evento a la transacción en curso (lo guarda el commit de quien llama)."""
    db.add(EventoSeguridad(
        tipo=tipo,
        usuario_id=usuario.id if usuario else None,
        username=(usuario.username if usuario else username or "")[:50] or None,
        ip=ip,
        detalle=detalle[:300] if detalle else None,
    ))


# ── Bloqueo ──────────────────────────────────────────────────────────────────

def bloqueada(usuario: Usuario, momento: datetime | None = None) -> bool:
    return usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > (momento or ahora())


async def intento_fallido(db: AsyncSession, usuario: Usuario, ip: str | None) -> bool:
    """Suma un fallo; al llegar al tope bloquea la cuenta. Devuelve True si quedó bloqueada."""
    usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
    await registrar_evento(db, "login_fallido", usuario=usuario, ip=ip,
                           detalle=f"intento {usuario.intentos_fallidos}")
    if usuario.intentos_fallidos < settings.login_max_intentos:
        return False
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = ahora() + timedelta(minutes=settings.login_bloqueo_minutos)
    await registrar_evento(db, "bloqueo", usuario=usuario, ip=ip,
                           detalle=f"{settings.login_max_intentos} intentos fallidos")
    return True


def desbloquear(usuario: Usuario) -> None:
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


# ── Sesiones ─────────────────────────────────────────────────────────────────

async def crear(db: AsyncSession, usuario: Usuario, request: Request | None) -> Sesion:
    momento = ahora()
    agente = request.headers.get("user-agent") if request else None
    sesion = Sesion(
        id=secrets.token_urlsafe(32),
        usuario_id=usuario.id,
        creada_en=momento,
        ultima_actividad=momento,
        expira_en=momento + timedelta(hours=settings.sesion_max_horas),
        ip=ip_de(request),
        user_agent=agente[:200] if agente else None,
    )
    db.add(sesion)
    return sesion


def motivo_vencida(sesion: Sesion, momento: datetime | None = None) -> str | None:
    """None si la sesión sigue viva; si no, por qué ya no sirve."""
    momento = momento or ahora()
    if sesion.cerrada_en is not None:
        return sesion.motivo_cierre or "cerrada"
    if sesion.expira_en <= momento:
        return "duracion_maxima"
    if sesion.ultima_actividad <= momento - timedelta(minutes=settings.sesion_inactividad_minutos):
        return "inactividad"
    return None


async def tocar(db: AsyncSession, sesion: Sesion, *, forzar: bool = False) -> None:
    """Marca actividad (como mucho una escritura por minuto, salvo forzar)."""
    momento = ahora()
    if forzar or sesion.ultima_actividad <= momento - _TOQUE:
        await db.execute(update(Sesion).where(Sesion.id == sesion.id)
                         .values(ultima_actividad=momento))
        sesion.ultima_actividad = momento
        await db.commit()


async def cerrar(db: AsyncSession, sesion: Sesion, motivo: str) -> None:
    if sesion.cerrada_en is None:
        sesion.cerrada_en = ahora()
        sesion.motivo_cierre = motivo[:30]


async def cerrar_todas(
    db: AsyncSession, usuario_id: int, motivo: str, *, excepto: str | None = None,
) -> int:
    """Cierra las sesiones abiertas del usuario (menos `excepto`). Devuelve cuántas."""
    condicion = [Sesion.usuario_id == usuario_id, Sesion.cerrada_en.is_(None)]
    if excepto:
        condicion.append(Sesion.id != excepto)
    resultado = await db.execute(
        update(Sesion).where(*condicion)
        .values(cerrada_en=ahora(), motivo_cierre=motivo[:30])
        .execution_options(synchronize_session=False)
    )
    return resultado.rowcount or 0


async def sesion_y_usuario(db: AsyncSession, sid: str, username: str) -> tuple[Sesion, Usuario] | None:
    fila = (await db.execute(
        select(Sesion, Usuario).join(Usuario, Usuario.id == Sesion.usuario_id)
        .where(Sesion.id == sid, Usuario.username == username)
    )).first()
    return (fila[0], fila[1]) if fila else None
