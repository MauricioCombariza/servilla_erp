"""Concede la page_key generar_dat a administrador y logistica

Revision ID: 029
Revises: 028
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador", "logistica"]


def upgrade() -> None:
    valores = ", ".join(f"('{rol}', 'generar_dat')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'generar_dat'")
