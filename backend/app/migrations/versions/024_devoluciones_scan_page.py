"""Concede la page_key devoluciones_scan a administrador, logistica y mensajero

Revision ID: 024
Revises: 023
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador", "logistica", "mensajero"]


def upgrade() -> None:
    valores = ", ".join(f"('{rol}', 'devoluciones_scan')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'devoluciones_scan'")
