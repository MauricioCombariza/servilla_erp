from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Personal(Base):
    __tablename__ = "personal"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    identificacion: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(100))
    tipo_personal: Mapped[str] = mapped_column(String(20), nullable=False)
    banco: Mapped[str | None] = mapped_column(String(100))
    numero_cuenta: Mapped[str | None] = mapped_column(String(50))
    tipo_cuenta: Mapped[str | None] = mapped_column(String(10))
    dia_pago: Mapped[int] = mapped_column(default=8)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_ingreso: Mapped[date | None] = mapped_column()
    precio_local: Mapped[float | None] = mapped_column(Numeric(10, 0))
    precio_nacional: Mapped[float | None] = mapped_column(Numeric(10, 0))
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    ciudades: Mapped[list["PersonalCiudad"]] = relationship(
        back_populates="personal", lazy="selectin"
    )


class PersonalCiudad(Base):
    __tablename__ = "personal_ciudades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    personal_id: Mapped[int] = mapped_column(ForeignKey("personal.id", ondelete="CASCADE"), nullable=False)
    ciudad_id: Mapped[int] = mapped_column(ForeignKey("ciudades.id", ondelete="CASCADE"), nullable=False)
    tarifa_entrega: Mapped[float | None] = mapped_column(Numeric(10, 2))
    tarifa_devolucion: Mapped[float | None] = mapped_column(Numeric(10, 2))
    vigencia_desde: Mapped[date] = mapped_column(nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column()
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    personal: Mapped["Personal"] = relationship(back_populates="ciudades")
