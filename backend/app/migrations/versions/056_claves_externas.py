"""Registro de claves de sistemas fuera del ERP (SER-MNT-F-02-2 / F-02-3, SER-MNT-PR-02 §20.3).

Solo metadatos: qué cuenta es, quién la custodia, en qué sobre y cofre está y cuándo se
cambió. **Nunca la clave**: esa sigue en el sobre sellado de la bóveda.

Revision ID: 056
Revises: 055
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056"
down_revision: Union[str, None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "claves_externas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("aplicacion", sa.String(100), nullable=False),    # fortinet, MariaDB WEB, Workspace…
        sa.Column("sistema", sa.String(100)),                        # linux, Windows 2008…
        sa.Column("usuario", sa.String(100), nullable=False),       # la cuenta, no la clave
        sa.Column("categoria", sa.String(30), nullable=False),      # app/routers/claves_externas.py
        sa.Column("periodicidad_dias", sa.Integer()),                # NULL = la de la categoría
        sa.Column("custodio_1", sa.String(100)),
        sa.Column("custodio_2", sa.String(100)),
        sa.Column("sobre_no", sa.String(20)),
        sa.Column("cofre_no", sa.String(20)),
        sa.Column("ambiente", sa.String(100)),
        sa.Column("notas", sa.String(500)),
        sa.Column("ultimo_cambio", sa.Date()),                       # NULL = sin registro: vencida
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("aplicacion", "usuario", name="uq_claves_externas_app_usuario"),
    )
    op.create_table(
        "claves_externas_cambios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("clave_id", sa.Integer(),
                  sa.ForeignKey("claves_externas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("responsable", sa.String(100), nullable=False),
        sa.Column("sobre_no", sa.String(20)),
        sa.Column("observacion", sa.String(500)),
        sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("fecha_registro", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_claves_externas_cambios_clave", "claves_externas_cambios", ["clave_id", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_claves_externas_cambios_clave", "claves_externas_cambios")
    op.drop_table("claves_externas_cambios")
    op.drop_table("claves_externas")
