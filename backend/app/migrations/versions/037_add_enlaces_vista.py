"""Add enlaces_vista: enlace secreto del día para ver sin sesión los paquetes que se
escanean, filtrados por zona (Paso 2.7)

Revision ID: 037
Revises: 036
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enlaces_vista",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("expira", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("token", name="uq_enlaces_vista_token"),
        sa.UniqueConstraint("usuario", "fecha", name="uq_enlaces_vista_usuario_fecha"),
    )


def downgrade() -> None:
    op.drop_table("enlaces_vista")
