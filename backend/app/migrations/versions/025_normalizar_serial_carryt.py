"""Normalizar serial de escaneos_carryt al primer segmento (antes del primer guion) y eliminar duplicados

Revision ID: 025
Revises: 024
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import ARRAY, Integer, bindparam

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _normalizar(serial: str) -> str:
    return serial.split("-", 1)[0]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, serial FROM escaneos_carryt ORDER BY fecha_creacion ASC, id ASC"
        )
    ).fetchall()

    grupos: dict[str, list[int]] = {}
    for row in rows:
        normalizado = _normalizar(row.serial)
        grupos.setdefault(normalizado, []).append(row.id)

    ids_a_borrar = [id_ for ids in grupos.values() for id_ in ids[1:]]
    if ids_a_borrar:
        stmt = sa.text("DELETE FROM escaneos_carryt WHERE id = ANY(:ids)").bindparams(
            bindparam("ids", type_=ARRAY(Integer))
        )
        conn.execute(stmt, {"ids": ids_a_borrar})

    for normalizado, ids in grupos.items():
        id_sobreviviente = ids[0]
        conn.execute(
            sa.text("UPDATE escaneos_carryt SET serial = :serial WHERE id = :id"),
            {"serial": normalizado, "id": id_sobreviviente},
        )


def downgrade() -> None:
    # No reversible: el sufijo UUID original de cada serial se pierde al truncar,
    # y las filas duplicadas eliminadas no se pueden reconstruir.
    pass
