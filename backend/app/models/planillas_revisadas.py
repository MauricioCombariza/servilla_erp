from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanillaRevisada(Base):
    __tablename__ = "planillas_revisadas"

    planilla: Mapped[str] = mapped_column(String(100), primary_key=True)
    fecha_revision: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revisado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
