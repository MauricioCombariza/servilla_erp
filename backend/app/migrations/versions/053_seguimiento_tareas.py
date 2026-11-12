"""Seguimiento de tareas y proyectos: tareas de hoy/mañana, plan semanal y anual,
demoradas, proyectos (seguridad de la información, nuevos proyectos…) repartidos
semana a semana y plantillas de tareas recurrentes.

- proyectos: agrupan tareas con un rango de fechas y un responsable.
- tareas_recurrentes: plantillas diaria/semanal/mensual; las tareas se materializan
  perezosamente en tareas_seguimiento (UNIQUE recurrente_id + fecha_programada).
- tareas_seguimiento: cada tarea con su fecha programada (define día y semana ISO).
- Concede la page_key seguimiento_tareas a administrador.

Revision ID: 053
Revises: 052
Create Date: 2026-11-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["administrador"]
_ts = sa.TIMESTAMP(timezone=True)
_now = sa.text("CURRENT_TIMESTAMP")


def _usuario_fk(nombre: str, nullable: bool = True) -> sa.Column:
    return sa.Column(nombre, sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "proyectos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(150), nullable=False),
        sa.Column("descripcion", sa.Text),
        sa.Column("categoria", sa.String(30), nullable=False, server_default="otro"),
        _usuario_fk("responsable_id"),
        sa.Column("fecha_inicio", sa.Date, nullable=False),
        sa.Column("fecha_fin", sa.Date, nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="planeado"),
        sa.Column("color", sa.String(9)),
        _usuario_fk("creado_por"),
        sa.Column("created_at", _ts, nullable=False, server_default=_now),
        sa.Column("updated_at", _ts, nullable=False, server_default=_now),
        sa.CheckConstraint(
            "categoria IN ('seguridad_informacion','nuevo_proyecto','operativo','otro')",
            name="ck_proyectos_categoria",
        ),
        sa.CheckConstraint(
            "estado IN ('planeado','en_curso','pausado','completado','cancelado')",
            name="ck_proyectos_estado",
        ),
        sa.CheckConstraint("fecha_fin >= fecha_inicio", name="ck_proyectos_rango"),
    )

    op.create_table(
        "tareas_recurrentes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text),
        sa.Column("proyecto_id", sa.Integer, sa.ForeignKey("proyectos.id", ondelete="CASCADE")),
        _usuario_fk("responsable_id"),
        sa.Column("prioridad", sa.String(10), nullable=False, server_default="media"),
        sa.Column("frecuencia", sa.String(10), nullable=False),
        sa.Column("dias_semana", ARRAY(sa.SmallInteger)),  # ISO 1=lunes … 7=domingo
        sa.Column("dia_mes", sa.SmallInteger),
        sa.Column("fecha_inicio", sa.Date, nullable=False),
        sa.Column("fecha_fin", sa.Date),
        sa.Column("saltar_festivos", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("generado_hasta", sa.Date),
        _usuario_fk("creado_por"),
        sa.Column("created_at", _ts, nullable=False, server_default=_now),
        sa.Column("updated_at", _ts, nullable=False, server_default=_now),
        sa.CheckConstraint("frecuencia IN ('diaria','semanal','mensual')", name="ck_recurrentes_frecuencia"),
        sa.CheckConstraint("prioridad IN ('baja','media','alta','critica')", name="ck_recurrentes_prioridad"),
        sa.CheckConstraint("dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31", name="ck_recurrentes_dia_mes"),
    )

    op.create_table(
        "tareas_seguimiento",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text),
        sa.Column("proyecto_id", sa.Integer, sa.ForeignKey("proyectos.id", ondelete="CASCADE")),
        sa.Column("recurrente_id", sa.Integer, sa.ForeignKey("tareas_recurrentes.id", ondelete="SET NULL")),
        _usuario_fk("responsable_id"),
        _usuario_fk("creado_por"),
        sa.Column("fecha_programada", sa.Date, nullable=False),
        sa.Column("fecha_limite", sa.Date),
        sa.Column("prioridad", sa.String(10), nullable=False, server_default="media"),
        sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
        sa.Column("esfuerzo_horas", sa.Numeric(6, 2)),
        sa.Column("completada_en", _ts),
        sa.Column("created_at", _ts, nullable=False, server_default=_now),
        sa.Column("updated_at", _ts, nullable=False, server_default=_now),
        sa.CheckConstraint("prioridad IN ('baja','media','alta','critica')", name="ck_tareas_seg_prioridad"),
        sa.CheckConstraint(
            "estado IN ('pendiente','en_progreso','completada','cancelada')", name="ck_tareas_seg_estado"
        ),
        sa.UniqueConstraint("recurrente_id", "fecha_programada", name="uq_tareas_seg_recurrente_fecha"),
    )
    op.create_index("idx_tareas_seg_resp_fecha", "tareas_seguimiento", ["responsable_id", "fecha_programada"])
    op.create_index("idx_tareas_seg_fecha", "tareas_seguimiento", ["fecha_programada"])
    op.create_index("idx_tareas_seg_proyecto", "tareas_seguimiento", ["proyecto_id"])
    op.execute(
        "CREATE INDEX idx_tareas_seg_abiertas ON tareas_seguimiento (fecha_programada) "
        "WHERE estado IN ('pendiente','en_progreso')"
    )

    valores = ", ".join(f"('{rol}', 'seguimiento_tareas')" for rol in ROLES)
    op.execute(f"""
        INSERT INTO rol_paginas (rol, page_key) VALUES {valores}
        ON CONFLICT ON CONSTRAINT uq_rol_paginas_rol_page DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM rol_paginas WHERE page_key = 'seguimiento_tareas'")
    op.drop_table("tareas_seguimiento")
    op.drop_table("tareas_recurrentes")
    op.drop_table("proyectos")
