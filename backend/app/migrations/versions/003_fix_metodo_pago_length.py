"""Fix metodo_pago VARCHAR length (transferencia = 13 chars)

Revision ID: 003
Revises: 002
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table, col in [
        ("liquidaciones", "metodo_pago"),
        ("pagos_recibidos", "metodo_pago"),
        ("pagos_realizados", "metodo_pago"),
    ]:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(15)")


def downgrade() -> None:
    for table, col in [
        ("liquidaciones", "metodo_pago"),
        ("pagos_recibidos", "metodo_pago"),
        ("pagos_realizados", "metodo_pago"),
    ]:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(12)")
