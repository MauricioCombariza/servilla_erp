from datetime import date, datetime

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class EnlaceVista(Base):
    """Enlace secreto del día para ver, sin iniciar sesión, los paquetes que escanea
    un usuario, filtrados por zona (Paso 2.7)."""

    __tablename__ = "enlaces_vista"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)  # quien escanea
    fecha: Mapped[date] = mapped_column(nullable=False)
    expira: Mapped[datetime] = mapped_column(_ts, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
