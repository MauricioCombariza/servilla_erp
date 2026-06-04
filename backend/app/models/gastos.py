from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class GastoAdministrativo(Base):
    __tablename__ = "gastos_administrativos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(nullable=False)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    proveedor: Mapped[str | None] = mapped_column(String(150))
    numero_factura: Mapped[str | None] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(10), default="pendiente")
    fecha_pago: Mapped[date | None] = mapped_column()
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)


class GastoFijoMensual(Base):
    __tablename__ = "gastos_fijos_mensuales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    dia_pago: Mapped[int] = mapped_column(default=1)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(_ts)

    pagos: Mapped[list["PagoGastoFijo"]] = relationship(
        back_populates="gasto_fijo", lazy="selectin"
    )


class PagoGastoFijo(Base):
    __tablename__ = "pagos_gastos_fijos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    gasto_fijo_id: Mapped[int] = mapped_column(
        ForeignKey("gastos_fijos_mensuales.id"), nullable=False
    )
    mes: Mapped[int] = mapped_column(nullable=False)
    anio: Mapped[int] = mapped_column(nullable=False)
    monto_pagado: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    fecha_pago: Mapped[date] = mapped_column(nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(_ts)

    gasto_fijo: Mapped["GastoFijoMensual"] = relationship(back_populates="pagos")
