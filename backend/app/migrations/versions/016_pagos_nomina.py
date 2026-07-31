"""Add pagos_nomina table and wire it into vista_cuentas_por_pagar

Permite registrar el pago de un periodo de nomina (mes/anio) sin modificar
las filas de costeo en nomina_provisiones, siguiendo el mismo patron que
pagos_gastos_fijos. Una vez registrado el pago del periodo en curso, la
vista deja de mostrar la nomina como cuenta por pagar pendiente.

Revision ID: 016
Revises: 015
Create Date: 2026-07-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_VIEW = """
CREATE VIEW vista_cuentas_por_pagar AS
SELECT
    base.tipo,
    base.id,
    base.referencia,
    base.codigo,
    base.acreedor,
    base.fecha_vencimiento,
    base.monto,
    base.estado,
    (base.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_vencimiento,
    CASE WHEN base.fecha_vencimiento < CURRENT_DATE THEN 'VENCIDA'
         WHEN (base.fecha_vencimiento - CURRENT_DATE) <= 7 THEN 'POR VENCER'
         ELSE 'VIGENTE' END AS clasificacion
FROM (
    -- 1. Facturas recibidas de proveedores/personal
    SELECT 'factura'::TEXT AS tipo, fr.id, fr.numero_factura AS referencia,
        p.codigo, p.nombre_completo AS acreedor, fr.fecha_vencimiento,
        fr.saldo_pendiente AS monto, fr.estado
    FROM facturas_recibidas fr JOIN personal p ON fr.personal_id = p.id
    WHERE fr.estado IN ('pendiente','parcial')

    UNION ALL

    -- 2. Liquidaciones de mensajeros / personal interno
    SELECT 'liquidacion'::TEXT AS tipo, l.id, l.numero_liquidacion AS referencia,
        p.codigo, p.nombre_completo AS acreedor,
        l.fecha_pago_programada AS fecha_vencimiento,
        l.total_a_pagar AS monto, l.estado
    FROM liquidaciones l JOIN personal p ON l.personal_id = p.id
    WHERE l.estado IN ('generada','aprobada')

    UNION ALL

    -- 3. Pagos ciudades: CxP a couriers externos (facturas_courier_cxp)
    SELECT 'ciudades'::TEXT AS tipo, fc.id, fc.numero_factura AS referencia,
        fc.cod_mensajero AS codigo,
        COALESCE(p.nombre_completo, fc.cod_mensajero) AS acreedor,
        fc.fecha_vencimiento, fc.valor_total AS monto, fc.estado
    FROM facturas_courier_cxp fc
    LEFT JOIN personal p ON p.codigo = fc.cod_mensajero
    WHERE fc.estado IN ('pendiente','vencida')

    UNION ALL

    -- 4. Transporte: fletes de couriers/transportadoras (saldo pendiente)
    SELECT 'transporte'::TEXT AS tipo, ft.id, ft.numero_factura AS referencia,
        p.codigo, p.nombre_completo AS acreedor,
        COALESCE(ft.fecha_vencimiento, ft.fecha_factura) AS fecha_vencimiento,
        (ft.monto_total - ft.monto_pagado) AS monto, ft.estado
    FROM facturas_transporte ft JOIN personal p ON p.id = ft.courrier_id
    WHERE ft.estado = 'pendiente' AND (ft.monto_total - ft.monto_pagado) > 0

    UNION ALL

    -- 5. Gastos administrativos / servicios pendientes
    SELECT 'gasto'::TEXT AS tipo, g.id,
        COALESCE(g.numero_factura, 'GA-' || g.id) AS referencia,
        NULL::VARCHAR AS codigo,
        COALESCE(g.proveedor, g.descripcion) AS acreedor,
        g.fecha AS fecha_vencimiento, g.monto, g.estado
    FROM gastos_administrativos g
    WHERE g.estado = 'pendiente'

    UNION ALL

    -- 6. Gastos fijos mensuales no pagados en el mes en curso
    SELECT 'gasto_fijo'::TEXT AS tipo, gf.id,
        ('GF-' || gf.id) AS referencia,
        NULL::VARCHAR AS codigo,
        gf.descripcion AS acreedor,
        make_date(
            EXTRACT(YEAR FROM CURRENT_DATE)::int,
            EXTRACT(MONTH FROM CURRENT_DATE)::int,
            LEAST(gf.dia_pago, 28)
        ) AS fecha_vencimiento,
        gf.monto, 'pendiente'::TEXT AS estado
    FROM gastos_fijos_mensuales gf
    LEFT JOIN pagos_gastos_fijos pg
        ON pg.gasto_fijo_id = gf.id
       AND pg.mes = EXTRACT(MONTH FROM CURRENT_DATE)::int
       AND pg.anio = EXTRACT(YEAR FROM CURRENT_DATE)::int
    WHERE gf.activo AND pg.id IS NULL

    UNION ALL

    -- 7. Nomina: una fila agregada con el costo laboral del periodo en curso
    SELECT 'nomina'::TEXT AS tipo,
        (np.periodo_anio * 100 + np.periodo_mes) AS id,
        ('NOM-' || np.periodo_anio || LPAD(np.periodo_mes::text, 2, '0')) AS referencia,
        NULL::VARCHAR AS codigo,
        ('Nomina ' || np.periodo_mes || '/' || np.periodo_anio) AS acreedor,
        (date_trunc('MONTH', CURRENT_DATE) + INTERVAL '1 MONTH - 1 day')::date AS fecha_vencimiento,
        SUM(
            COALESCE(np.salario_base, 0) + COALESCE(np.auxilio_transporte, 0)
            + COALESCE(np.auxilio_no_salarial, 0) + COALESCE(np.arl, 0)
            + COALESCE(np.eps, 0) + COALESCE(np.afp, 0)
            + COALESCE(np.caja_compensacion, 0) + COALESCE(np.prima, 0)
            + COALESCE(np.cesantias, 0) + COALESCE(np.int_cesantias, 0)
            + COALESCE(np.vacaciones, 0)
        ) AS monto,
        'pendiente'::TEXT AS estado
    FROM nomina_provisiones np
    WHERE np.periodo_mes = EXTRACT(MONTH FROM CURRENT_DATE)::int
      AND np.periodo_anio = EXTRACT(YEAR FROM CURRENT_DATE)::int
    GROUP BY np.periodo_mes, np.periodo_anio
    HAVING SUM(
        COALESCE(np.salario_base, 0) + COALESCE(np.auxilio_transporte, 0)
        + COALESCE(np.auxilio_no_salarial, 0) + COALESCE(np.arl, 0)
        + COALESCE(np.eps, 0) + COALESCE(np.afp, 0)
        + COALESCE(np.caja_compensacion, 0) + COALESCE(np.prima, 0)
        + COALESCE(np.cesantias, 0) + COALESCE(np.int_cesantias, 0)
        + COALESCE(np.vacaciones, 0)
    ) > 0
) AS base
ORDER BY base.fecha_vencimiento
"""


_NEW_VIEW = """
CREATE VIEW vista_cuentas_por_pagar AS
SELECT
    base.tipo,
    base.id,
    base.referencia,
    base.codigo,
    base.acreedor,
    base.fecha_vencimiento,
    base.monto,
    base.estado,
    (base.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_vencimiento,
    CASE WHEN base.fecha_vencimiento < CURRENT_DATE THEN 'VENCIDA'
         WHEN (base.fecha_vencimiento - CURRENT_DATE) <= 7 THEN 'POR VENCER'
         ELSE 'VIGENTE' END AS clasificacion
FROM (
    -- 1. Facturas recibidas de proveedores/personal
    SELECT 'factura'::TEXT AS tipo, fr.id, fr.numero_factura AS referencia,
        p.codigo, p.nombre_completo AS acreedor, fr.fecha_vencimiento,
        fr.saldo_pendiente AS monto, fr.estado
    FROM facturas_recibidas fr JOIN personal p ON fr.personal_id = p.id
    WHERE fr.estado IN ('pendiente','parcial')

    UNION ALL

    -- 2. Liquidaciones de mensajeros / personal interno
    SELECT 'liquidacion'::TEXT AS tipo, l.id, l.numero_liquidacion AS referencia,
        p.codigo, p.nombre_completo AS acreedor,
        l.fecha_pago_programada AS fecha_vencimiento,
        l.total_a_pagar AS monto, l.estado
    FROM liquidaciones l JOIN personal p ON l.personal_id = p.id
    WHERE l.estado IN ('generada','aprobada')

    UNION ALL

    -- 3. Pagos ciudades: CxP a couriers externos (facturas_courier_cxp)
    SELECT 'ciudades'::TEXT AS tipo, fc.id, fc.numero_factura AS referencia,
        fc.cod_mensajero AS codigo,
        COALESCE(p.nombre_completo, fc.cod_mensajero) AS acreedor,
        fc.fecha_vencimiento, fc.valor_total AS monto, fc.estado
    FROM facturas_courier_cxp fc
    LEFT JOIN personal p ON p.codigo = fc.cod_mensajero
    WHERE fc.estado IN ('pendiente','vencida')

    UNION ALL

    -- 4. Transporte: fletes de couriers/transportadoras (saldo pendiente)
    SELECT 'transporte'::TEXT AS tipo, ft.id, ft.numero_factura AS referencia,
        p.codigo, p.nombre_completo AS acreedor,
        COALESCE(ft.fecha_vencimiento, ft.fecha_factura) AS fecha_vencimiento,
        (ft.monto_total - ft.monto_pagado) AS monto, ft.estado
    FROM facturas_transporte ft JOIN personal p ON p.id = ft.courrier_id
    WHERE ft.estado = 'pendiente' AND (ft.monto_total - ft.monto_pagado) > 0

    UNION ALL

    -- 5. Gastos administrativos / servicios pendientes
    SELECT 'gasto'::TEXT AS tipo, g.id,
        COALESCE(g.numero_factura, 'GA-' || g.id) AS referencia,
        NULL::VARCHAR AS codigo,
        COALESCE(g.proveedor, g.descripcion) AS acreedor,
        g.fecha AS fecha_vencimiento, g.monto, g.estado
    FROM gastos_administrativos g
    WHERE g.estado = 'pendiente'

    UNION ALL

    -- 6. Gastos fijos mensuales no pagados en el mes en curso
    SELECT 'gasto_fijo'::TEXT AS tipo, gf.id,
        ('GF-' || gf.id) AS referencia,
        NULL::VARCHAR AS codigo,
        gf.descripcion AS acreedor,
        make_date(
            EXTRACT(YEAR FROM CURRENT_DATE)::int,
            EXTRACT(MONTH FROM CURRENT_DATE)::int,
            LEAST(gf.dia_pago, 28)
        ) AS fecha_vencimiento,
        gf.monto, 'pendiente'::TEXT AS estado
    FROM gastos_fijos_mensuales gf
    LEFT JOIN pagos_gastos_fijos pg
        ON pg.gasto_fijo_id = gf.id
       AND pg.mes = EXTRACT(MONTH FROM CURRENT_DATE)::int
       AND pg.anio = EXTRACT(YEAR FROM CURRENT_DATE)::int
    WHERE gf.activo AND pg.id IS NULL

    UNION ALL

    -- 7. Nomina: una fila agregada con el costo laboral del periodo en curso,
    --    excluida si ya existe un pago registrado en pagos_nomina para ese periodo.
    SELECT 'nomina'::TEXT AS tipo,
        (np.periodo_anio * 100 + np.periodo_mes) AS id,
        ('NOM-' || np.periodo_anio || LPAD(np.periodo_mes::text, 2, '0')) AS referencia,
        NULL::VARCHAR AS codigo,
        ('Nomina ' || np.periodo_mes || '/' || np.periodo_anio) AS acreedor,
        (date_trunc('MONTH', CURRENT_DATE) + INTERVAL '1 MONTH - 1 day')::date AS fecha_vencimiento,
        SUM(
            COALESCE(np.salario_base, 0) + COALESCE(np.auxilio_transporte, 0)
            + COALESCE(np.auxilio_no_salarial, 0) + COALESCE(np.arl, 0)
            + COALESCE(np.eps, 0) + COALESCE(np.afp, 0)
            + COALESCE(np.caja_compensacion, 0) + COALESCE(np.prima, 0)
            + COALESCE(np.cesantias, 0) + COALESCE(np.int_cesantias, 0)
            + COALESCE(np.vacaciones, 0)
        ) AS monto,
        'pendiente'::TEXT AS estado
    FROM nomina_provisiones np
    LEFT JOIN pagos_nomina pn
        ON pn.periodo_mes = np.periodo_mes
       AND pn.periodo_anio = np.periodo_anio
    WHERE np.periodo_mes = EXTRACT(MONTH FROM CURRENT_DATE)::int
      AND np.periodo_anio = EXTRACT(YEAR FROM CURRENT_DATE)::int
      AND pn.id IS NULL
    GROUP BY np.periodo_mes, np.periodo_anio
    HAVING SUM(
        COALESCE(np.salario_base, 0) + COALESCE(np.auxilio_transporte, 0)
        + COALESCE(np.auxilio_no_salarial, 0) + COALESCE(np.arl, 0)
        + COALESCE(np.eps, 0) + COALESCE(np.afp, 0)
        + COALESCE(np.caja_compensacion, 0) + COALESCE(np.prima, 0)
        + COALESCE(np.cesantias, 0) + COALESCE(np.int_cesantias, 0)
        + COALESCE(np.vacaciones, 0)
    ) > 0
) AS base
ORDER BY base.fecha_vencimiento
"""


def upgrade() -> None:
    op.create_table(
        "pagos_nomina",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("periodo_mes", sa.Integer(), nullable=False),
        sa.Column("periodo_anio", sa.Integer(), nullable=False),
        sa.Column("monto_pagado", sa.Numeric(15, 2), nullable=False),
        sa.Column("fecha_pago", sa.Date(), nullable=False),
        sa.Column("observaciones", sa.String(255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("periodo_mes", "periodo_anio", name="uq_pagos_nomina_periodo"),
    )
    op.execute("DROP VIEW IF EXISTS vista_cuentas_por_pagar")
    op.execute(_NEW_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vista_cuentas_por_pagar")
    op.execute(_OLD_VIEW)
    op.drop_table("pagos_nomina")
