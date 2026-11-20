"""Concede la page_key tiempo_entrega (informe de tiempo de entrega iMile) a
administrador y logistica.

Revision ID: 058
Revises: 057
Create Date: 2026-11-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "058"
down_revision: Union[str, None] = "057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador", "logistica"]


def upgrade() -> None:
    valores = ", ".join(f"('{rol}', 'tiempo_entrega')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'tiempo_entrega'")
