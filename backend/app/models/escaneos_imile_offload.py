from datetime import date, datetime

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class EscaneoImileOffload(Base):
    __tablename__ = "escaneos_imile_offload"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column()
    cod_men: Mapped[str] = mapped_column(String(4), nullable=False)
    nombre_mensajero: Mapped[str] = mapped_column(String(150), nullable=False)
    serial: Mapped[str] = mapped_column(String(50), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_creacion: Mapped[datetime | None] = mapped_column(
        _ts, server_default=text("CURRENT_TIMESTAMP")
    )
