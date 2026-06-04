"""Initial schema — 38 tablas + 5 vistas

Revision ID: 001
Revises:
Create Date: 2026-06-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Trigger function ─────────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_fecha_modificacion()
        RETURNS TRIGGER AS $$
        BEGIN NEW.fecha_modificacion = CURRENT_TIMESTAMP; RETURN NEW; END;
        $$ LANGUAGE plpgsql
    """)

    # ── 1. usuarios ───────────────────────────────────────────────────────────
    op.create_table("usuarios",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nombre_completo", sa.String(100), nullable=False),
        sa.Column("email", sa.String(100)),
        sa.Column("rol", sa.String(15), nullable=False),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ultimo_acceso", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint("rol IN ('administrador','contabilidad','operaciones','ventas')", name="ck_usuarios_rol"),
    )
    op.create_index("idx_usuarios_username", "usuarios", ["username"])
    op.create_index("idx_usuarios_rol", "usuarios", ["rol"])

    # ── 2. clientes ───────────────────────────────────────────────────────────
    op.create_table("clientes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nombre_empresa", sa.String(150), nullable=False),
        sa.Column("nit", sa.String(20), unique=True, nullable=False),
        sa.Column("contacto_nombre", sa.String(100)),
        sa.Column("contacto_telefono", sa.String(20)),
        sa.Column("contacto_email", sa.String(100)),
        sa.Column("direccion", sa.Text),
        sa.Column("ciudad", sa.String(50)),
        sa.Column("plazo_pago_dias", sa.Integer, server_default="30"),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("notas", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_clientes_nit", "clientes", ["nit"])
    op.create_index("idx_clientes_activo", "clientes", ["activo"])
    op.execute("CREATE TRIGGER trg_clientes_mod BEFORE UPDATE ON clientes FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 3. ciudades  (absorbe ciudad_tipo) ────────────────────────────────────
    op.create_table("ciudades",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("departamento", sa.String(100)),
        sa.Column("codigo", sa.String(10)),
        sa.Column("es_bogota", sa.Boolean, server_default="false"),
        sa.Column("ambito", sa.String(8), server_default="'nacional'"),
        sa.Column("activa", sa.Boolean, server_default="true"),
        sa.CheckConstraint("ambito IN ('bogota','nacional')", name="ck_ciudades_ambito"),
    )
    op.create_index("idx_ciudades_nombre", "ciudades", ["nombre"])
    op.create_index("idx_ciudades_bogota", "ciudades", ["es_bogota"])
    op.create_index("idx_ciudades_ambito", "ciudades", ["ambito"])

    # ── 4. personal ───────────────────────────────────────────────────────────
    op.create_table("personal",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("codigo", sa.CHAR(4), unique=True, nullable=False),
        sa.Column("nombre_completo", sa.String(150), nullable=False),
        sa.Column("identificacion", sa.String(20), unique=True, nullable=False),
        sa.Column("telefono", sa.String(20)),
        sa.Column("email", sa.String(100)),
        sa.Column("tipo_personal", sa.String(20), nullable=False),
        sa.Column("banco", sa.String(100)),
        sa.Column("numero_cuenta", sa.String(50)),
        sa.Column("tipo_cuenta", sa.String(10)),
        sa.Column("dia_pago", sa.Integer, server_default="8"),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_ingreso", sa.Date),
        sa.Column("precio_local", sa.Numeric(10, 0)),
        sa.Column("precio_nacional", sa.Numeric(10, 0)),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_personal IN ('mensajero','alistamiento','conductor','courier_externo','transportadora')", name="ck_personal_tipo"),
        sa.CheckConstraint("tipo_cuenta IN ('ahorros','corriente')", name="ck_personal_cuenta"),
    )
    op.create_index("idx_personal_codigo", "personal", ["codigo"])
    op.create_index("idx_personal_tipo", "personal", ["tipo_personal"])
    op.create_index("idx_personal_activo", "personal", ["activo"])
    op.execute("CREATE TRIGGER trg_personal_mod BEFORE UPDATE ON personal FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 5. precios_cliente  (entrega+devolucion en 1 fila) ────────────────────
    op.create_table("precios_cliente",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("cliente_id", sa.BigInteger, sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo_servicio", sa.String(8), nullable=False),
        sa.Column("ambito", sa.String(8), nullable=False),
        sa.Column("precio_entrega", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("precio_devolucion", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("costo_mensajero_entrega", sa.Numeric(10, 2), server_default="0"),
        sa.Column("costo_mensajero_devolucion", sa.Numeric(10, 2), server_default="0"),
        sa.Column("vigencia_desde", sa.Date, nullable=False),
        sa.Column("vigencia_hasta", sa.Date),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("notas", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_servicio IN ('sobre','paquete')", name="ck_precios_tipo"),
        sa.CheckConstraint("ambito IN ('bogota','nacional')", name="ck_precios_ambito"),
        sa.UniqueConstraint("cliente_id", "tipo_servicio", "ambito", "vigencia_desde", name="uq_precios_cliente"),
    )
    op.create_index("idx_precios_cliente", "precios_cliente", ["cliente_id", "tipo_servicio", "ambito"])
    op.create_index("idx_precios_vigencia", "precios_cliente", ["vigencia_desde"])

    # ── 6. personal_ciudades ─────────────────────────────────────────────────
    op.create_table("personal_ciudades",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ciudad_id", sa.BigInteger, sa.ForeignKey("ciudades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tarifa_entrega", sa.Numeric(10, 2)),
        sa.Column("tarifa_devolucion", sa.Numeric(10, 2)),
        sa.Column("vigencia_desde", sa.Date, nullable=False),
        sa.Column("vigencia_hasta", sa.Date),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.UniqueConstraint("personal_id", "ciudad_id", name="uq_personal_ciudad"),
    )
    op.create_index("idx_personal_ciudades_ciudad", "personal_ciudades", ["ciudad_id"])

    # ── 7. tarifas_servicios ─────────────────────────────────────────────────
    op.create_table("tarifas_servicios",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tipo_servicio", sa.String(25), nullable=False),
        sa.Column("descripcion", sa.String(200)),
        sa.Column("tarifa", sa.Numeric(10, 2), nullable=False),
        sa.Column("vigencia_desde", sa.Date, nullable=False),
        sa.Column("vigencia_hasta", sa.Date),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_servicio IN ('alistamiento_hora','transporte_completo','medio_transporte','pegado_guia')", name="ck_tarifas_tipo"),
    )
    op.create_index("idx_tarifas_tipo", "tarifas_servicios", ["tipo_servicio"])
    op.create_index("idx_tarifas_vigencia", "tarifas_servicios", ["vigencia_desde"])

    # ── 8. ordenes ────────────────────────────────────────────────────────────
    op.create_table("ordenes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("numero_orden", sa.String(50), unique=True, nullable=False),
        sa.Column("cliente_id", sa.BigInteger, sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("ciudad_destino_id", sa.BigInteger, sa.ForeignKey("ciudades.id", ondelete="SET NULL")),
        sa.Column("fecha_recepcion", sa.Date, nullable=False),
        sa.Column("tipo_servicio", sa.String(8), nullable=False),
        sa.Column("cantidad_total", sa.Integer, server_default="0", nullable=False),
        sa.Column("cantidad_recibido", sa.Integer, server_default="0", nullable=False),
        sa.Column("cantidad_en_cajoneras", sa.Integer, server_default="0", nullable=False),
        sa.Column("cantidad_en_lleva", sa.Integer, server_default="0", nullable=False),
        sa.Column("cantidad_entregados", sa.Integer, server_default="0", nullable=False),
        sa.Column("cantidad_devolucion", sa.Integer, server_default="0", nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2)),
        sa.Column("valor_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("costo_mensajero_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("costo_alistamiento_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("costo_pegado_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("costo_transporte_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("costo_flete_total", sa.Numeric(12, 2), server_default="0"),
        sa.Column("estado", sa.String(10), server_default="'activa'"),
        sa.Column("facturado", sa.Boolean, server_default="false"),
        sa.Column("fecha_finalizacion", sa.Date),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_servicio IN ('sobre','paquete')", name="ck_ordenes_tipo"),
        sa.CheckConstraint("estado IN ('activa','finalizada','anulada')", name="ck_ordenes_estado"),
    )
    # Columnas GENERATED no se pueden crear con op.create_table en Alembic; se agregan via DDL
    op.execute("""
        ALTER TABLE ordenes
        ADD COLUMN costo_total NUMERIC(12,2) GENERATED ALWAYS AS (
            COALESCE(costo_mensajero_total,0) + COALESCE(costo_alistamiento_total,0) +
            COALESCE(costo_pegado_total,0) + COALESCE(costo_transporte_total,0) +
            COALESCE(costo_flete_total,0)
        ) STORED,
        ADD COLUMN utilidad_total NUMERIC(12,2) GENERATED ALWAYS AS (
            COALESCE(valor_total,0) - (
                COALESCE(costo_mensajero_total,0) + COALESCE(costo_alistamiento_total,0) +
                COALESCE(costo_pegado_total,0) + COALESCE(costo_transporte_total,0) +
                COALESCE(costo_flete_total,0)
            )
        ) STORED
    """)
    op.create_index("idx_ordenes_cliente", "ordenes", ["cliente_id"])
    op.create_index("idx_ordenes_fecha", "ordenes", ["fecha_recepcion"])
    op.create_index("idx_ordenes_estado", "ordenes", ["estado"])
    op.create_index("idx_ordenes_facturado", "ordenes", ["facturado"])
    op.create_index("idx_ordenes_numero", "ordenes", ["numero_orden"])
    op.create_index("idx_ordenes_ciudad", "ordenes", ["ciudad_destino_id"])
    op.execute("CREATE TRIGGER trg_ordenes_mod BEFORE UPDATE ON ordenes FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 9. orden_personal ─────────────────────────────────────────────────────
    op.create_table("orden_personal",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cantidad_asignada", sa.Integer, nullable=False),
        sa.Column("cantidad_entregada", sa.Integer, server_default="0"),
        sa.Column("cantidad_devolucion", sa.Integer, server_default="0"),
        sa.Column("tarifa_unitaria", sa.Numeric(10, 2)),
        sa.Column("fecha_asignacion", sa.Date),
        sa.Column("observaciones", sa.Text),
    )
    op.execute("""
        ALTER TABLE orden_personal
        ADD COLUMN total_pagar NUMERIC(10,2) GENERATED ALWAYS AS (
            (COALESCE(cantidad_entregada,0) + COALESCE(cantidad_devolucion,0)) * COALESCE(tarifa_unitaria,0)
        ) STORED
    """)
    op.create_index("idx_orden_personal_orden", "orden_personal", ["orden_id"])
    op.create_index("idx_orden_personal_personal", "orden_personal", ["personal_id"])

    # ── 10. seriales_gestion ─────────────────────────────────────────────────
    op.create_table("seriales_gestion",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("serial", sa.String(50), unique=True, nullable=False),
        sa.Column("f_emi", sa.Date),
        sa.Column("f_esc", sa.Date, nullable=False),
        sa.Column("planilla", sa.String(50), nullable=False),
        sa.Column("cod_men", sa.String(4), nullable=False),
        sa.Column("mensajero_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="SET NULL")),
        sa.Column("cliente_id", sa.BigInteger, sa.ForeignKey("clientes.id", ondelete="SET NULL")),
        sa.Column("tipo_gestion", sa.String(10), nullable=False),
        sa.Column("tipo_envio", sa.String(8), server_default="'sobre'"),
        sa.Column("ambito", sa.String(8), server_default="'bogota'"),
        sa.Column("precio_cliente", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("precio_mensajero", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("estado", sa.String(12), server_default="'pendiente'", nullable=False),
        sa.Column("liquidacion_id", sa.BigInteger),
        sa.Column("factura_id", sa.BigInteger),
        sa.Column("origen", sa.String(8), server_default="'scanner'", nullable=False),
        sa.Column("editado_manualmente", sa.Boolean, server_default="false", nullable=False),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("tipo_gestion IN ('Entrega','Devolucion')", name="ck_sg_tipo_gestion"),
        sa.CheckConstraint("tipo_envio IN ('sobre','paquete')", name="ck_sg_tipo_envio"),
        sa.CheckConstraint("ambito IN ('bogota','nacional')", name="ck_sg_ambito"),
        sa.CheckConstraint("estado IN ('pendiente','liquidado','facturado','anulado','en_revision')", name="ck_sg_estado"),
        sa.CheckConstraint("origen IN ('scanner','imile','manual')", name="ck_sg_origen"),
    )
    op.create_index("idx_sg_planilla", "seriales_gestion", ["planilla"])
    op.create_index("idx_sg_cod_men", "seriales_gestion", ["cod_men"])
    op.create_index("idx_sg_f_esc", "seriales_gestion", ["f_esc"])
    op.create_index("idx_sg_f_emi", "seriales_gestion", ["f_emi"])
    op.create_index("idx_sg_estado", "seriales_gestion", ["estado"])
    op.create_index("idx_sg_mensajero", "seriales_gestion", ["mensajero_id"])
    op.create_index("idx_sg_cliente", "seriales_gestion", ["cliente_id"])
    op.create_index("idx_sg_liquidacion", "seriales_gestion", ["liquidacion_id"])
    op.create_index("idx_sg_factura", "seriales_gestion", ["factura_id"])
    op.execute("CREATE TRIGGER trg_sg_mod BEFORE UPDATE ON seriales_gestion FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 11. planillas_revisadas ───────────────────────────────────────────────
    op.create_table("planillas_revisadas",
        sa.Column("lot_esc", sa.String(100), primary_key=True),
        sa.Column("fecha_revision", sa.Date, nullable=False),
    )

    # ── 12. courier_planilla_asignada ─────────────────────────────────────────
    op.create_table("courier_planilla_asignada",
        sa.Column("cod_men", sa.String(20), primary_key=True),
        sa.Column("planilla_asignada", sa.String(100), nullable=False),
        sa.Column("fecha_asignacion", sa.Date, nullable=False),
    )

    # ── 13. mapeo_clientes ────────────────────────────────────────────────────
    op.create_table("mapeo_clientes",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nombre_csv", sa.String(200), unique=True, nullable=False),
        sa.Column("nombre_bd", sa.String(200)),
        sa.Column("cliente_id", sa.BigInteger, sa.ForeignKey("clientes.id", ondelete="SET NULL")),
    )

    # ── 14. mapeo_da ─────────────────────────────────────────────────────────
    op.create_table("mapeo_da",
        sa.Column("nombre_da", sa.String(200), primary_key=True),
        sa.Column("cod_mensajero", sa.String(20), nullable=False),
    )

    # ── 15. registro_horas ────────────────────────────────────────────────────
    op.create_table("registro_horas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="SET NULL")),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("horas_trabajadas", sa.Numeric(5, 2), nullable=False),
        sa.Column("tarifa_hora", sa.Numeric(10, 2), nullable=False),
        sa.Column("tipo_trabajo", sa.String(25), nullable=False),
        sa.Column("aprobado", sa.Boolean, server_default="false"),
        sa.Column("aprobado_por", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_aprobacion", sa.TIMESTAMP(timezone=True)),
        sa.Column("liquidado", sa.Boolean, server_default="false"),
        sa.Column("liquidacion_id", sa.BigInteger),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_trabajo IN ('alistamiento_sobres','alistamiento_paquetes')", name="ck_reg_horas_tipo"),
    )
    op.execute("ALTER TABLE registro_horas ADD COLUMN total NUMERIC(10,2) GENERATED ALWAYS AS (horas_trabajadas * tarifa_hora) STORED")
    op.create_index("idx_reg_horas_personal", "registro_horas", ["personal_id"])
    op.create_index("idx_reg_horas_fecha", "registro_horas", ["fecha"])
    op.create_index("idx_reg_horas_aprobado", "registro_horas", ["aprobado"])
    op.create_index("idx_reg_horas_liquidado", "registro_horas", ["liquidado"])

    # ── 16. registro_labores ──────────────────────────────────────────────────
    op.create_table("registro_labores",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="SET NULL")),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("tipo_labor", sa.String(25), nullable=False),
        sa.Column("cantidad", sa.Integer, nullable=False),
        sa.Column("tarifa_unitaria", sa.Numeric(10, 2), nullable=False),
        sa.Column("aprobado", sa.Boolean, server_default="false"),
        sa.Column("aprobado_por", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_aprobacion", sa.TIMESTAMP(timezone=True)),
        sa.Column("liquidado", sa.Boolean, server_default="false"),
        sa.Column("liquidacion_id", sa.BigInteger),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_labor IN ('pegado_guia','transporte_completo','medio_transporte')", name="ck_reg_labores_tipo"),
    )
    op.execute("ALTER TABLE registro_labores ADD COLUMN total NUMERIC(10,2) GENERATED ALWAYS AS (cantidad * tarifa_unitaria) STORED")
    op.create_index("idx_reg_labores_personal", "registro_labores", ["personal_id"])
    op.create_index("idx_reg_labores_fecha", "registro_labores", ["fecha"])
    op.create_index("idx_reg_labores_tipo", "registro_labores", ["tipo_labor"])
    op.create_index("idx_reg_labores_aprobado", "registro_labores", ["aprobado"])
    op.create_index("idx_reg_labores_liquidado", "registro_labores", ["liquidado"])

    # ── 17. subsidio_transporte ───────────────────────────────────────────────
    op.create_table("subsidio_transporte",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("horas_totales", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("tipo_subsidio", sa.String(25), nullable=False),
        sa.Column("tarifa", sa.Numeric(10, 2), nullable=False),
        sa.Column("origen", sa.String(12), server_default="'automatico'"),
        sa.Column("aprobado", sa.Boolean, server_default="false"),
        sa.Column("aprobado_por", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_aprobacion", sa.TIMESTAMP(timezone=True)),
        sa.Column("liquidado", sa.Boolean, server_default="false"),
        sa.Column("liquidacion_id", sa.BigInteger),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo_subsidio IN ('transporte_completo','medio_transporte')", name="ck_subsidio_tipo"),
        sa.CheckConstraint("origen IN ('automatico','manual','recalculado')", name="ck_subsidio_origen"),
        sa.UniqueConstraint("personal_id", "fecha", name="uq_subsidio_personal_fecha"),
    )
    op.execute("ALTER TABLE subsidio_transporte ADD COLUMN total NUMERIC(10,2) GENERATED ALWAYS AS (tarifa) STORED")
    op.create_index("idx_subsidio_fecha", "subsidio_transporte", ["fecha"])
    op.create_index("idx_subsidio_personal", "subsidio_transporte", ["personal_id"])
    op.create_index("idx_subsidio_aprobado", "subsidio_transporte", ["aprobado"])
    op.create_index("idx_subsidio_liquidado", "subsidio_transporte", ["liquidado"])
    op.execute("CREATE TRIGGER trg_subsidio_mod BEFORE UPDATE ON subsidio_transporte FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 18. liquidaciones ─────────────────────────────────────────────────────
    op.create_table("liquidaciones",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("numero_liquidacion", sa.String(50), unique=True, nullable=False),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id", ondelete="CASCADE"), nullable=False),
        sa.Column("periodo_mes", sa.Integer, nullable=False),
        sa.Column("periodo_anio", sa.Integer, nullable=False),
        sa.Column("fecha_generacion", sa.Date, nullable=False),
        sa.Column("fecha_pago_programada", sa.Date, nullable=False),
        sa.Column("total_entregas", sa.Numeric(12, 2), server_default="0"),
        sa.Column("cantidad_entregas", sa.Integer, server_default="0"),
        sa.Column("total_horas", sa.Numeric(12, 2), server_default="0"),
        sa.Column("cantidad_horas", sa.Numeric(5, 2), server_default="0"),
        sa.Column("total_labores", sa.Numeric(12, 2), server_default="0"),
        sa.Column("cantidad_labores", sa.Integer, server_default="0"),
        sa.Column("bonificaciones", sa.Numeric(12, 2), server_default="0"),
        sa.Column("descuentos", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total_a_pagar", sa.Numeric(12, 2), nullable=False),
        sa.Column("estado", sa.String(10), server_default="'generada'"),
        sa.Column("fecha_pago_real", sa.Date),
        sa.Column("metodo_pago", sa.String(12), server_default="'transferencia'"),
        sa.Column("referencia_pago", sa.String(100)),
        sa.Column("observaciones", sa.Text),
        sa.Column("generado_por", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("aprobado_por", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('generada','aprobada','pagada')", name="ck_liquidaciones_estado"),
        sa.CheckConstraint("metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')", name="ck_liquidaciones_metodo"),
    )
    op.create_index("idx_liquidaciones_personal", "liquidaciones", ["personal_id"])
    op.create_index("idx_liquidaciones_periodo", "liquidaciones", ["periodo_anio", "periodo_mes"])
    op.create_index("idx_liquidaciones_fecha_pago", "liquidaciones", ["fecha_pago_programada"])
    op.create_index("idx_liquidaciones_estado", "liquidaciones", ["estado"])

    # ── 19. facturas_emitidas ─────────────────────────────────────────────────
    op.create_table("facturas_emitidas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("numero_factura", sa.String(50), unique=True, nullable=False),
        sa.Column("cliente_id", sa.BigInteger, sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("fecha_emision", sa.Date, nullable=False),
        sa.Column("fecha_vencimiento", sa.Date, nullable=False),
        sa.Column("periodo_mes", sa.Integer, nullable=False),
        sa.Column("periodo_anio", sa.Integer, nullable=False),
        sa.Column("cantidad_items", sa.Integer, server_default="0"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("descuento", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("saldo_pendiente", sa.Numeric(12, 2), nullable=False),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('pendiente','parcial','pagada','vencida','anulada')", name="ck_fact_emit_estado"),
    )
    op.create_index("idx_fact_emit_numero", "facturas_emitidas", ["numero_factura"])
    op.create_index("idx_fact_emit_cliente", "facturas_emitidas", ["cliente_id"])
    op.create_index("idx_fact_emit_fecha", "facturas_emitidas", ["fecha_emision"])
    op.create_index("idx_fact_emit_vence", "facturas_emitidas", ["fecha_vencimiento"])
    op.create_index("idx_fact_emit_estado", "facturas_emitidas", ["estado"])
    op.create_index("idx_fact_emit_periodo", "facturas_emitidas", ["periodo_anio", "periodo_mes"])
    op.execute("CREATE TRIGGER trg_fact_emit_mod BEFORE UPDATE ON facturas_emitidas FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 20. detalle_facturas_emitidas ─────────────────────────────────────────
    op.create_table("detalle_facturas_emitidas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("factura_id", sa.BigInteger, sa.ForeignKey("facturas_emitidas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="SET NULL")),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("cantidad", sa.Integer, server_default="1", nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("idx_det_emit_factura", "detalle_facturas_emitidas", ["factura_id"])
    op.create_index("idx_det_emit_orden", "detalle_facturas_emitidas", ["orden_id"])

    # ── 21. facturas_recibidas ────────────────────────────────────────────────
    op.create_table("facturas_recibidas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("numero_factura", sa.String(50), nullable=False),
        sa.Column("personal_id", sa.BigInteger, sa.ForeignKey("personal.id"), nullable=False),
        sa.Column("tipo", sa.String(15), nullable=False),
        sa.Column("fecha_recepcion", sa.Date, nullable=False),
        sa.Column("fecha_vencimiento", sa.Date, nullable=False),
        sa.Column("periodo_mes", sa.Integer),
        sa.Column("periodo_anio", sa.Integer),
        sa.Column("cantidad_items", sa.Integer, server_default="0"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("descuento", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("saldo_pendiente", sa.Numeric(12, 2), nullable=False),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("observaciones", sa.Text),
        sa.Column("archivo_adjunto", sa.String(255)),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("fecha_modificacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo IN ('courier','transportadora','materiales','otros')", name="ck_fact_rec_tipo"),
        sa.CheckConstraint("estado IN ('pendiente','parcial','pagada','anulada')", name="ck_fact_rec_estado"),
    )
    op.create_index("idx_fact_rec_numero", "facturas_recibidas", ["numero_factura", "personal_id"])
    op.create_index("idx_fact_rec_personal", "facturas_recibidas", ["personal_id"])
    op.create_index("idx_fact_rec_fecha", "facturas_recibidas", ["fecha_recepcion"])
    op.create_index("idx_fact_rec_vence", "facturas_recibidas", ["fecha_vencimiento"])
    op.create_index("idx_fact_rec_estado", "facturas_recibidas", ["estado"])
    op.create_index("idx_fact_rec_tipo", "facturas_recibidas", ["tipo"])
    op.execute("CREATE TRIGGER trg_fact_rec_mod BEFORE UPDATE ON facturas_recibidas FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion()")

    # ── 22. detalle_facturas_recibidas ────────────────────────────────────────
    op.create_table("detalle_facturas_recibidas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("factura_id", sa.BigInteger, sa.ForeignKey("facturas_recibidas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("cantidad", sa.Integer, server_default="1", nullable=False),
        sa.Column("precio_unitario", sa.Numeric(10, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("idx_det_rec_factura", "detalle_facturas_recibidas", ["factura_id"])

    # ── 23. facturas_transporte ────────────────────────────────────────────────
    op.create_table("facturas_transporte",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("numero_factura", sa.String(100), nullable=False),
        sa.Column("fecha_factura", sa.Date, nullable=False),
        sa.Column("courrier_id", sa.BigInteger, sa.ForeignKey("personal.id"), nullable=False),
        sa.Column("monto_total", sa.Numeric(15, 2), nullable=False),
        sa.Column("total_sobres", sa.Integer, server_default="0"),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_vencimiento", sa.Date),
        sa.Column("monto_pagado", sa.Numeric(15, 2), server_default="0"),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('pendiente','pagada','anulada')", name="ck_fact_transp_estado"),
        sa.UniqueConstraint("numero_factura", "courrier_id", name="uq_fact_transp"),
    )
    op.create_index("idx_fact_transp_courrier", "facturas_transporte", ["courrier_id"])
    op.create_index("idx_fact_transp_fecha", "facturas_transporte", ["fecha_factura"])
    op.create_index("idx_fact_transp_estado", "facturas_transporte", ["estado"])

    # ── 24. detalle_facturas_transporte ───────────────────────────────────────
    op.create_table("detalle_facturas_transporte",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("factura_id", sa.BigInteger, sa.ForeignKey("facturas_transporte.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="SET NULL")),
        sa.Column("cantidad_sobres", sa.Integer, server_default="0"),
        sa.Column("costo_asignado", sa.Numeric(12, 2), server_default="0"),
    )
    op.create_index("idx_det_transp_factura", "detalle_facturas_transporte", ["factura_id"])
    op.create_index("idx_det_transp_orden", "detalle_facturas_transporte", ["orden_id"])

    # ── 25. pagos_recibidos ───────────────────────────────────────────────────
    op.create_table("pagos_recibidos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("factura_id", sa.BigInteger, sa.ForeignKey("facturas_emitidas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fecha_pago", sa.Date, nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_pago", sa.String(12), nullable=False),
        sa.Column("referencia", sa.String(100)),
        sa.Column("observaciones", sa.Text),
        sa.Column("usuario_registro_id", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')", name="ck_pagos_rec_metodo"),
    )
    op.create_index("idx_pagos_rec_factura", "pagos_recibidos", ["factura_id"])
    op.create_index("idx_pagos_rec_fecha", "pagos_recibidos", ["fecha_pago"])

    # ── 26. pagos_realizados ──────────────────────────────────────────────────
    op.create_table("pagos_realizados",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("factura_id", sa.BigInteger, sa.ForeignKey("facturas_recibidas.id", ondelete="CASCADE")),
        sa.Column("liquidacion_id", sa.BigInteger, sa.ForeignKey("liquidaciones.id", ondelete="CASCADE")),
        sa.Column("fecha_pago", sa.Date, nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("metodo_pago", sa.String(12), nullable=False),
        sa.Column("referencia", sa.String(100)),
        sa.Column("observaciones", sa.Text),
        sa.Column("usuario_registro_id", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')", name="ck_pagos_real_metodo"),
    )
    op.create_index("idx_pagos_real_factura", "pagos_realizados", ["factura_id"])
    op.create_index("idx_pagos_real_liquidacion", "pagos_realizados", ["liquidacion_id"])
    op.create_index("idx_pagos_real_fecha", "pagos_realizados", ["fecha_pago"])

    # ── 27. costos_adicionales ────────────────────────────────────────────────
    op.create_table("costos_adicionales",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False),
        sa.Column("ciudad_id", sa.BigInteger, sa.ForeignKey("ciudades.id", ondelete="SET NULL")),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("monto", sa.Numeric(10, 2), nullable=False),
        sa.Column("proveedor", sa.String(150)),
        sa.Column("factura_referencia", sa.String(50)),
        sa.Column("orden_id", sa.BigInteger, sa.ForeignKey("ordenes.id", ondelete="SET NULL")),
        sa.Column("pagado", sa.Boolean, server_default="false"),
        sa.Column("fecha_pago", sa.Date),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo IN ('flete','materiales','otros')", name="ck_costos_tipo"),
    )
    op.create_index("idx_costos_tipo", "costos_adicionales", ["tipo"])
    op.create_index("idx_costos_fecha", "costos_adicionales", ["fecha"])
    op.create_index("idx_costos_pagado", "costos_adicionales", ["pagado"])

    # ── 28. gastos_administrativos ────────────────────────────────────────────
    op.create_table("gastos_administrativos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fecha", sa.Date, nullable=False),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("proveedor", sa.String(150)),
        sa.Column("numero_factura", sa.String(50)),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("fecha_pago", sa.Date),
        sa.Column("observaciones", sa.Text),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('pendiente','pagado')", name="ck_gastos_admin_estado"),
    )
    op.create_index("idx_gastos_admin_fecha", "gastos_administrativos", ["fecha"])
    op.create_index("idx_gastos_admin_categoria", "gastos_administrativos", ["categoria"])
    op.create_index("idx_gastos_admin_estado", "gastos_administrativos", ["estado"])

    # ── 29. reservas_dinero ───────────────────────────────────────────────────
    op.create_table("reservas_dinero",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fecha_creacion_reg", sa.Date, nullable=False),
        sa.Column("fecha_programada", sa.Date),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("estado", sa.String(10), server_default="'activa'"),
        sa.Column("fecha_liberacion", sa.Date),
        sa.Column("observaciones", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('activa','liberada','ejecutada')", name="ck_reservas_estado"),
    )
    op.create_index("idx_reservas_estado", "reservas_dinero", ["estado"])
    op.create_index("idx_reservas_fecha", "reservas_dinero", ["fecha_programada"])

    # ── 30. gastos_fijos_mensuales ────────────────────────────────────────────
    op.create_table("gastos_fijos_mensuales",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("descripcion", sa.String(255), nullable=False),
        sa.Column("monto", sa.Numeric(15, 2), nullable=False),
        sa.Column("dia_pago", sa.Integer, server_default="1"),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("observaciones", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── 31. pagos_gastos_fijos ────────────────────────────────────────────────
    op.create_table("pagos_gastos_fijos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("gasto_fijo_id", sa.BigInteger, sa.ForeignKey("gastos_fijos_mensuales.id"), nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("monto_pagado", sa.Numeric(15, 2), nullable=False),
        sa.Column("fecha_pago", sa.Date, nullable=False),
        sa.Column("observaciones", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("gasto_fijo_id", "mes", "anio", name="uq_pago_gasto_mes"),
    )

    # ── 32. nomina_empleados ──────────────────────────────────────────────────
    op.create_table("nomina_empleados",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("nombre_completo", sa.String(150), nullable=False),
        sa.Column("identificacion", sa.String(20), unique=True),
        sa.Column("cargo", sa.String(100)),
        sa.Column("salario_mensual", sa.Numeric(15, 2), server_default="0", nullable=False),
        sa.Column("tiene_auxilio_transporte", sa.Boolean, server_default="false"),
        sa.Column("auxilio_no_salarial", sa.Numeric(15, 2), server_default="0"),
        sa.Column("fecha_ingreso", sa.Date),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── 33. nomina_provisiones ────────────────────────────────────────────────
    op.create_table("nomina_provisiones",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("empleado_id", sa.BigInteger, sa.ForeignKey("nomina_empleados.id"), nullable=False),
        sa.Column("periodo_mes", sa.Integer, nullable=False),
        sa.Column("periodo_anio", sa.Integer, nullable=False),
        sa.Column("salario_base", sa.Numeric(15, 2)),
        sa.Column("auxilio_transporte", sa.Numeric(15, 2)),
        sa.Column("auxilio_no_salarial", sa.Numeric(15, 2)),
        sa.Column("arl", sa.Numeric(15, 2)),
        sa.Column("eps", sa.Numeric(15, 2)),
        sa.Column("afp", sa.Numeric(15, 2)),
        sa.Column("caja_compensacion", sa.Numeric(15, 2)),
        sa.Column("prima", sa.Numeric(15, 2)),
        sa.Column("cesantias", sa.Numeric(15, 2)),
        sa.Column("int_cesantias", sa.Numeric(15, 2)),
        sa.Column("vacaciones", sa.Numeric(15, 2)),
        sa.Column("fecha_creacion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("empleado_id", "periodo_mes", "periodo_anio", name="uq_nomina_periodo"),
    )

    # ── 34. nomina_parametros ─────────────────────────────────────────────────
    op.create_table("nomina_parametros",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("parametro", sa.String(100), nullable=False),
        sa.Column("valor", sa.Numeric(15, 4), nullable=False),
        sa.Column("descripcion", sa.String(255)),
        sa.Column("vigencia_desde", sa.Date, nullable=False),
        sa.Column("activo", sa.Boolean, server_default="true"),
    )
    op.create_index("idx_nomina_params_activo", "nomina_parametros", ["activo"])

    # ── 35. pagos_operativos_mensuales ────────────────────────────────────────
    op.create_table("pagos_operativos_mensuales",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tipo", sa.String(15), nullable=False),
        sa.Column("periodo_mes", sa.Integer, nullable=False),
        sa.Column("periodo_anio", sa.Integer, nullable=False),
        sa.Column("monto_total", sa.Numeric(15, 2), nullable=False),
        sa.Column("fecha_vencimiento", sa.Date, nullable=False),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("fecha_pago", sa.Date),
        sa.Column("observaciones", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("tipo IN ('mensajeros','alistamiento')", name="ck_pago_op_tipo"),
        sa.CheckConstraint("estado IN ('pendiente','pagado')", name="ck_pago_op_estado"),
        sa.UniqueConstraint("tipo", "periodo_mes", "periodo_anio", name="uq_pago_op_periodo"),
    )

    # ── 36. prefacturas_courier ───────────────────────────────────────────────
    op.create_table("prefacturas_courier",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("cod_mensajero", sa.String(4), nullable=False),
        sa.Column("fecha_generacion", sa.Date, nullable=False),
        sa.Column("periodo_desde", sa.Date),
        sa.Column("periodo_hasta", sa.Date),
        sa.Column("cantidad_planillas", sa.Integer, server_default="0"),
        sa.Column("cantidad_local", sa.Integer, server_default="0"),
        sa.Column("cantidad_nacional", sa.Integer, server_default="0"),
        sa.Column("valor_local", sa.Numeric(15, 2), server_default="0"),
        sa.Column("valor_nacional", sa.Numeric(15, 2), server_default="0"),
        sa.Column("valor_total", sa.Numeric(15, 2), server_default="0"),
        sa.Column("estado", sa.String(10), server_default="'borrador'"),
        sa.Column("notas", sa.Text),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('borrador','aprobada','facturada')", name="ck_prefact_estado"),
    )
    op.create_index("idx_prefact_cod_men", "prefacturas_courier", ["cod_mensajero"])
    op.create_index("idx_prefact_estado", "prefacturas_courier", ["estado"])

    # ── 37. prefactura_planillas ──────────────────────────────────────────────
    op.create_table("prefactura_planillas",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("prefactura_id", sa.BigInteger, sa.ForeignKey("prefacturas_courier.id", ondelete="CASCADE"), nullable=False),
        sa.Column("planilla", sa.String(50), nullable=False),
        sa.Column("fecha_escaner", sa.Date),
        sa.Column("cantidad_local", sa.Integer, server_default="0"),
        sa.Column("cantidad_nacional", sa.Integer, server_default="0"),
        sa.Column("precio_local", sa.Numeric(10, 2), server_default="0"),
        sa.Column("precio_nac", sa.Numeric(10, 2), server_default="0"),
        sa.Column("valor_local", sa.Numeric(12, 2), server_default="0"),
        sa.Column("valor_nac", sa.Numeric(12, 2), server_default="0"),
        sa.Column("valor_total", sa.Numeric(12, 2), server_default="0"),
    )
    op.create_index("idx_prefact_planillas_id", "prefactura_planillas", ["prefactura_id"])

    # ── 38. facturas_courier_cxp ──────────────────────────────────────────────
    op.create_table("facturas_courier_cxp",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("prefactura_id", sa.BigInteger, sa.ForeignKey("prefacturas_courier.id"), nullable=False),
        sa.Column("cod_mensajero", sa.String(4), nullable=False),
        sa.Column("numero_factura", sa.String(100), nullable=False),
        sa.Column("fecha_emision", sa.Date),
        sa.Column("fecha_vencimiento", sa.Date, nullable=False),
        sa.Column("valor_total", sa.Numeric(15, 2), nullable=False),
        sa.Column("estado", sa.String(10), server_default="'pendiente'"),
        sa.Column("notas", sa.Text),
        sa.Column("fecha_pago", sa.Date),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("estado IN ('pendiente','pagada','vencida')", name="ck_cxp_estado"),
    )
    op.create_index("idx_cxp_estado", "facturas_courier_cxp", ["estado"])
    op.create_index("idx_cxp_vencimiento", "facturas_courier_cxp", ["fecha_vencimiento"])

    # ── auditoria ─────────────────────────────────────────────────────────────
    op.create_table("auditoria",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.BigInteger, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("tabla", sa.String(50), nullable=False),
        sa.Column("registro_id", sa.BigInteger),
        sa.Column("accion", sa.String(6), nullable=False),
        sa.Column("datos_anteriores", sa.JSON),
        sa.Column("datos_nuevos", sa.JSON),
        sa.Column("fecha_accion", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ip_address", sa.String(45)),
        sa.CheckConstraint("accion IN ('INSERT','UPDATE','DELETE')", name="ck_auditoria_accion"),
    )
    op.create_index("idx_auditoria_tabla", "auditoria", ["tabla", "registro_id"])
    op.create_index("idx_auditoria_usuario", "auditoria", ["usuario_id"])
    op.create_index("idx_auditoria_fecha", "auditoria", ["fecha_accion"])

    # ── Vistas ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE VIEW vista_estado_ordenes AS
        SELECT o.id, o.numero_orden, c.nombre_empresa AS cliente, ci.nombre AS ciudad_destino,
            o.tipo_servicio, o.fecha_recepcion, o.cantidad_total, o.cantidad_recibido,
            o.cantidad_en_cajoneras, o.cantidad_en_lleva, o.cantidad_entregados, o.cantidad_devolucion,
            (o.cantidad_entregados + o.cantidad_devolucion) AS finalizados,
            CASE WHEN o.cantidad_total > 0
                THEN ROUND((o.cantidad_entregados + o.cantidad_devolucion)::NUMERIC / o.cantidad_total * 100, 2)
                ELSE 0 END AS porcentaje_completado,
            o.valor_total, o.costo_total, o.utilidad_total,
            CASE WHEN o.valor_total > 0
                THEN ROUND(o.utilidad_total / o.valor_total * 100, 2)
                ELSE 0 END AS margen_porcentaje,
            o.estado, o.facturado
        FROM ordenes o
        JOIN clientes c ON o.cliente_id = c.id
        LEFT JOIN ciudades ci ON o.ciudad_destino_id = ci.id
    """)

    op.execute("""
        CREATE VIEW vista_rentabilidad_cliente AS
        SELECT c.id, c.nombre_empresa,
            COUNT(DISTINCT o.id) AS total_ordenes, SUM(o.cantidad_total) AS total_items,
            SUM(o.cantidad_entregados) AS total_entregados, SUM(o.cantidad_devolucion) AS total_devoluciones,
            SUM(o.valor_total) AS ingresos_totales, SUM(o.costo_total) AS costos_totales,
            SUM(o.utilidad_total) AS utilidad_total,
            CASE WHEN SUM(o.valor_total) > 0
                THEN ROUND(SUM(o.utilidad_total) / SUM(o.valor_total) * 100, 2)
                ELSE 0 END AS margen_porcentaje
        FROM clientes c
        LEFT JOIN ordenes o ON c.id = o.cliente_id AND o.estado = 'finalizada'
        GROUP BY c.id, c.nombre_empresa
    """)

    op.execute("""
        CREATE VIEW vista_cuentas_por_cobrar AS
        SELECT fe.id, fe.numero_factura, c.nombre_empresa AS cliente,
            fe.fecha_emision, fe.fecha_vencimiento, fe.total, fe.saldo_pendiente, fe.estado,
            (CURRENT_DATE - fe.fecha_vencimiento) AS dias_vencidos,
            CASE WHEN (CURRENT_DATE - fe.fecha_vencimiento) > 0 THEN 'VENCIDA'
                 WHEN (fe.fecha_vencimiento - CURRENT_DATE) <= 7 THEN 'POR VENCER'
                 ELSE 'VIGENTE' END AS clasificacion
        FROM facturas_emitidas fe
        JOIN clientes c ON fe.cliente_id = c.id
        WHERE fe.estado IN ('pendiente','parcial','vencida')
        ORDER BY fe.fecha_vencimiento
    """)

    op.execute("""
        CREATE VIEW vista_cuentas_por_pagar AS
        SELECT 'factura'::TEXT AS tipo, fr.id, fr.numero_factura AS referencia,
            p.codigo, p.nombre_completo AS acreedor, fr.fecha_vencimiento,
            fr.saldo_pendiente AS monto, fr.estado,
            (fr.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_vencimiento,
            CASE WHEN (CURRENT_DATE - fr.fecha_vencimiento) > 0 THEN 'VENCIDA'
                 WHEN (fr.fecha_vencimiento - CURRENT_DATE) <= 7 THEN 'POR VENCER'
                 ELSE 'VIGENTE' END AS clasificacion
        FROM facturas_recibidas fr JOIN personal p ON fr.personal_id = p.id
        WHERE fr.estado IN ('pendiente','parcial')
        UNION ALL
        SELECT 'liquidacion'::TEXT AS tipo, l.id, l.numero_liquidacion AS referencia,
            p.codigo, p.nombre_completo AS acreedor, l.fecha_pago_programada AS fecha_vencimiento,
            l.total_a_pagar AS monto, l.estado,
            (l.fecha_pago_programada - CURRENT_DATE) AS dias_hasta_vencimiento,
            CASE WHEN (CURRENT_DATE - l.fecha_pago_programada) > 0 THEN 'VENCIDA'
                 WHEN (l.fecha_pago_programada - CURRENT_DATE) <= 7 THEN 'POR VENCER'
                 ELSE 'VIGENTE' END AS clasificacion
        FROM liquidaciones l JOIN personal p ON l.personal_id = p.id
        WHERE l.estado IN ('generada','aprobada')
        ORDER BY fecha_vencimiento
    """)

    op.execute("""
        CREATE VIEW vista_flujo_caja_60dias AS
        SELECT fecha, tipo, descripcion, monto, categoria, dias_hasta_fecha,
            CASE WHEN dias_hasta_fecha < 0 THEN 'VENCIDO'
                 WHEN dias_hasta_fecha <= 7 THEN 'ESTA SEMANA'
                 WHEN dias_hasta_fecha <= 30 THEN 'ESTE MES'
                 ELSE 'PROXIMO MES' END AS periodo
        FROM (
            SELECT fe.fecha_vencimiento AS fecha, 'ingreso'::TEXT AS tipo,
                c.nombre_empresa || ' - ' || fe.numero_factura AS descripcion,
                fe.saldo_pendiente AS monto, 'cliente'::TEXT AS categoria,
                (fe.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_fecha
            FROM facturas_emitidas fe JOIN clientes c ON fe.cliente_id = c.id
            WHERE fe.estado IN ('pendiente','parcial','vencida')
              AND fe.fecha_vencimiento <= CURRENT_DATE + INTERVAL '60 days'
            UNION ALL
            SELECT fr.fecha_vencimiento AS fecha, 'egreso'::TEXT AS tipo,
                p.nombre_completo || ' - ' || fr.numero_factura AS descripcion,
                fr.saldo_pendiente AS monto, fr.tipo AS categoria,
                (fr.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_fecha
            FROM facturas_recibidas fr JOIN personal p ON fr.personal_id = p.id
            WHERE fr.estado IN ('pendiente','parcial')
              AND fr.fecha_vencimiento <= CURRENT_DATE + INTERVAL '60 days'
            UNION ALL
            SELECT l.fecha_pago_programada AS fecha, 'egreso'::TEXT AS tipo,
                p.nombre_completo || ' - ' || l.numero_liquidacion AS descripcion,
                l.total_a_pagar AS monto, p.tipo_personal AS categoria,
                (l.fecha_pago_programada - CURRENT_DATE) AS dias_hasta_fecha
            FROM liquidaciones l JOIN personal p ON l.personal_id = p.id
            WHERE l.estado IN ('generada','aprobada')
              AND l.fecha_pago_programada <= CURRENT_DATE + INTERVAL '60 days'
        ) AS flujo
        ORDER BY fecha, tipo DESC
    """)

    # ── Datos iniciales ────────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO usuarios (username, password_hash, nombre_completo, email, rol)
        VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7RXVdgxEgi',
                'Administrador', 'admin@servilla.co', 'administrador')
    """)
    op.execute("""
        INSERT INTO ciudades (nombre, departamento, codigo, es_bogota, ambito)
        VALUES ('Bogotá D.C.', 'Cundinamarca', 'BOG', true, 'bogota')
    """)
    op.execute("""
        INSERT INTO tarifas_servicios (tipo_servicio, descripcion, tarifa, vigencia_desde) VALUES
        ('alistamiento_hora',   'Hora de alistamiento',   7960.90, '2025-01-01'),
        ('transporte_completo', 'Transporte completo',     8333.33, '2025-01-01'),
        ('medio_transporte',    'Medio transporte',        4166.67, '2025-01-01'),
        ('pegado_guia',         'Pegado de guía',            11.54, '2025-01-01')
    """)


def downgrade() -> None:
    # Vistas
    for view in ["vista_flujo_caja_60dias", "vista_cuentas_por_pagar",
                 "vista_cuentas_por_cobrar", "vista_rentabilidad_cliente", "vista_estado_ordenes"]:
        op.execute(f"DROP VIEW IF EXISTS {view}")

    # Tablas en orden inverso de dependencias
    tables = [
        "auditoria", "facturas_courier_cxp", "prefactura_planillas", "prefacturas_courier",
        "pagos_operativos_mensuales", "nomina_parametros", "nomina_provisiones", "nomina_empleados",
        "pagos_gastos_fijos", "gastos_fijos_mensuales", "reservas_dinero",
        "gastos_administrativos", "costos_adicionales", "pagos_realizados", "pagos_recibidos",
        "detalle_facturas_transporte", "facturas_transporte",
        "detalle_facturas_recibidas", "facturas_recibidas",
        "detalle_facturas_emitidas", "facturas_emitidas",
        "liquidaciones", "subsidio_transporte", "registro_labores", "registro_horas",
        "mapeo_da", "mapeo_clientes", "courier_planilla_asignada", "planillas_revisadas",
        "seriales_gestion", "orden_personal", "ordenes",
        "tarifas_servicios", "personal_ciudades", "precios_cliente",
        "personal", "ciudades", "clientes", "usuarios",
    ]
    for t in tables:
        op.drop_table(t)

    op.execute("DROP FUNCTION IF EXISTS update_fecha_modificacion() CASCADE")
