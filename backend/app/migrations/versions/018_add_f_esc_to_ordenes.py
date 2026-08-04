"""Add f_esc column to ordenes

Revision ID: 018
Revises: 017
Create Date: 2026-08-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ordenes", sa.Column("f_esc", sa.Date(), nullable=True))
    # Backfill: fecha_recepcion ya representa la fecha de escáner/recepción para
    # las órdenes existentes (misma fuente, ver ordenes_service.py), así que se
    # copia tal cual en vez de dejarla en NULL.
    op.execute("UPDATE ordenes SET f_esc = fecha_recepcion WHERE f_esc IS NULL")


def downgrade() -> None:
    op.drop_column("ordenes", "f_esc")
