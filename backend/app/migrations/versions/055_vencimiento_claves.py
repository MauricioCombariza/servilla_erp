"""Vencimiento y cambio periódico de contraseñas (SER-MNT-PR-02 §20.3).

- usuarios.clave_cambiada_en: desde cuándo rige la clave actual. La clave vence a los
  CLAVE_VIGENCIA_DIAS (45 por defecto) de esa fecha.
- usuarios.debe_cambiar_clave: la próxima vez que entre debe poner una clave suya
  (clave temporal asignada por un administrador, o arranque de esta política).
- usuarios_claves_anteriores: hashes de las últimas claves, para no repetirlas.

Al aplicar, todos los usuarios que ya existen quedan con debe_cambiar_clave: así arranca
el ciclo con claves que cumplen la política nueva (12 caracteres, letras y números) y se
cambian las que pudieron quedar expuestas en el historial del repositorio.

Revision ID: 055
Revises: 054
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column(
        "clave_cambiada_en", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("usuarios", sa.Column(
        "debe_cambiar_clave", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE usuarios SET debe_cambiar_clave = TRUE")

    op.create_table(
        "usuarios_claves_anteriores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("fecha", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usuarios_claves_anteriores_usuario", "usuarios_claves_anteriores",
                    ["usuario_id", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_usuarios_claves_anteriores_usuario", "usuarios_claves_anteriores")
    op.drop_table("usuarios_claves_anteriores")
    op.drop_column("usuarios", "debe_cambiar_clave")
    op.drop_column("usuarios", "clave_cambiada_en")
