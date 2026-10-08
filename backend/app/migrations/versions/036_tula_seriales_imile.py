"""tula_seriales: resultado del ingreso del paquete en iMile (Paso 2.5)

Revision ID: 036
Revises: 035
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ok | repetido | bloqueado | error | sin_confirmar | omitido (ingreso apagado)
    op.add_column("tula_seriales", sa.Column("imile_estado", sa.String(20), nullable=True))
    op.add_column("tula_seriales", sa.Column("imile_mensaje", sa.Text, nullable=True))
    op.add_column("tula_seriales", sa.Column("imile_fecha", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tula_seriales", "imile_fecha")
    op.drop_column("tula_seriales", "imile_mensaje")
    op.drop_column("tula_seriales", "imile_estado")
