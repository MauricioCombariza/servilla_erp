from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class PrefacturaCourier(Base):
    __tablename__ = "prefacturas_courier"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cod_mensajero: Mapped[str] = mapped_column(String(4), nullable=False)
    fecha_generacion: Mapped[date] = mapped_column(nullable=False)
    periodo_desde: Mapped[date | None] = mapped_column()
    periodo_hasta: Mapped[date | None] = mapped_column()
    cantidad_planillas: Mapped[int] = mapped_column(default=0)
    cantidad_local: Mapped[int] = mapped_column(default=0)
    cantidad_nacional: Mapped[int] = mapped_column(default=0)
    valor_local: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    valor_nacional: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    valor_total: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    estado: Mapped[str] = mapped_column(String(10), default="borrador")
    notas: Mapped[str | None] = mapped_column(Text)
    valor_ajustado: Mapped[float | None] = mapped_column(Numeric(15, 2))
    notas_ajuste: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(_ts)

    planillas: Mapped[list["PrefacturaPlanilla"]] = relationship(
        back_populates="prefactura", lazy="selectin", cascade="all, delete-orphan"
    )


class PrefacturaPlanilla(Base):
    __tablename__ = "prefactura_planillas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prefactura_id: Mapped[int] = mapped_column(
        ForeignKey("prefacturas_courier.id", ondelete="CASCADE"), nullable=False
    )
    planilla: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha_escaner: Mapped[date | None] = mapped_column()
    cantidad_local: Mapped[int] = mapped_column(default=0)
    cantidad_nacional: Mapped[int] = mapped_column(default=0)
    precio_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    precio_nac: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    valor_local: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    valor_nac: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    valor_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    prefactura: Mapped["PrefacturaCourier"] = relationship(back_populates="planillas")


class FacturaCourierCxp(Base):
    __tablename__ = "facturas_courier_cxp"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prefactura_id: Mapped[int] = mapped_column(
        ForeignKey("prefacturas_courier.id"), nullable=False
    )
    cod_mensajero: Mapped[str] = mapped_column(String(4), nullable=False)
    numero_factura: Mapped[str] = mapped_column(String(100), nullable=False)
    fecha_emision: Mapped[date | None] = mapped_column()
    fecha_vencimiento: Mapped[date] = mapped_column(nullable=False)
    valor_total: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), default="pendiente")
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_pago: Mapped[date | None] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(_ts)
