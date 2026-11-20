from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(100))
    rol: Mapped[str] = mapped_column(
        String(30), ForeignKey("roles.nombre", onupdate="CASCADE"), nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts, default=None)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(_ts, default=None)
    # Vencimiento de la clave (app/auth/claves.py, SER-MNT-PR-02 §20.3)
    clave_cambiada_en: Mapped[datetime] = mapped_column(_ts, server_default=func.now())
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, server_default=false(), default=False)
    # Bloqueo por intentos fallidos (app/auth/sesiones.py, PR-12)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(_ts, default=None)


class UsuarioClaveAnterior(Base):
    """Hashes de las últimas claves de cada usuario, para no dejar que las repita."""
    __tablename__ = "usuarios_claves_anteriores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha: Mapped[datetime] = mapped_column(_ts, server_default=func.now())


class Sesion(Base):
    """Un inicio de sesión. Los tokens llevan su id (sid); cerrada = tokens sin valor."""
    __tablename__ = "sesiones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    creada_en: Mapped[datetime] = mapped_column(_ts, server_default=func.now())
    ultima_actividad: Mapped[datetime] = mapped_column(_ts, server_default=func.now())
    expira_en: Mapped[datetime] = mapped_column(_ts)
    cerrada_en: Mapped[datetime | None] = mapped_column(_ts, default=None)
    motivo_cierre: Mapped[str | None] = mapped_column(String(30), default=None)
    ip: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(200), default=None)


class EventoSeguridad(Base):
    """Login correcto o fallido, bloqueos, cierres de sesión y cambios de clave."""
    __tablename__ = "eventos_seguridad"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha: Mapped[datetime] = mapped_column(_ts, server_default=func.now())
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(50))
    tipo: Mapped[str] = mapped_column(String(30))
    ip: Mapped[str | None] = mapped_column(String(45))
    detalle: Mapped[str | None] = mapped_column(String(300))
