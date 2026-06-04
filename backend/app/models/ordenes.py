from datetime import date, datetime

from sqlalchemy import Boolean, Computed, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Orden(Base):
    __tablename__ = "ordenes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero_orden: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), nullable=False)
    ciudad_destino_id: Mapped[int | None] = mapped_column(ForeignKey("ciudades.id", ondelete="SET NULL"))
    fecha_recepcion: Mapped[date] = mapped_column(nullable=False)
    tipo_servicio: Mapped[str] = mapped_column(String(8), nullable=False)

    cantidad_total: Mapped[int] = mapped_column(default=0)
    cantidad_recibido: Mapped[int] = mapped_column(default=0)
    cantidad_en_cajoneras: Mapped[int] = mapped_column(default=0)
    cantidad_en_lleva: Mapped[int] = mapped_column(default=0)
    cantidad_entregados: Mapped[int] = mapped_column(default=0)
    cantidad_devolucion: Mapped[int] = mapped_column(default=0)

    precio_unitario: Mapped[float | None] = mapped_column(Numeric(10, 2))
    valor_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    costo_mensajero_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    costo_alistamiento_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    costo_pegado_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    costo_transporte_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    costo_flete_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    # GENERATED ALWAYS AS STORED — SQLAlchemy no los incluye en INSERT/UPDATE
    costo_total: Mapped[float] = mapped_column(
        Numeric(12, 2),
        Computed(
            "COALESCE(costo_mensajero_total,0)+COALESCE(costo_alistamiento_total,0)"
            "+COALESCE(costo_pegado_total,0)+COALESCE(costo_transporte_total,0)"
            "+COALESCE(costo_flete_total,0)",
            persisted=True,
        ),
    )
    utilidad_total: Mapped[float] = mapped_column(
        Numeric(12, 2),
        Computed(
            "COALESCE(valor_total,0)-(COALESCE(costo_mensajero_total,0)+COALESCE(costo_alistamiento_total,0)"
            "+COALESCE(costo_pegado_total,0)+COALESCE(costo_transporte_total,0)+COALESCE(costo_flete_total,0))",
            persisted=True,
        ),
    )

    estado: Mapped[str] = mapped_column(String(10), default="activa")
    facturado: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_finalizacion: Mapped[date | None] = mapped_column()
    observaciones: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)
    fecha_modificacion: Mapped[datetime | None] = mapped_column(_ts)

    # Relationships (lazy=selectin para cargar junto al objeto)
    cliente: Mapped["Cliente"] = relationship("Cliente", lazy="selectin")  # type: ignore[name-defined]
    ciudad_destino: Mapped["Ciudad | None"] = relationship("Ciudad", lazy="selectin")  # type: ignore[name-defined]
