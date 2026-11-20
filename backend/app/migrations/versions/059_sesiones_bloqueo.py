"""Sesiones en el servidor, bloqueo por intentos fallidos y eventos de seguridad (PR-12).

- usuarios.intentos_fallidos / bloqueado_hasta: tras LOGIN_MAX_INTENTOS fallos seguidos la
  cuenta queda bloqueada LOGIN_BLOQUEO_MINUTOS.
- sesiones: una fila por inicio de sesión. Los tokens llevan su id (sid); si la sesión se
  cierra (salida, inactividad, administrador, cambio de clave) los tokens dejan de servir.
- eventos_seguridad: login correcto o fallido, bloqueos, cierres de sesión, cambios de
  clave. Es la evidencia que piden PR-12 y la revisión quincenal (F-06-4).

Al aplicar no se cierra nada, pero los tokens emitidos antes no llevan sid: cada persona
vuelve a iniciar sesión una vez.

Revision ID: 059
Revises: 058
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "059"
down_revision: Union[str, None] = "058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.add_column("usuarios", sa.Column(
        "intentos_fallidos", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usuarios", sa.Column("bloqueado_hasta", _ts, nullable=True))

    op.create_table(
        "sesiones",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creada_en", _ts, nullable=False, server_default=sa.func.now()),
        sa.Column("ultima_actividad", _ts, nullable=False, server_default=sa.func.now()),
        sa.Column("expira_en", _ts, nullable=False),
        sa.Column("cerrada_en", _ts, nullable=True),
        sa.Column("motivo_cierre", sa.String(30), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(200), nullable=True),
    )
    op.create_index("ix_sesiones_usuario_abiertas", "sesiones", ["usuario_id"],
                    postgresql_where=sa.text("cerrada_en IS NULL"))

    op.create_table(
        "eventos_seguridad",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fecha", _ts, nullable=False, server_default=sa.func.now()),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("username", sa.String(50), nullable=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("detalle", sa.String(300), nullable=True),
    )
    op.create_index("ix_eventos_seguridad_fecha", "eventos_seguridad", ["fecha"])
    op.create_index("ix_eventos_seguridad_usuario", "eventos_seguridad", ["usuario_id", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_eventos_seguridad_usuario", table_name="eventos_seguridad")
    op.drop_index("ix_eventos_seguridad_fecha", table_name="eventos_seguridad")
    op.drop_table("eventos_seguridad")
    op.drop_index("ix_sesiones_usuario_abiertas", table_name="sesiones")
    op.drop_table("sesiones")
    op.drop_column("usuarios", "bloqueado_hasta")
    op.drop_column("usuarios", "intentos_fallidos")
