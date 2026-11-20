"""Segundo factor con código del celular (TOTP) y códigos de respaldo (app/auth/mfa.py).

- usuarios.mfa_secreto: secreto TOTP cifrado. Se llena al empezar la configuración;
  mfa_activo pasa a TRUE cuando la persona confirma el primer código.
- usuarios.mfa_ultimo_paso: último paso de 30 s usado (un código no sirve dos veces).
- usuarios_mfa_respaldo: hashes de los 10 códigos de un solo uso.

Nadie queda con MFA activo al aplicar: con MFA_OBLIGATORIO cada persona lo configura
la próxima vez que inicie sesión.

Revision ID: 061
Revises: 060
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "061"
down_revision: Union[str, None] = "060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("mfa_secreto", sa.String(255), nullable=True))
    op.add_column("usuarios", sa.Column(
        "mfa_activo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("usuarios", sa.Column("mfa_ultimo_paso", sa.BigInteger(), nullable=True))

    op.create_table(
        "usuarios_mfa_respaldo",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("codigo_hash", sa.String(255), nullable=False),
        sa.Column("usado_en", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_usuarios_mfa_respaldo_usuario", "usuarios_mfa_respaldo", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_usuarios_mfa_respaldo_usuario", table_name="usuarios_mfa_respaldo")
    op.drop_table("usuarios_mfa_respaldo")
    op.drop_column("usuarios", "mfa_ultimo_paso")
    op.drop_column("usuarios", "mfa_activo")
    op.drop_column("usuarios", "mfa_secreto")
