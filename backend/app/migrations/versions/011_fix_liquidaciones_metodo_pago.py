"""Fix liquidaciones.metodo_pago length (transferencia = 13 chars)

Revision ID: 011
Revises: 010
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE liquidaciones ALTER COLUMN metodo_pago TYPE VARCHAR(15)")


def downgrade() -> None:
    op.execute("ALTER TABLE liquidaciones ALTER COLUMN metodo_pago TYPE VARCHAR(12)")
