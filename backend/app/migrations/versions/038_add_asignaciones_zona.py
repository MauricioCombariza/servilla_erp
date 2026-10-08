"""Add asignaciones_zona (cada zona completa a un solo mensajero por día),
asignaciones_serial (paquetes reasignados uno a uno, por encima de la zona) y la
page_key asignacion_zonas para administrador y logistica (Pasos 3.1 y 3.2)

Revision ID: 038
Revises: 037
Create Date: 2026-10-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador", "logistica"]


def upgrade() -> None:
    op.create_table(
        "asignaciones_zona",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("zona", sa.String(50), nullable=False),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("fecha", "zona", name="uq_asignaciones_zona_fecha_zona"),
    )
    op.create_index("idx_asignaciones_zona_personal_fecha", "asignaciones_zona", ["personal_id", "fecha"])

    op.create_table(
        "asignaciones_serial",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("serial", sa.String(50), nullable=False),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("fecha", "serial", name="uq_asignaciones_serial_fecha_serial"),
    )
    op.create_index("idx_asignaciones_serial_personal_fecha", "asignaciones_serial", ["personal_id", "fecha"])

    valores = ", ".join(f"('{rol}', 'asignacion_zonas')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'asignacion_zonas'")
    op.drop_index("idx_asignaciones_serial_personal_fecha", table_name="asignaciones_serial")
    op.drop_table("asignaciones_serial")
    op.drop_index("idx_asignaciones_zona_personal_fecha", table_name="asignaciones_zona")
    op.drop_table("asignaciones_zona")
