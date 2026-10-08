"""Add paquetes_despacho (paquetes de la base de despacho, sectorizados con
sectorizacion_limites; un serial repetido se reemplaza y vuelve a 'sin gestión')

Revision ID: 032
Revises: 031
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paquetes_despacho",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("serial", sa.String(50), nullable=False),
        sa.Column("nombre", sa.String(150), nullable=True),
        sa.Column("telefono", sa.String(30), nullable=True),
        sa.Column("direccion", sa.Text, nullable=True),
        sa.Column("direccion_estandarizada", sa.String(100), nullable=True),
        sa.Column("codigo_postal", sa.String(10), nullable=True),
        sa.Column("localidad", sa.String(100), nullable=True),
        sa.Column("zona", sa.String(50), nullable=True),
        sa.Column("f_emi", sa.Date, nullable=False),
        sa.Column("estado", sa.String(20), server_default=sa.text("'sin gestión'"), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("serial", name="uq_paquetes_despacho_serial"),
        sa.CheckConstraint(
            "estado IN ('sin gestión', 'Paquete dañado')", name="ck_paquetes_despacho_estado"
        ),
    )
    op.create_index("idx_paquetes_despacho_f_emi", "paquetes_despacho", ["f_emi"])
    op.create_index("idx_paquetes_despacho_zona", "paquetes_despacho", ["zona"])


def downgrade() -> None:
    op.drop_index("idx_paquetes_despacho_zona", table_name="paquetes_despacho")
    op.drop_index("idx_paquetes_despacho_f_emi", table_name="paquetes_despacho")
    op.drop_table("paquetes_despacho")
