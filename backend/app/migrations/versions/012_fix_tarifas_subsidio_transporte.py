"""Flatten transporte_completo rate to 8333 (matches legacy MySQL policy)

Revision ID: 012
Revises: 011
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE tarifas_servicios SET tarifa = 8333 "
        "WHERE tipo_servicio = 'transporte_completo' AND activo = TRUE"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE tarifas_servicios SET tarifa = 8333.33 "
        "WHERE tipo_servicio = 'transporte_completo' AND activo = TRUE"
    )
