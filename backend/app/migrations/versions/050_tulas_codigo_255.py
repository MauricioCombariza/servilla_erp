"""tulas.codigo de 80 a 255: el 2026-11-06 se leyó como código de tula algo de más de 80
caracteres y el error de la base trabó la cola del celular toda la mañana (nada de lo
leído llegaba al servidor ni a la vista por zonas). El servicio Go ahora rechaza con 422
lo que pase de 255 y los errores de datos ya no traban la cola.

En producción se amplió a mano antes de esta migración; ALTER TYPE a un varchar más
largo no reescribe la tabla y repetirlo no hace nada.

Revision ID: 050
Revises: 049
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tulas", "codigo", type_=sa.String(255), existing_type=sa.String(80), existing_nullable=True)


def downgrade() -> None:
    op.execute("UPDATE tulas SET codigo = left(codigo, 80) WHERE length(codigo) > 80")
    op.alter_column("tulas", "codigo", type_=sa.String(80), existing_type=sa.String(255), existing_nullable=True)
