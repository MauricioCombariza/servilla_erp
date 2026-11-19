from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)
_now = text("CURRENT_TIMESTAMP")


class Proyecto(Base):
    __tablename__ = "proyectos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(String(30), default="otro")
    responsable_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="planeado")
    color: Mapped[str | None] = mapped_column(String(9))
    creado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(_ts, server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(_ts, server_default=_now, onupdate=_now)


class TareaRecurrente(Base):
    __tablename__ = "tareas_recurrentes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    proyecto_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proyectos.id", ondelete="CASCADE"))
    responsable_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    prioridad: Mapped[str] = mapped_column(String(10), default="media")
    frecuencia: Mapped[str] = mapped_column(String(10), nullable=False)
    dias_semana: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger))
    dia_mes: Mapped[int | None] = mapped_column(SmallInteger)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    saltar_festivos: Mapped[bool] = mapped_column(Boolean, default=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    generado_hasta: Mapped[date | None] = mapped_column(Date)
    creado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(_ts, server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(_ts, server_default=_now, onupdate=_now)


class TareaSeguimiento(Base):
    __tablename__ = "tareas_seguimiento"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    proyecto_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("proyectos.id", ondelete="CASCADE"))
    recurrente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tareas_recurrentes.id", ondelete="SET NULL")
    )
    responsable_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    creado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"))
    fecha_programada: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_limite: Mapped[date | None] = mapped_column(Date)
    prioridad: Mapped[str] = mapped_column(String(10), default="media")
    estado: Mapped[str] = mapped_column(String(15), default="pendiente")
    esfuerzo_horas: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    completada_en: Mapped[datetime | None] = mapped_column(_ts)
    created_at: Mapped[datetime] = mapped_column(_ts, server_default=_now)
    updated_at: Mapped[datetime] = mapped_column(_ts, server_default=_now, onupdate=_now)
