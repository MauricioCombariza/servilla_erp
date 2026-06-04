from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class RegistroHoras(Base):
    __tablename__ = "registro_horas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    personal_id: Mapped[int] = mapped_column(
        ForeignKey("personal.id", ondelete="CASCADE"), nullable=False
    )
    orden_id: Mapped[int | None] = mapped_column(
        ForeignKey("ordenes.id", ondelete="SET NULL")
    )
    fecha: Mapped[date] = mapped_column(nullable=False)
    horas_trabajadas: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    tarifa_hora: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # total es GENERATED ALWAYS AS (horas_trabajadas * tarifa_hora) STORED — solo lectura
    tipo_trabajo: Mapped[str] = mapped_column(String(25), nullable=False)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(_ts)
    liquidado: Mapped[bool] = mapped_column(Boolean, default=False)
    liquidacion_id: Mapped[int | None] = mapped_column()
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)


class RegistroLabores(Base):
    __tablename__ = "registro_labores"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    personal_id: Mapped[int] = mapped_column(
        ForeignKey("personal.id", ondelete="CASCADE"), nullable=False
    )
    orden_id: Mapped[int | None] = mapped_column(
        ForeignKey("ordenes.id", ondelete="SET NULL")
    )
    fecha: Mapped[date] = mapped_column(nullable=False)
    tipo_labor: Mapped[str] = mapped_column(String(25), nullable=False)
    cantidad: Mapped[int] = mapped_column(nullable=False)
    tarifa_unitaria: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # total es GENERATED ALWAYS AS (cantidad * tarifa_unitaria) STORED — solo lectura
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(_ts)
    liquidado: Mapped[bool] = mapped_column(Boolean, default=False)
    liquidacion_id: Mapped[int | None] = mapped_column()
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
