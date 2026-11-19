"""Fix roles constraint (antes también sembraba usuarios reales)

Revision ID: 002
Revises: 001
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reemplaza el CHECK constraint de roles con los roles reales del sistema
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','logistica','paquetes'))
    """)

    # Actualiza el usuario admin ya insertado
    op.execute("UPDATE usuarios SET rol = 'administrador' WHERE username = 'admin'")

    # Los usuarios reales ya no se siembran aquí (antes iban con su hash en el código).
    # En producción ya existen; en una base nueva se crean con scripts/crear_usuario.py.


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','contabilidad','operaciones','ventas'))
    """)
