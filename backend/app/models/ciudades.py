from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Ciudad(Base):
    __tablename__ = "ciudades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    departamento: Mapped[str | None] = mapped_column(String(100))
    codigo: Mapped[str | None] = mapped_column(String(10))
    es_bogota: Mapped[bool] = mapped_column(Boolean, default=False)
    ambito: Mapped[str] = mapped_column(String(8), default="nacional")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
