from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class Rol(Base):
    __tablename__ = "roles"

    nombre: Mapped[str] = mapped_column(String(30), primary_key=True)
    descripcion: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts, default=None)


class RolPagina(Base):
    __tablename__ = "rol_paginas"
    __table_args__ = (UniqueConstraint("rol", "page_key", name="uq_rol_paginas_rol_page"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rol: Mapped[str] = mapped_column(
        String(30), ForeignKey("roles.nombre", onupdate="CASCADE"), nullable=False
    )
    page_key: Mapped[str] = mapped_column(String(50), nullable=False)
