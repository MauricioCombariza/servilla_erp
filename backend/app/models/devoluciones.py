from datetime import datetime

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Devolucion(Base):
    __tablename__ = "devoluciones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(20))
    direccion: Mapped[str | None] = mapped_column(Text)
    localidad: Mapped[str | None] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(30), default="transito")
    fecha_carga: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        _ts, server_default=text("CURRENT_TIMESTAMP"), onupdate=text("CURRENT_TIMESTAMP")
    )
    fecha_escaneo: Mapped[datetime | None] = mapped_column(_ts, nullable=True)
