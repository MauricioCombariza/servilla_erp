"""Add rol 'mensajero' y crea usuario Mariela (acceso solo a Carryt)

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

    # bcrypt.hashpw(b"Pabon", bcrypt.gensalt())
    op.execute("""
        INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES
        ('mariela', '$2b$12$zipTqiU0q/7imIsU/aVTruWe89VJOFajFM2FtZiOonvrl.GdbXcVe', 'Mariela Pabon', 'mensajero')
        ON CONFLICT (username) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM usuarios WHERE username = 'mariela'")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','logistica','paquetes'))
    """)
