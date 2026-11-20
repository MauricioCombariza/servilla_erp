"""Intentos fallidos de consultar el tracking iMile de una guía entregada.

Una guía con el tracking guardado (novedades_imile no NULL) no se vuelve a consultar.
Las que iMile no encuentra o que fallan se reintentaban en cada carga para siempre:
ahora se cuentan y después de 3 intentos se dejan de consultar. No cuentan "busy" ni
"Unauthorized" (son de iMile o de la sesión, no de la guía).

Revision ID: 060
Revises: 059
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "060"
down_revision: Union[str, None] = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "seriales_gestion",
        sa.Column("tracking_intentos", sa.SmallInteger, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("seriales_gestion", "tracking_intentos")
