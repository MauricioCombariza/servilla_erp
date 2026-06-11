from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanillaRevisada(Base):
    __tablename__ = "planillas_revisadas"

    # La tabla usa 'lot_esc' como PK (nombre histórico del campo planilla)
    lot_esc: Mapped[str] = mapped_column(String(100), primary_key=True)
    fecha_revision: Mapped[date] = mapped_column(Date, nullable=False)
    revisado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
