from datetime import date, datetime

from sqlalchemy import Boolean, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TIMESTAMP

from app.database import Base

_ts = TIMESTAMP(timezone=True)


class NominaEmpleado(Base):
    __tablename__ = "nomina_empleados"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre_completo: Mapped[str] = mapped_column(String(150), nullable=False)
    identificacion: Mapped[str | None] = mapped_column(String(20), unique=True)
    cargo: Mapped[str | None] = mapped_column(String(100))
    salario_mensual: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    tiene_auxilio_transporte: Mapped[bool] = mapped_column(Boolean, default=False)
    auxilio_no_salarial: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    fecha_ingreso: Mapped[date | None] = mapped_column()
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)


class NominaProvision(Base):
    __tablename__ = "nomina_provisiones"
    __table_args__ = (
        UniqueConstraint("empleado_id", "periodo_mes", "periodo_anio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    empleado_id: Mapped[int] = mapped_column(nullable=False)
    periodo_mes: Mapped[int] = mapped_column(nullable=False)
    periodo_anio: Mapped[int] = mapped_column(nullable=False)
    salario_base: Mapped[float | None] = mapped_column(Numeric(15, 2))
    auxilio_transporte: Mapped[float | None] = mapped_column(Numeric(15, 2))
    auxilio_no_salarial: Mapped[float | None] = mapped_column(Numeric(15, 2))
    arl: Mapped[float | None] = mapped_column(Numeric(15, 2))
    eps: Mapped[float | None] = mapped_column(Numeric(15, 2))
    afp: Mapped[float | None] = mapped_column(Numeric(15, 2))
    caja_compensacion: Mapped[float | None] = mapped_column(Numeric(15, 2))
    prima: Mapped[float | None] = mapped_column(Numeric(15, 2))
    cesantias: Mapped[float | None] = mapped_column(Numeric(15, 2))
    int_cesantias: Mapped[float | None] = mapped_column(Numeric(15, 2))
    vacaciones: Mapped[float | None] = mapped_column(Numeric(15, 2))
    fecha_creacion: Mapped[datetime | None] = mapped_column(_ts)


class NominaParametro(Base):
    __tablename__ = "nomina_parametros"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    parametro: Mapped[str] = mapped_column(String(100), nullable=False)
    valor: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    vigencia_desde: Mapped[date] = mapped_column(nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
