from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre_empresa: Mapped[str] = mapped_column(String(150), nullable=False)
    nit: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    contacto_nombre: Mapped[str | None] = mapped_column(String(100))
    contacto_telefono: Mapped[str | None] = mapped_column(String(20))
    contacto_email: Mapped[str | None] = mapped_column(String(100))
    direccion: Mapped[str | None] = mapped_column(Text)
    ciudad: Mapped[str | None] = mapped_column(String(50))
    plazo_pago_dias: Mapped[int] = mapped_column(default=30)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    precios: Mapped[list["PrecioCliente"]] = relationship(
        back_populates="cliente", lazy="selectin"
    )


class PrecioCliente(Base):
    __tablename__ = "precios_cliente"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    tipo_servicio: Mapped[str] = mapped_column(String(8), nullable=False)
    ambito: Mapped[str] = mapped_column(String(8), nullable=False)
    precio_entrega: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    precio_devolucion: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    costo_mensajero_entrega: Mapped[float | None] = mapped_column(Numeric(10, 2), default=0)
    costo_mensajero_devolucion: Mapped[float | None] = mapped_column(Numeric(10, 2), default=0)
    vigencia_desde: Mapped[date] = mapped_column(nullable=False)
    vigencia_hasta: Mapped[date | None] = mapped_column()
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)

    cliente: Mapped["Cliente"] = relationship(back_populates="precios")
