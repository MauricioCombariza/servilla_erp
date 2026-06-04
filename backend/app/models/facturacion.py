from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class FacturaEmitida(Base):
    __tablename__ = "facturas_emitidas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_factura: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    fecha_emision: Mapped[date] = mapped_column(nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(nullable=False)
    periodo_mes: Mapped[int] = mapped_column(nullable=False)
    periodo_anio: Mapped[int] = mapped_column(nullable=False)
    cantidad_items: Mapped[int] = mapped_column(default=0)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    descuento: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_pendiente: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), default="pendiente")
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="selectin")  # type: ignore[name-defined]
    detalles: Mapped[list["DetalleFacturaEmitida"]] = relationship(
        back_populates="factura", lazy="selectin", cascade="all, delete-orphan"
    )
    pagos: Mapped[list["PagoRecibido"]] = relationship(
        back_populates="factura", lazy="selectin"
    )


class DetalleFacturaEmitida(Base):
    __tablename__ = "detalle_facturas_emitidas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas_emitidas.id", ondelete="CASCADE"), nullable=False
    )
    orden_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes.id", ondelete="SET NULL"))
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[int] = mapped_column(default=1)
    precio_unitario: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    factura: Mapped["FacturaEmitida"] = relationship(back_populates="detalles")


class PagoRecibido(Base):
    __tablename__ = "pagos_recibidos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas_emitidas.id", ondelete="CASCADE"), nullable=False
    )
    fecha_pago: Mapped[date] = mapped_column(nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(15), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    usuario_registro_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)

    factura: Mapped["FacturaEmitida"] = relationship(back_populates="pagos")


class FacturaRecibida(Base):
    __tablename__ = "facturas_recibidas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_factura: Mapped[str] = mapped_column(String(50), nullable=False)
    personal_id: Mapped[int] = mapped_column(ForeignKey("personal.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(15), nullable=False)
    fecha_recepcion: Mapped[date] = mapped_column(nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(nullable=False)
    periodo_mes: Mapped[int | None] = mapped_column()
    periodo_anio: Mapped[int | None] = mapped_column()
    cantidad_items: Mapped[int] = mapped_column(default=0)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    descuento: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_pendiente: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), default="pendiente")
    observaciones: Mapped[str | None] = mapped_column(Text)
    archivo_adjunto: Mapped[str | None] = mapped_column(String(255))
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    personal: Mapped["Personal"] = relationship("Personal", lazy="selectin")  # type: ignore[name-defined]
    detalles: Mapped[list["DetalleFacturaRecibida"]] = relationship(
        back_populates="factura", lazy="selectin", cascade="all, delete-orphan"
    )
    pagos: Mapped[list["PagoRealizado"]] = relationship(
        back_populates="factura", lazy="selectin"
    )


class DetalleFacturaRecibida(Base):
    __tablename__ = "detalle_facturas_recibidas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas_recibidas.id", ondelete="CASCADE"), nullable=False
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    cantidad: Mapped[int] = mapped_column(default=1)
    precio_unitario: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    factura: Mapped["FacturaRecibida"] = relationship(back_populates="detalles")


class PagoRealizado(Base):
    __tablename__ = "pagos_realizados"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    factura_id: Mapped[int | None] = mapped_column(
        ForeignKey("facturas_recibidas.id", ondelete="CASCADE")
    )
    liquidacion_id: Mapped[int | None] = mapped_column()  # FK a liquidaciones — sin ORM FK hasta implementar ese módulo
    fecha_pago: Mapped[date] = mapped_column(nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(15), nullable=False)
    referencia: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    usuario_registro_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)

    factura: Mapped["FacturaRecibida | None"] = relationship(back_populates="pagos")
