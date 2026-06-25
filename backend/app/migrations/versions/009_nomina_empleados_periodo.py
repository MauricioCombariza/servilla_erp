"""Add nomina_empleados_periodo for month-by-month roster

Revision ID: 009
Revises: 008
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS nomina_empleados_periodo (
            id SERIAL PRIMARY KEY,
            empleado_id INTEGER NOT NULL REFERENCES nomina_empleados(id) ON DELETE CASCADE,
            periodo_mes INTEGER NOT NULL CHECK (periodo_mes BETWEEN 1 AND 12),
            periodo_anio INTEGER NOT NULL,
            fecha_creacion TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (empleado_id, periodo_mes, periodo_anio)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nomina_empleados_periodo")
