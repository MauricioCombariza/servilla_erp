"""Add sectorizacion_limites (una sola tabla con los límites de calle/carrera de los
códigos postales de Bogotá + su localidad, y las 33 zonas específicas con paridad de
placa). Se carga desde app/assets/sectorizacion_limites.csv, que une los tres Excel
de dirnum: limites_estandarizados, localidad_codigo_postal_bogota y zonas_especificas.

Revision ID: 031
Revises: 030
Create Date: 2026-10-08
"""
import csv
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEMILLA = Path(__file__).resolve().parents[2] / "assets" / "sectorizacion_limites.csv"


def _leer_semilla() -> list[dict]:
    with SEMILLA.open(encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        for campo, valor in fila.items():
            if valor == "":
                fila[campo] = None
        fila["orden"] = int(fila["orden"])
    return filas


def upgrade() -> None:
    tabla = op.create_table(
        "sectorizacion_limites",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(50), nullable=False),
        sa.Column("localidad", sa.String(100), nullable=True),
        sa.Column("limite_norte", sa.String(50), nullable=True),
        sa.Column("placas_norte", sa.String(10), nullable=True),
        sa.Column("limite_sur", sa.String(50), nullable=True),
        sa.Column("placas_sur", sa.String(10), nullable=True),
        sa.Column("limite_oriente", sa.String(50), nullable=True),
        sa.Column("placas_oriente", sa.String(10), nullable=True),
        sa.Column("limite_occidente", sa.String(50), nullable=True),
        sa.Column("placas_occidente", sa.String(10), nullable=True),
        sa.Column("orden", sa.Integer, nullable=False),
        sa.Column("activo", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("tipo IN ('codigo_postal', 'zona')", name="ck_sectorizacion_limites_tipo"),
        sa.UniqueConstraint("tipo", "nombre", name="uq_sectorizacion_limites_tipo_nombre"),
    )
    op.bulk_insert(tabla, _leer_semilla())


def downgrade() -> None:
    op.drop_table("sectorizacion_limites")
