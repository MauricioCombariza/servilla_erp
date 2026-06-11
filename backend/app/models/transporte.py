from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class FacturaTransporte(Base):
    __tablename__ = "facturas_transporte"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_factura: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_factura: Mapped[date] = mapped_column(nullable=False)
    courrier_id: Mapped[int] = mapped_column(
        ForeignKey("personal.id"), nullable=False
    )
    monto_total: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    total_sobres: Mapped[int] = mapped_column(default=0)
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_vencimiento: Mapped[date | None] = mapped_column()
    monto_pagado: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    estado: Mapped[str] = mapped_column(String(10), default="pendiente")
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)

    courrier: Mapped["Personal"] = relationship("Personal", lazy="selectin")  # type: ignore[name-defined]
    detalles: Mapped[list["DetalleFacturaTransporte"]] = relationship(
        back_populates="factura", lazy="selectin", cascade="all, delete-orphan"
    )


class DetalleFacturaTransporte(Base):
    __tablename__ = "detalle_facturas_transporte"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas_transporte.id", ondelete="CASCADE"), nullable=False
    )
    orden_id: Mapped[int | None] = mapped_column(
        ForeignKey("ordenes.id", ondelete="SET NULL")
    )
    cantidad_sobres: Mapped[int] = mapped_column(default=0)
    costo_asignado: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    factura: Mapped["FacturaTransporte"] = relationship(back_populates="detalles")
    orden: Mapped["Orden"] = relationship("Orden", lazy="selectin")  # type: ignore[name-defined]
