from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class SerialGestion(Base):
    __tablename__ = "seriales_gestion"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    f_emi: Mapped[date | None] = mapped_column()
    f_esc: Mapped[date] = mapped_column(nullable=False)
    planilla: Mapped[str] = mapped_column(String(50), nullable=False)
    cod_men: Mapped[str] = mapped_column(String(4), nullable=False)
    mensajero_id: Mapped[int | None] = mapped_column(ForeignKey("personal.id", ondelete="SET NULL"))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id", ondelete="SET NULL"))
    tipo_gestion: Mapped[str] = mapped_column(String(10), nullable=False)
    tipo_envio: Mapped[str] = mapped_column(String(8), default="sobre")
    ambito: Mapped[str] = mapped_column(String(8), default="bogota")
    precio_cliente: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    precio_mensajero: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    liquidacion_id: Mapped[int | None] = mapped_column()
    factura_id: Mapped[int | None] = mapped_column()
    origen: Mapped[str] = mapped_column(String(8), default="scanner")
    editado_manualmente: Mapped[bool] = mapped_column(Boolean, default=False)
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    mensajero: Mapped["Personal | None"] = relationship("Personal", lazy="selectin")  # type: ignore[name-defined]
    cliente: Mapped["Cliente | None"] = relationship("Cliente", lazy="selectin")  # type: ignore[name-defined]
