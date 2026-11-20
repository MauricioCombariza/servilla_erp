"""Esquema legacy: copia cruda del FoxPro que mantiene el replicador (replicador/).

- legacy.<archivo>: las crea el propio replicador, una por archivo del SCO, con los campos
  del DBF más _recno, _hash, _borrado, _crudo y _visto_en.
- legacy._archivos: estado de cada archivo (última marca, última pasada buena, último error).
  El ERP la mira para avisar si la réplica se detuvo.
- legacy._conciliacion: resultado de cada pasada (conteo y suma de hashes DBF vs Postgres).

El rol del replicador (con su clave) se crea aparte, con replicador/sql/rol.sql: aquí no
van claves. Ver docs/diseno_ola1_replicador.md.

Revision ID: 062
Revises: 061
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ts = sa.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS legacy")
    op.create_table(
        "_archivos",
        sa.Column("tabla", sa.String(64), primary_key=True),
        sa.Column("recurso", sa.String(30), nullable=False),
        sa.Column("ruta", sa.String(200), nullable=False),
        sa.Column("marca", sa.String(100), nullable=False, server_default=""),
        sa.Column("registros", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ultima_pasada", _ts, nullable=True),
        sa.Column("ultima_buena", _ts, nullable=True),
        sa.Column("ultimo_error", sa.Text(), nullable=True),
        schema="legacy",
    )
    op.create_table(
        "_conciliacion",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fecha", _ts, nullable=False, server_default=sa.func.now()),
        sa.Column("tabla", sa.String(64), nullable=False),
        sa.Column("registros_dbf", sa.BigInteger(), nullable=False),
        sa.Column("incluidos", sa.BigInteger(), nullable=False),
        sa.Column("borrados", sa.BigInteger(), nullable=False),
        sa.Column("enviados", sa.BigInteger(), nullable=False),
        sa.Column("en_pg", sa.BigInteger(), nullable=False),
        sa.Column("suma_dbf", sa.Numeric(), nullable=False),
        sa.Column("suma_pg", sa.Numeric(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("segundos", sa.Float(), nullable=False),
        schema="legacy",
    )
    op.create_index("ix_conciliacion_tabla_fecha", "_conciliacion", ["tabla", "fecha"], schema="legacy")


def downgrade() -> None:
    # Solo lo que crea esta migración; las tablas que creó el replicador se borran con el esquema
    op.drop_index("ix_conciliacion_tabla_fecha", table_name="_conciliacion", schema="legacy")
    op.drop_table("_conciliacion", schema="legacy")
    op.drop_table("_archivos", schema="legacy")
    op.execute("DROP SCHEMA IF EXISTS legacy CASCADE")
