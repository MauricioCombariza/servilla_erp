from datetime import datetime

from sqlalchemy import Boolean, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Geocerca(Base):
    __tablename__ = "geocercas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    poligono: Mapped[dict] = mapped_column(JSONB, nullable=False)
    area_m2: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_por: Mapped[str | None] = mapped_column(String(100))
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        _ts, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP")
    )

    # Futuro: cuando exista una tabla de coordenadas de entregas, la sectorización
    # se resuelve con shapely.geometry.shape(poligono).contains(Point(lng, lat))
    # sobre las geocercas activas — no requiere columnas adicionales aquí.
