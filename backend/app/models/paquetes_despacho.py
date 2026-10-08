from datetime import date, datetime

from sqlalchemy import String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)

ESTADO_SIN_GESTION = "sin gestión"
ESTADO_DANADO = "Paquete dañado"


class PaqueteDespacho(Base):
    """Un paquete de la base de despacho, ya sectorizado (localidad / zona)."""

    __tablename__ = "paquetes_despacho"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(150))
    telefono: Mapped[str | None] = mapped_column(String(30))
    direccion: Mapped[str | None] = mapped_column(Text)
    direccion_estandarizada: Mapped[str | None] = mapped_column(String(100))
    codigo_postal: Mapped[str | None] = mapped_column(String(10))
    localidad: Mapped[str | None] = mapped_column(String(100))
    zona: Mapped[str | None] = mapped_column(String(50))
    f_emi: Mapped[date] = mapped_column(nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{ESTADO_SIN_GESTION}'")
    )
    fecha_creacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
    fecha_modificacion: Mapped[datetime] = mapped_column(_ts, server_default=text("CURRENT_TIMESTAMP"))
