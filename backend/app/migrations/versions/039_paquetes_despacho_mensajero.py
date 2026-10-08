"""Concede la page_key paquetes_despacho al rol mensajero: quien escanea (Mariela)
sube desde el celular la base de despacho que llega por WhatsApp (Paso 1.4)

Revision ID: 039
Revises: 038
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "039"
down_revision: Union[str, None] = "038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO rol_paginas (rol, page_key) VALUES ('mensajero', 'paquetes_despacho')
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE rol = 'mensajero' AND page_key = 'paquetes_despacho'")
