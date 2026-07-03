from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Liquidacion(Base):
    __tablename__ = "liquidaciones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_liquidacion: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    personal_id: Mapped[int] = mapped_column(
        ForeignKey("personal.id", ondelete="CASCADE"), nullable=False
    )
    periodo_mes: Mapped[int] = mapped_column(nullable=False)
    periodo_anio: Mapped[int] = mapped_column(nullable=False)
    fecha_generacion: Mapped[date] = mapped_column(nullable=False)
    fecha_pago_programada: Mapped[date] = mapped_column(nullable=False)
    total_entregas: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cantidad_entregas: Mapped[int] = mapped_column(default=0)
    total_horas: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cantidad_horas: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    total_labores: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cantidad_labores: Mapped[int] = mapped_column(default=0)
    total_subsidio: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    bonificaciones: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    descuentos: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_a_pagar: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(10), default="generada")
    fecha_pago_real: Mapped[date | None] = mapped_column()
    metodo_pago: Mapped[str] = mapped_column(String(15), default="transferencia")
    referencia_pago: Mapped[str | None] = mapped_column(String(100))
    observaciones: Mapped[str | None] = mapped_column(Text)
    generado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    aprobado_por: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL")
    )
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
