"""Seed mapeo_clientes con aliases de nombres CSV

Revision ID: 006
Revises: 005
Create Date: 2026-06-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO mapeo_clientes (nombre_csv, nombre_bd, cliente_id)
        SELECT nombre_csv, nombre_bd, c.id
        FROM (VALUES
            ('VEHIGROUP SAS',            'Vehigrupo SAS',              'Vehigrupo SAS'),
            ('-VEHIGROUP SAS',           'Vehigrupo SAS',              'Vehigrupo SAS'),
            ('PRONTICOURRIER EXPRESS SA','Pronticourier Express S.A.S', 'Pronticourier Express S.A.S'),
            ('FIDUCIARIA CAJA SOCIAL',   'Banco Caja Social',          'Banco Caja Social')
        ) AS m(nombre_csv, nombre_bd, nombre_empresa)
        JOIN clientes c ON c.nombre_empresa = m.nombre_empresa
        ON CONFLICT (nombre_csv) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM mapeo_clientes
        WHERE nombre_csv IN (
            'VEHIGROUP SAS', '-VEHIGROUP SAS',
            'PRONTICOURRIER EXPRESS SA', 'FIDUCIARIA CAJA SOCIAL'
        )
    """)
