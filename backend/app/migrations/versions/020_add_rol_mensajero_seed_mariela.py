"""Add rol 'mensajero' (antes también sembraba el usuario de Mariela)

Revision ID: 020
Revises: 019
Create Date: 2026-08-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','logistica','paquetes','mensajero'))
    """)

    # El usuario de Mariela ya no se siembra aquí (antes iba con su hash en el código).
    # En producción ya existe; en una base nueva se crea con scripts/crear_usuario.py.


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','logistica','paquetes'))
    """)
