from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db

router = APIRouter(prefix="/api/flujo", tags=["flujo"])
_auth = Depends(require_role("administrador", "contabilidad"))


@router.get("/")
async def flujo_60dias(db: AsyncSession = Depends(get_db), _=_auth):
    rows = (
        await db.execute(text("SELECT * FROM vista_flujo_caja_60dias"))
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/resumen-mensual")
async def resumen_mensual(
    anio: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    params: dict = {}
    anio_filter = ""
    if anio is not None:
        anio_filter = "AND sg_mes.anio = :anio AND fe_mes.anio = :anio AND ga_mes.anio = :anio"
        params["anio"] = anio

    sql = text("""
        WITH meses AS (
            SELECT DISTINCT
                EXTRACT(YEAR  FROM fecha_emision)::INT AS anio,
                EXTRACT(MONTH FROM fecha_emision)::INT AS mes
            FROM facturas_emitidas
            UNION
            SELECT DISTINCT
                EXTRACT(YEAR  FROM f_esc)::INT,
                EXTRACT(MONTH FROM f_esc)::INT
            FROM seriales_gestion
        ),
        ingresos AS (
            SELECT
                EXTRACT(YEAR  FROM pr.fecha_pago)::INT AS anio,
                EXTRACT(MONTH FROM pr.fecha_pago)::INT AS mes,
                SUM(pr.monto) AS cobrado
            FROM pagos_recibidos pr
            GROUP BY 1, 2
        ),
        facturado AS (
            SELECT
                fe.periodo_anio AS anio,
                fe.periodo_mes  AS mes,
                SUM(fe.total)   AS total_facturado,
                SUM(fe.saldo_pendiente) AS por_cobrar
            FROM facturas_emitidas fe
            GROUP BY 1, 2
        ),
        costos_men AS (
            SELECT
                EXTRACT(YEAR  FROM f_esc)::INT AS anio,
                EXTRACT(MONTH FROM f_esc)::INT AS mes,
                SUM(precio_mensajero) AS costo_mensajero,
                SUM(precio_cliente)   AS ingreso_bruto
            FROM seriales_gestion
            WHERE estado != 'anulado'
            GROUP BY 1, 2
        ),
        gastos_adm AS (
            SELECT
                EXTRACT(YEAR  FROM fecha)::INT AS anio,
                EXTRACT(MONTH FROM fecha)::INT AS mes,
                SUM(monto) AS total_gastos
            FROM gastos_administrativos
            GROUP BY 1, 2
        ),
        nom AS (
            SELECT
                np.periodo_anio AS anio,
                np.periodo_mes  AS mes,
                SUM(
                    COALESCE(np.salario_base, 0) +
                    COALESCE(np.auxilio_transporte, 0) +
                    COALESCE(np.auxilio_no_salarial, 0) +
                    COALESCE(np.arl, 0) +
                    COALESCE(np.eps, 0) +
                    COALESCE(np.afp, 0) +
                    COALESCE(np.caja_compensacion, 0) +
                    COALESCE(np.prima, 0) +
                    COALESCE(np.cesantias, 0) +
                    COALESCE(np.int_cesantias, 0) +
                    COALESCE(np.vacaciones, 0)
                ) AS costo_nomina
            FROM nomina_provisiones np
            GROUP BY 1, 2
        )
        SELECT
            m.anio,
            m.mes,
            COALESCE(f.total_facturado, 0)  AS total_facturado,
            COALESCE(i.cobrado, 0)          AS cobrado,
            COALESCE(f.por_cobrar, 0)       AS por_cobrar,
            COALESCE(cm.ingreso_bruto, 0)   AS ingreso_bruto_seriales,
            COALESCE(cm.costo_mensajero, 0) AS costo_mensajero,
            COALESCE(ga.total_gastos, 0)    AS gastos_admin,
            COALESCE(n.costo_nomina, 0)     AS costo_nomina,
            COALESCE(i.cobrado, 0)
                - COALESCE(cm.costo_mensajero, 0)
                - COALESCE(ga.total_gastos, 0)
                - COALESCE(n.costo_nomina, 0)  AS flujo_neto
        FROM meses m
        LEFT JOIN ingresos   i  ON m.anio = i.anio  AND m.mes = i.mes
        LEFT JOIN facturado  f  ON m.anio = f.anio  AND m.mes = f.mes
        LEFT JOIN costos_men cm ON m.anio = cm.anio AND m.mes = cm.mes
        LEFT JOIN gastos_adm ga ON m.anio = ga.anio AND m.mes = ga.mes
        LEFT JOIN nom        n  ON m.anio = n.anio  AND m.mes = n.mes
        ORDER BY m.anio DESC, m.mes DESC
    """)
    rows = (await db.execute(sql, params)).mappings().all()
    return [
        {
            "anio": r["anio"],
            "mes": r["mes"],
            "total_facturado": float(r["total_facturado"]),
            "cobrado": float(r["cobrado"]),
            "por_cobrar": float(r["por_cobrar"]),
            "ingreso_bruto_seriales": float(r["ingreso_bruto_seriales"]),
            "costo_mensajero": float(r["costo_mensajero"]),
            "gastos_admin": float(r["gastos_admin"]),
            "costo_nomina": float(r["costo_nomina"]),
            "flujo_neto": float(r["flujo_neto"]),
        }
        for r in rows
    ]
