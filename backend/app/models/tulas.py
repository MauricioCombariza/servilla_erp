from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)

ESTADO_ABIERTA = "abierta"
ESTADO_CERRADA = "cerrada"


class Tula(Base):
    """Una tula que se está descargando o ya se descargó (Pasos 2.4 y 2.8)."""

    __tablename__ = "tulas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str | None] = mapped_column(String(80))  # NULL si es "Sin etiqueta"
    sin_etiqueta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_esperado: Mapped[int | None] = mapped_column()  # lo trae iMile (2.3)
    estado: Mapped[str] = mapped_column(String(10), nullable=False, default=ESTADO_ABIERTA)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[date] = mapped_column(nullable=False)
    fecha_apertura: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
    fecha_cierre: Mapped[datetime | None] = mapped_column(_ts)


class TulaSerial(Base):
    """Un paquete leído dentro de una tula."""

    __tablename__ = "tula_seriales"
    __table_args__ = (UniqueConstraint("tula_id", "serial", name="uq_tula_seriales_tula_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tula_id: Mapped[int] = mapped_column(ForeignKey("tulas.id", ondelete="CASCADE"), nullable=False)
    serial: Mapped[str] = mapped_column(String(50), nullable=False)
    en_tabla: Mapped[bool] = mapped_column(Boolean, nullable=False)
    zona: Mapped[str | None] = mapped_column(String(50))
    fecha_escaneo: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
    # Ingreso en iMile (Paso 2.5): ok | repetido | bloqueado | error | sin_confirmar | omitido
    imile_estado: Mapped[str | None] = mapped_column(String(20))
    imile_mensaje: Mapped[str | None] = mapped_column(Text)
    imile_fecha: Mapped[datetime | None] = mapped_column(_ts)
