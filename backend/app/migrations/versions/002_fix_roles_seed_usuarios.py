"""Fix roles constraint and seed real users

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

    # Inserta los usuarios reales desde auth/users.yaml
    op.execute("""
        INSERT INTO usuarios (username, password_hash, nombre_completo, rol) VALUES
        ('usuario1', '$2b$12$FFsCs/cDjc8VmIXj.I6opukObck/RKEVVbGctuLCHYHskvYrFstFy', 'Catalina Villamizar', 'logistica'),
        ('usuario2', '$2b$12$v2FP7/26mqpghHMNiA203.ufUZSoc4sTmiRtzHWtWdwVns/rQhg4m', 'Cata Villamizar',     'paquetes'),
        ('usuario3', '$2b$12$7432.QgOKrG9eD4zQMWlJeczfaHgcHY9Wo1pGI0rjtKtiUop1uPA6', 'Luz Mary Munoz',      'logistica'),
        ('usuario4', '$2b$12$OkExAwA.8Jm4F8Kqb85rYuMETR7j6AgtoOvNTmFuwqePC35stdMq6', 'Mariela Pabon',       'paquetes')
        ON CONFLICT (username) DO NOTHING
    """)

    # Actualiza el admin con hash para 'admin123' (cambiar en producción)
    op.execute("""
        UPDATE usuarios SET password_hash = '$2b$12$laAExq96yvm98hHYazHJGOAxb1o51AwDlP0X1n2vDzCXilCK8ikKS'
        WHERE username = 'admin'
    """)


def downgrade() -> None:
    op.execute("DELETE FROM usuarios WHERE username IN ('usuario1','usuario2','usuario3','usuario4')")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios
        ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','contabilidad','operaciones','ventas'))
    """)
