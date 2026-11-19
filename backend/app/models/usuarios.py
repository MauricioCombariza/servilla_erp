from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, false, func
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


class UsuarioClaveAnterior(Base):
    """Hashes de las últimas claves de cada usuario, para no dejar que las repita."""
    __tablename__ = "usuarios_claves_anteriores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha: Mapped[datetime] = mapped_column(_ts, server_default=func.now())
