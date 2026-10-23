from datetime import date, datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class AsignacionZona(Base):
    """Zona completa asignada a un mensajero en un día (Paso 3.2)."""

    __tablename__ = "asignaciones_zona"
    __table_args__ = (UniqueConstraint("fecha", "zona", name="uq_asignaciones_zona_fecha_zona"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(nullable=False)
    zona: Mapped[str] = mapped_column(String(50), nullable=False)
    personal_id: Mapped[int] = mapped_column(ForeignKey("personal.id", ondelete="CASCADE"), nullable=False)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)  # quien asignó
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))


class AsignacionSerial(Base):
    """Un paquete reasignado a mano a un mensajero en un día, por encima de su zona (Paso 3.2)."""

    __tablename__ = "asignaciones_serial"
    __table_args__ = (UniqueConstraint("fecha", "serial", name="uq_asignaciones_serial_fecha_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(nullable=False)
    serial: Mapped[str] = mapped_column(String(50), nullable=False)
    personal_id: Mapped[int] = mapped_column(ForeignKey("personal.id", ondelete="CASCADE"), nullable=False)
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))


class AsignacionImile(Base):
    """Resultado de asignar un serial a un mensajero en iMile en un día (Paso 3.3)."""

    __tablename__ = "asignaciones_imile"
    __table_args__ = (UniqueConstraint("fecha", "serial", name="uq_asignaciones_imile_fecha_serial"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(nullable=False)
    serial: Mapped[str] = mapped_column(String(50), nullable=False)
    personal_id: Mapped[int] = mapped_column(ForeignKey("personal.id", ondelete="CASCADE"), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)  # ok | repetido | bloqueado | error | sin_confirmar
    mensaje: Mapped[str | None] = mapped_column(Text)
    codigo: Mapped[str | None] = mapped_column(String(20))  # blockCode de iMile
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)  # quien presionó "Asignar en iMile"
    fecha_envio: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
