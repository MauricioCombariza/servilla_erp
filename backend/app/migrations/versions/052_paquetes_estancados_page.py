"""Concede la page_key paquetes_estancados (paquetes con más de N días sin entregar)
a administrador y logistica.

Revision ID: 052
Revises: 051
Create Date: 2026-11-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador", "logistica"]


def upgrade() -> None:
    valores = ", ".join(f"('{rol}', 'paquetes_estancados')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'paquetes_estancados'")
