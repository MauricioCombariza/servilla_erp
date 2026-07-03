from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.liquidaciones import Liquidacion
from app.models.personal import Personal
from app.schemas.liquidaciones import (
    GenerarLiquidacionRequest,
    LiquidacionRead,
    LiquidacionUpdate,
    PagarLiquidacionRequest,
    ResumenPendientePago,
)

router = APIRouter(prefix="/api/liquidaciones", tags=["liquidaciones"])
_auth = Depends(require_role("administrador", "contabilidad", "operaciones"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


# ── Resumen pendientes de pago ────────────────────────────────────────────────

@router.get("/pendientes", response_model=list[ResumenPendientePago])
async def pendientes_pago(
    mes: int,
    anio: int,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    sql = text("""
        WITH ya_liq AS (
            SELECT personal_id FROM liquidaciones
            WHERE periodo_mes = :mes AND periodo_anio = :anio
        ),
        seriales AS (
            SELECT p.id AS personal_id, p.codigo, p.nombre_completo, p.tipo_personal,
                   COUNT(sg.id)              AS total_seriales,
                   SUM(sg.precio_mensajero)  AS total_mensajero
            FROM personal p
            JOIN seriales_gestion sg ON sg.cod_men = p.codigo
            WHERE sg.estado = 'pendiente'
              AND EXTRACT(MONTH FROM sg.f_esc) = :mes
              AND EXTRACT(YEAR  FROM sg.f_esc) = :anio
              AND p.tipo_personal = 'mensajero'
            GROUP BY p.id, p.codigo, p.nombre_completo, p.tipo_personal
        ),
        horas AS (
            SELECT personal_id,
                   SUM(horas_trabajadas)              AS total_horas,
                   SUM(horas_trabajadas * tarifa_hora) AS total_horas_monto
            FROM registro_horas
            WHERE EXTRACT(MONTH FROM fecha) = :mes
              AND EXTRACT(YEAR  FROM fecha) = :anio
              AND aprobado = TRUE AND liquidado = FALSE
            GROUP BY personal_id
        ),
        labores AS (
            SELECT personal_id,
                   SUM(cantidad)                   AS total_labores,
                   SUM(cantidad * tarifa_unitaria)  AS total_labores_monto
            FROM registro_labores
            WHERE EXTRACT(MONTH FROM fecha) = :mes
              AND EXTRACT(YEAR  FROM fecha) = :anio
              AND aprobado = TRUE AND liquidado = FALSE
            GROUP BY personal_id
        ),
        subsidio AS (
            -- subsidio_transporte no tiene flujo de aprobación implementado,
            -- por eso no se filtra por aprobado (solo liquidado).
            SELECT personal_id,
                   SUM(tarifa) AS total_subsidio
            FROM subsidio_transporte
            WHERE EXTRACT(MONTH FROM fecha) = :mes
              AND EXTRACT(YEAR  FROM fecha) = :anio
              AND liquidado = FALSE
            GROUP BY personal_id
        )
        SELECT
            COALESCE(s.personal_id, h.personal_id, l.personal_id, sub.personal_id) AS personal_id,
            COALESCE(s.codigo, p2.codigo)                         AS codigo,
            COALESCE(s.nombre_completo, p2.nombre_completo)       AS nombre_completo,
            COALESCE(s.tipo_personal, p2.tipo_personal)           AS tipo_personal,
            COALESCE(s.total_seriales, 0)    AS total_seriales,
            COALESCE(s.total_mensajero, 0)   AS total_mensajero,
            COALESCE(h.total_horas, 0)       AS total_horas,
            COALESCE(h.total_horas_monto, 0) AS total_horas_monto,
            COALESCE(l.total_labores, 0)     AS total_labores,
            COALESCE(l.total_labores_monto, 0) AS total_labores_monto,
            COALESCE(sub.total_subsidio, 0)  AS total_subsidio,
            COALESCE(s.total_mensajero, 0)
              + COALESCE(h.total_horas_monto, 0)
              + COALESCE(l.total_labores_monto, 0)
              + COALESCE(sub.total_subsidio, 0) AS total_pendiente,
            (COALESCE(s.personal_id, h.personal_id, l.personal_id, sub.personal_id) IN (SELECT personal_id FROM ya_liq)) AS ya_liquidado
        FROM seriales s
        FULL OUTER JOIN horas    h   ON s.personal_id = h.personal_id
        FULL OUTER JOIN labores  l   ON COALESCE(s.personal_id, h.personal_id) = l.personal_id
        FULL OUTER JOIN subsidio sub ON COALESCE(s.personal_id, h.personal_id, l.personal_id) = sub.personal_id
        LEFT JOIN personal p2 ON p2.id = COALESCE(s.personal_id, h.personal_id, l.personal_id, sub.personal_id)
        ORDER BY total_pendiente DESC
    """)
    rows = (await db.execute(sql, {"mes": mes, "anio": anio})).mappings().all()
    return [ResumenPendientePago(**dict(r)) for r in rows]


# ── CRUD Liquidaciones ────────────────────────────────────────────────────────

@router.get("/", response_model=list[LiquidacionRead])
async def list_liquidaciones(
    mes: int | None = None,
    anio: int | None = None,
    personal_id: int | None = None,
    estado: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(Liquidacion).order_by(
        Liquidacion.periodo_anio.desc(),
        Liquidacion.periodo_mes.desc(),
        Liquidacion.fecha_generacion.desc(),
    )
    if mes is not None:
        q = q.where(Liquidacion.periodo_mes == mes)
    if anio is not None:
        q = q.where(Liquidacion.periodo_anio == anio)
    if personal_id is not None:
        q = q.where(Liquidacion.personal_id == personal_id)
    if estado:
        q = q.where(Liquidacion.estado == estado)
    return (await db.execute(q)).scalars().all()


@router.post("/generar", response_model=LiquidacionRead, status_code=status.HTTP_201_CREATED)
async def generar_liquidacion(
    body: GenerarLiquidacionRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    # Verificar que no exista ya para este personal/período
    exists = await db.execute(
        select(Liquidacion).where(
            Liquidacion.personal_id == body.personal_id,
            Liquidacion.periodo_mes == body.periodo_mes,
            Liquidacion.periodo_anio == body.periodo_anio,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Ya existe una liquidación para este mensajero en este período",
        )

    # Obtener código del personal para cruzar con seriales
    personal = (await db.execute(
        select(Personal).where(Personal.id == body.personal_id)
    )).scalar_one_or_none()
    if personal is None:
        raise HTTPException(status_code=404, detail="Personal no encontrado")

    # Calcular totales desde seriales_gestion
    sql_ser = text("""
        SELECT COUNT(*) AS cant, COALESCE(SUM(precio_mensajero), 0) AS total
        FROM seriales_gestion
        WHERE cod_men = :codigo AND estado = 'pendiente'
          AND EXTRACT(MONTH FROM f_esc) = :mes
          AND EXTRACT(YEAR  FROM f_esc) = :anio
    """)
    r_ser = (await db.execute(sql_ser, {
        "codigo": personal.codigo, "mes": body.periodo_mes, "anio": body.periodo_anio
    })).mappings().one()

    # Totales de horas
    sql_h = text("""
        SELECT COUNT(*) AS cant,
               COALESCE(SUM(horas_trabajadas), 0) AS horas,
               COALESCE(SUM(horas_trabajadas * tarifa_hora), 0) AS monto
        FROM registro_horas
        WHERE personal_id = :pid AND aprobado = TRUE AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes
          AND EXTRACT(YEAR  FROM fecha) = :anio
    """)
    r_h = (await db.execute(sql_h, {
        "pid": body.personal_id, "mes": body.periodo_mes, "anio": body.periodo_anio
    })).mappings().one()

    # Totales de labores
    sql_l = text("""
        SELECT COUNT(*) AS cant,
               COALESCE(SUM(cantidad * tarifa_unitaria), 0) AS monto
        FROM registro_labores
        WHERE personal_id = :pid AND aprobado = TRUE AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes
          AND EXTRACT(YEAR  FROM fecha) = :anio
    """)
    r_l = (await db.execute(sql_l, {
        "pid": body.personal_id, "mes": body.periodo_mes, "anio": body.periodo_anio
    })).mappings().one()

    # Total de subsidio de transporte (sin filtrar por aprobado — ver nota en pendientes_pago)
    sql_sub = text("""
        SELECT COALESCE(SUM(tarifa), 0) AS monto
        FROM subsidio_transporte
        WHERE personal_id = :pid AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes
          AND EXTRACT(YEAR  FROM fecha) = :anio
    """)
    r_sub = (await db.execute(sql_sub, {
        "pid": body.personal_id, "mes": body.periodo_mes, "anio": body.periodo_anio
    })).mappings().one()

    total = (
        float(r_ser["total"]) + float(r_h["monto"]) + float(r_l["monto"]) + float(r_sub["monto"])
        + body.bonificaciones - body.descuentos
    )

    num = f"LIQ-{body.periodo_anio}{body.periodo_mes:02d}-{personal.codigo}"
    liq = Liquidacion(
        numero_liquidacion=num,
        personal_id=body.personal_id,
        periodo_mes=body.periodo_mes,
        periodo_anio=body.periodo_anio,
        fecha_generacion=date.today(),
        fecha_pago_programada=body.fecha_pago_programada,
        total_entregas=float(r_ser["total"]),
        cantidad_entregas=int(r_ser["cant"]),
        total_horas=float(r_h["monto"]),
        cantidad_horas=float(r_h["horas"]),
        total_labores=float(r_l["monto"]),
        cantidad_labores=int(r_l["cant"]),
        total_subsidio=float(r_sub["monto"]),
        bonificaciones=body.bonificaciones,
        descuentos=body.descuentos,
        total_a_pagar=round(total, 2),
        estado="generada",
        observaciones=body.observaciones,
    )
    db.add(liq)

    await db.flush()

    # Actualizar liquidacion_id en seriales y estado en horas/labores
    await db.execute(text("""
        UPDATE seriales_gestion
        SET estado = 'liquidado', liquidacion_id = :lid
        WHERE cod_men = :codigo AND estado IN ('pendiente','liquidado')
          AND EXTRACT(MONTH FROM f_esc) = :mes
          AND EXTRACT(YEAR  FROM f_esc) = :anio
    """), {"lid": liq.id, "codigo": personal.codigo,
           "mes": body.periodo_mes, "anio": body.periodo_anio})

    await db.execute(text("""
        UPDATE registro_horas SET liquidado = TRUE, liquidacion_id = :lid
        WHERE personal_id = :pid AND aprobado = TRUE AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes AND EXTRACT(YEAR FROM fecha) = :anio
    """), {"lid": liq.id, "pid": body.personal_id,
           "mes": body.periodo_mes, "anio": body.periodo_anio})

    await db.execute(text("""
        UPDATE registro_labores SET liquidado = TRUE, liquidacion_id = :lid
        WHERE personal_id = :pid AND aprobado = TRUE AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes AND EXTRACT(YEAR FROM fecha) = :anio
    """), {"lid": liq.id, "pid": body.personal_id,
           "mes": body.periodo_mes, "anio": body.periodo_anio})

    await db.execute(text("""
        UPDATE subsidio_transporte SET liquidado = TRUE, liquidacion_id = :lid
        WHERE personal_id = :pid AND liquidado = FALSE
          AND EXTRACT(MONTH FROM fecha) = :mes AND EXTRACT(YEAR FROM fecha) = :anio
    """), {"lid": liq.id, "pid": body.personal_id,
           "mes": body.periodo_mes, "anio": body.periodo_anio})

    await db.commit()
    await db.refresh(liq)
    return liq


@router.put("/{liq_id}", response_model=LiquidacionRead)
async def update_liquidacion(
    liq_id: int, body: LiquidacionUpdate,
    db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    liq = (await db.execute(select(Liquidacion).where(Liquidacion.id == liq_id))).scalar_one_or_none()
    if liq is None:
        raise HTTPException(status_code=404, detail="Liquidación no encontrada")
    if liq.estado == "pagada":
        raise HTTPException(status_code=400, detail="No se puede editar una liquidación pagada")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(liq, field, val)
    # Recalcular total
    liq.total_a_pagar = round(
        liq.total_entregas + liq.total_horas + liq.total_labores + liq.total_subsidio
        + liq.bonificaciones - liq.descuentos, 2
    )
    await db.commit()
    await db.refresh(liq)
    return liq


@router.post("/{liq_id}/aprobar", response_model=LiquidacionRead)
async def aprobar_liquidacion(
    liq_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    liq = (await db.execute(select(Liquidacion).where(Liquidacion.id == liq_id))).scalar_one_or_none()
    if liq is None:
        raise HTTPException(status_code=404, detail="Liquidación no encontrada")
    liq.estado = "aprobada"
    await db.commit()
    await db.refresh(liq)
    return liq


@router.post("/{liq_id}/pagar", response_model=LiquidacionRead)
async def pagar_liquidacion(
    liq_id: int, body: PagarLiquidacionRequest,
    db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    liq = (await db.execute(select(Liquidacion).where(Liquidacion.id == liq_id))).scalar_one_or_none()
    if liq is None:
        raise HTTPException(status_code=404, detail="Liquidación no encontrada")
    if liq.estado == "pagada":
        raise HTTPException(status_code=400, detail="Ya está pagada")
    liq.estado = "pagada"
    liq.fecha_pago_real = body.fecha_pago_real
    liq.metodo_pago = body.metodo_pago
    liq.referencia_pago = body.referencia_pago
    if body.observaciones:
        liq.observaciones = body.observaciones
    await db.commit()
    await db.refresh(liq)
    return liq


@router.delete("/{liq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_liquidacion(
    liq_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin,
):
    liq = (await db.execute(select(Liquidacion).where(Liquidacion.id == liq_id))).scalar_one_or_none()
    if liq is None:
        raise HTTPException(status_code=404, detail="Liquidación no encontrada")
    if liq.estado == "pagada":
        raise HTTPException(status_code=400, detail="No se puede eliminar una liquidación pagada")
    # Revertir seriales a pendiente
    await db.execute(text("""
        UPDATE seriales_gestion SET estado = 'pendiente', liquidacion_id = NULL
        WHERE liquidacion_id = :lid
    """), {"lid": liq_id})
    await db.execute(text("""
        UPDATE registro_horas SET liquidado = FALSE, liquidacion_id = NULL
        WHERE liquidacion_id = :lid
    """), {"lid": liq_id})
    await db.execute(text("""
        UPDATE registro_labores SET liquidado = FALSE, liquidacion_id = NULL
        WHERE liquidacion_id = :lid
    """), {"lid": liq_id})
    await db.execute(text("""
        UPDATE subsidio_transporte SET liquidado = FALSE, liquidacion_id = NULL
        WHERE liquidacion_id = :lid
    """), {"lid": liq_id})
    await db.delete(liq)
    await db.commit()
