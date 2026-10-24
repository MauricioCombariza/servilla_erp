"""asignaciones_imile: el bloqueo 1118 "Guía ya cerrada" pasa de "bloqueado" a "cerrada"
(estado propio que no se vuelve a mandar a iMile). Corrige lo guardado el 2026-10-23.

Revision ID: 045
Revises: 044
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE asignaciones_imile SET estado = 'cerrada' WHERE codigo = '1118' AND estado = 'bloqueado'")


def downgrade() -> None:
    op.execute("UPDATE asignaciones_imile SET estado = 'bloqueado' WHERE estado = 'cerrada'")
