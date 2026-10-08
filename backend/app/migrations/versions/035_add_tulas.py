"""Add tulas y tula_seriales (descarga de tulas: contador y seriales leídos), y la
page_key escaneo_tulas para administrador, logistica y mensajero

Revision ID: 035
Revises: 034
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# mensajero: rol del usuario que escanea (como las demás páginas de escaneo del ERP)
ROLES = ["administrador", "logistica", "mensajero"]


def upgrade() -> None:
    op.create_table(
        "tulas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.String(80), nullable=True),
        sa.Column("sin_etiqueta", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("total_esperado", sa.Integer, nullable=True),
        sa.Column("estado", sa.String(10), server_default=sa.text("'abierta'"), nullable=False),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("fecha_apertura", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("fecha_cierre", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("estado IN ('abierta', 'cerrada')", name="ck_tulas_estado"),
        sa.CheckConstraint("sin_etiqueta OR codigo IS NOT NULL", name="ck_tulas_codigo"),
    )
    op.create_index("idx_tulas_fecha", "tulas", ["fecha"])
    # Una sola tula abierta por usuario
    op.create_index(
        "uq_tulas_abierta_por_usuario", "tulas", ["usuario"],
        unique=True, postgresql_where=sa.text("estado = 'abierta'"),
    )

    op.create_table(
        "tula_seriales",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tula_id", sa.BigInteger, sa.ForeignKey("tulas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial", sa.String(50), nullable=False),
        sa.Column("en_tabla", sa.Boolean, nullable=False),
        sa.Column("zona", sa.String(50), nullable=True),
        sa.Column("fecha_escaneo", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("tula_id", "serial", name="uq_tula_seriales_tula_serial"),
    )
    op.create_index("idx_tula_seriales_serial", "tula_seriales", ["serial"])

    valores = ", ".join(f"('{rol}', 'escaneo_tulas')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'escaneo_tulas'")
    op.drop_index("idx_tula_seriales_serial", table_name="tula_seriales")
    op.drop_table("tula_seriales")
    op.drop_index("uq_tulas_abierta_por_usuario", table_name="tulas")
    op.drop_index("idx_tulas_fecha", table_name="tulas")
    op.drop_table("tulas")
