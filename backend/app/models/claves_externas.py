"""Registro de claves de sistemas fuera del ERP (SER-MNT-F-02-2 / F-02-3). Solo metadatos:
la clave nunca se guarda aquí, sigue en el sobre sellado de la bóveda."""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, func, true
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class ClaveExterna(Base):
    __tablename__ = "claves_externas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    aplicacion: Mapped[str] = mapped_column(String(100), nullable=False)
    sistema: Mapped[str | None] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(100), nullable=False)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    periodicidad_dias: Mapped[int | None] = mapped_column(Integer)
    custodio_1: Mapped[str | None] = mapped_column(String(100))
    custodio_2: Mapped[str | None] = mapped_column(String(100))
    sobre_no: Mapped[str | None] = mapped_column(String(20))
    cofre_no: Mapped[str | None] = mapped_column(String(20))
    ambiente: Mapped[str | None] = mapped_column(String(100))
    notas: Mapped[str | None] = mapped_column(String(500))
    ultimo_cambio: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, server_default=true(), default=True)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts, server_default=func.now())


class ClaveExternaCambio(Base):
    __tablename__ = "claves_externas_cambios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    clave_id: Mapped[int] = mapped_column(ForeignKey("claves_externas.id", ondelete="CASCADE"))
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    responsable: Mapped[str] = mapped_column(String(100), nullable=False)
    sobre_no: Mapped[str | None] = mapped_column(String(20))
    observacion: Mapped[str | None] = mapped_column(String(500))
    registrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha_registro: Mapped[datetime | None] = mapped_column(_ts, server_default=func.now())
