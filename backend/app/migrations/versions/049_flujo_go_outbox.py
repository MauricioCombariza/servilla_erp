"""Servicio Go `flujo` (escaneo de tulas y asignación): cola de tareas de iMile,
idempotencia de las operaciones que manda el celular sin señal y avisos NOTIFY.

- imile_tareas: lo que hay que hacer en iMile (ingreso 2.5 / asignar 3.3). La lectura
  se guarda al instante y un pool de páginas Playwright en Go la pasa a iMile después.
- operaciones_cliente: cada operación del celular trae un op_id (UUID); si llega dos
  veces (reintento tras un corte) se responde lo mismo sin repetirla.
- tulas.local_id: la tula abierta en el celular sin señal, antes de tener id del servidor.
- NOTIFY imile_tareas_nueva despierta a los workers apenas llega una tarea.

Revision ID: 049
Revises: 048
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "imile_tareas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(20), nullable=False),  # ingreso | asignar
        sa.Column("serial", sa.String(50), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("tula_serial_id", sa.BigInteger, sa.ForeignKey("tula_seriales.id", ondelete="CASCADE")),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE")),
        sa.Column("envio_id", UUID(as_uuid=True)),  # agrupa las tareas de un "Asignar en iMile"
        sa.Column("usuario", sa.String(50), nullable=False),
        # pendiente | en_proceso | hecha | fallida | cancelada
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("resultado", sa.String(20)),  # ok | repetido | bloqueado | error | cerrada | sin_confirmar
        sa.Column("intentos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("proximo_intento", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("lease_hasta", sa.TIMESTAMP(timezone=True)),
        sa.Column("ultimo_error", sa.Text),
        sa.Column("creado", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("actualizado", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.execute(
        "CREATE INDEX idx_imile_tareas_pendientes ON imile_tareas (tipo, proximo_intento) "
        "WHERE estado = 'pendiente'"
    )
    op.create_index("idx_imile_tareas_envio", "imile_tareas", ["envio_id"])
    op.create_index("idx_imile_tareas_actualizado", "imile_tareas", ["actualizado"])

    op.create_table(
        "operaciones_cliente",
        sa.Column("op_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario", sa.String(50), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("resultado", JSONB, nullable=False),
        sa.Column("creado", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("idx_operaciones_cliente_creado", "operaciones_cliente", ["creado"])

    op.add_column("tulas", sa.Column("local_id", UUID(as_uuid=True)))
    op.create_unique_constraint("uq_tulas_local_id", "tulas", ["local_id"])

    op.execute("""
        CREATE FUNCTION notificar_imile_tarea() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify('imile_tareas_nueva', NEW.tipo);
            RETURN NULL;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_imile_tareas_nueva AFTER INSERT ON imile_tareas
        FOR EACH ROW EXECUTE FUNCTION notificar_imile_tarea()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_imile_tareas_nueva ON imile_tareas")
    op.execute("DROP FUNCTION IF EXISTS notificar_imile_tarea()")
    op.drop_constraint("uq_tulas_local_id", "tulas", type_="unique")
    op.drop_column("tulas", "local_id")
    op.drop_index("idx_operaciones_cliente_creado", table_name="operaciones_cliente")
    op.drop_table("operaciones_cliente")
    op.drop_index("idx_imile_tareas_actualizado", table_name="imile_tareas")
    op.drop_index("idx_imile_tareas_envio", table_name="imile_tareas")
    op.execute("DROP INDEX IF EXISTS idx_imile_tareas_pendientes")
    op.drop_table("imile_tareas")
