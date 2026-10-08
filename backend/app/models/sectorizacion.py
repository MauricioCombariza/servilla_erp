from datetime import datetime

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class SectorizacionLimite(Base):
    """Límites de calle/carrera de un código postal (con su localidad) o de una zona específica."""

    __tablename__ = "sectorizacion_limites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # 'codigo_postal' | 'zona'
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    localidad: Mapped[str | None] = mapped_column(String(100))
    limite_norte: Mapped[str | None] = mapped_column(String(50))
    placas_norte: Mapped[str | None] = mapped_column(String(10))  # 'par' | 'impar' | 'cualquiera' | NULL
    limite_sur: Mapped[str | None] = mapped_column(String(50))
    placas_sur: Mapped[str | None] = mapped_column(String(10))
    limite_oriente: Mapped[str | None] = mapped_column(String(50))
    placas_oriente: Mapped[str | None] = mapped_column(String(10))
    limite_occidente: Mapped[str | None] = mapped_column(String(50))
    placas_occidente: Mapped[str | None] = mapped_column(String(10))
    orden: Mapped[int] = mapped_column(nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
