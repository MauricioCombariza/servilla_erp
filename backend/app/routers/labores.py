from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.labores import RegistroHoras, RegistroLabores
from app.schemas.labores import (
    RegistroHorasBulkCreate,
    RegistroHorasCreate, RegistroHorasRead, RegistroHorasUpdate,
    RegistroLaboresCreate, RegistroLaboresRead, RegistroLaboresUpdate,
    ResumenLabores, ResumenDiario,
)

router = APIRouter(prefix="/api/labores", tags=["labores"])
_auth = Depends(require_role("administrador", "operaciones", "contabilidad"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


# ── Helpers internos ──────────────────────────────────────────────────────────

async def _recalcular_costos_ordenes(db: AsyncSession, orden_ids: set[int]) -> None:
    for oid in orden_ids:
        res_h = await db.execute(text("""
            SELECT COALESCE(SUM(CASE WHEN tipo_trabajo IN ('alistamiento_sobres','alistamiento_paquetes')
                                     THEN total END), 0) AS alist
            FROM registro_horas WHERE orden_id = :oid
        """), {"oid": oid})
        costo_alist = res_h.scalar()

        res_l = await db.execute(text("""
            SELECT
              COALESCE(SUM(CASE WHEN tipo_labor = 'pegado_guia' THEN total END), 0) AS peg,
              COALESCE(SUM(CASE WHEN tipo_labor IN ('transporte_completo','medio_transporte')
                               THEN total END), 0) AS transp
            FROM registro_labores WHERE orden_id = :oid
        """), {"oid": oid})
        row = res_l.one()

        await db.execute(text("""
            UPDATE ordenes SET
                costo_alistamiento_total = :alist,
                costo_pegado_total       = :peg,
                costo_transporte_total   = :transp
            WHERE id = :oid
        """), {"alist": costo_alist, "peg": row.peg, "transp": row.transp, "oid": oid})


async def _upsert_subsidio_transporte(db: AsyncSession, personal_id: int, fecha) -> None:
    res = await db.execute(text("""
        SELECT COALESCE(SUM(horas_trabajadas), 0)
        FROM registro_horas WHERE personal_id = :pid AND fecha = :fecha
    """), {"pid": personal_id, "fecha": fecha})
    horas = float(res.scalar())
    if horas <= 0:
        return

    tipo = 'transporte_completo' if horas >= 5.0 else 'medio_transporte'

    tr = await db.execute(text("""
        SELECT tarifa FROM tarifas_servicios
        WHERE tipo_servicio = :tipo AND activo = TRUE
        ORDER BY vigencia_desde DESC LIMIT 1
    """), {"tipo": tipo})
    tarifa = float(tr.scalar() or 0)

    await db.execute(text("""
        INSERT INTO subsidio_transporte (personal_id, fecha, horas_totales, tipo_subsidio, tarifa, origen)
        VALUES (:pid, :fecha, :horas, :tipo, :tarifa, 'automatico')
        ON CONFLICT (personal_id, fecha) DO UPDATE SET
            horas_totales = EXCLUDED.horas_totales,
            tipo_subsidio = EXCLUDED.tipo_subsidio,
            tarifa        = EXCLUDED.tarifa,
            origen        = 'automatico'
        WHERE subsidio_transporte.liquidado = FALSE
    """), {"pid": personal_id, "fecha": fecha, "horas": horas, "tipo": tipo, "tarifa": tarifa})


# ── Tarifas ───────────────────────────────────────────────────────────────────

@router.get("/tarifas/{tipo_servicio}")
async def get_tarifa(tipo_servicio: str, db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(text("""
        SELECT tarifa FROM tarifas_servicios
        WHERE tipo_servicio = :tipo AND activo = TRUE
        ORDER BY vigencia_desde DESC LIMIT 1
    """), {"tipo": tipo_servicio})
    tarifa = result.scalar_one_or_none()
    if tarifa is None:
        raise HTTPException(status_code=404, detail="Tarifa no encontrada")
    return {"tipo_servicio": tipo_servicio, "tarifa": float(tarifa)}


# ── Registro de horas ─────────────────────────────────────────────────────────

_HORAS_ENRICH_SQL = """
    SELECT
        rh.*,
        p.nombre_completo AS personal_nombre,
        o.numero_orden    AS orden_numero
    FROM registro_horas rh
    JOIN personal p ON p.id = rh.personal_id
    LEFT JOIN ordenes o ON o.id = rh.orden_id
    WHERE 1=1
"""


@router.get("/horas", response_model=list[RegistroHorasRead])
async def list_horas(
    personal_id: int | None = None,
    mes: int | None = None,
    anio: int | None = None,
    aprobado: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    filters = []
    params: dict = {}
    if personal_id is not None:
        filters.append("AND rh.personal_id = :personal_id")
        params["personal_id"] = personal_id
    if mes is not None:
        filters.append("AND EXTRACT(MONTH FROM rh.fecha) = :mes")
        params["mes"] = mes
    if anio is not None:
        filters.append("AND EXTRACT(YEAR FROM rh.fecha) = :anio")
        params["anio"] = anio
    if aprobado is not None:
        filters.append("AND rh.aprobado = :aprobado")
        params["aprobado"] = aprobado

    sql = text(_HORAS_ENRICH_SQL + " ".join(filters) + " ORDER BY rh.fecha DESC")
    rows = (await db.execute(sql, params)).mappings().all()
    return [RegistroHorasRead(**dict(r)) for r in rows]


@router.post("/horas", response_model=RegistroHorasRead, status_code=status.HTTP_201_CREATED)
async def create_hora(body: RegistroHorasCreate, db: AsyncSession = Depends(get_db), _=_auth):
    r = RegistroHoras(**body.model_dump())
    db.add(r)
    await db.flush()
    if r.orden_id:
        await _recalcular_costos_ordenes(db, {r.orden_id})
    await _upsert_subsidio_transporte(db, r.personal_id, r.fecha)
    await db.commit()
    await db.refresh(r)
    return r


@router.post("/horas/bulk", status_code=status.HTTP_201_CREATED)
async def create_horas_bulk(body: RegistroHorasBulkCreate, db: AsyncSession = Depends(get_db), _=_auth):
    orden_ids: set[int] = set()
    for item in body.items:
        db.add(RegistroHoras(
            personal_id=body.personal_id,
            orden_id=item.orden_id,
            fecha=body.fecha,
            horas_trabajadas=item.horas_trabajadas,
            tarifa_hora=item.tarifa_hora,
            tipo_trabajo=body.tipo_trabajo,
            observaciones=body.observaciones,
        ))
        if item.orden_id:
            orden_ids.add(item.orden_id)
    await db.flush()
    await _recalcular_costos_ordenes(db, orden_ids)
    await _upsert_subsidio_transporte(db, body.personal_id, body.fecha)
    await db.commit()
    return {"creados": len(body.items)}


@router.put("/horas/{hora_id}", response_model=RegistroHorasRead)
async def update_hora(
    hora_id: int, body: RegistroHorasUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(RegistroHoras).where(RegistroHoras.id == hora_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if r.aprobado:
        raise HTTPException(status_code=400, detail="No se puede editar un registro aprobado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    await db.commit()
    await db.refresh(r)
    return r


@router.delete("/horas/{hora_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_hora(hora_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin):
    result = await db.execute(select(RegistroHoras).where(RegistroHoras.id == hora_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if r.liquidado:
        raise HTTPException(status_code=400, detail="No se puede eliminar un registro liquidado")
    orden_id = r.orden_id
    personal_id = r.personal_id
    fecha = r.fecha
    await db.delete(r)
    await db.flush()
    if orden_id:
        await _recalcular_costos_ordenes(db, {orden_id})
    await _upsert_subsidio_transporte(db, personal_id, fecha)
    await db.commit()


@router.post("/horas/{hora_id}/aprobar", response_model=RegistroHorasRead)
async def aprobar_hora(hora_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin):
    result = await db.execute(select(RegistroHoras).where(RegistroHoras.id == hora_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    r.aprobado = True
    r.fecha_aprobacion = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(r)
    return r


# ── Registro de labores ───────────────────────────────────────────────────────

_LABORES_ENRICH_SQL = """
    SELECT
        rl.*,
        p.nombre_completo AS personal_nombre,
        o.numero_orden    AS orden_numero
    FROM registro_labores rl
    JOIN personal p ON p.id = rl.personal_id
    LEFT JOIN ordenes o ON o.id = rl.orden_id
    WHERE 1=1
"""


@router.get("/labores", response_model=list[RegistroLaboresRead])
async def list_labores(
    personal_id: int | None = None,
    mes: int | None = None,
    anio: int | None = None,
    aprobado: bool | None = None,
    tipo_labor: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    filters = []
    params: dict = {}
    if personal_id is not None:
        filters.append("AND rl.personal_id = :personal_id")
        params["personal_id"] = personal_id
    if mes is not None:
        filters.append("AND EXTRACT(MONTH FROM rl.fecha) = :mes")
        params["mes"] = mes
    if anio is not None:
        filters.append("AND EXTRACT(YEAR FROM rl.fecha) = :anio")
        params["anio"] = anio
    if aprobado is not None:
        filters.append("AND rl.aprobado = :aprobado")
        params["aprobado"] = aprobado
    if tipo_labor:
        filters.append("AND rl.tipo_labor = :tipo_labor")
        params["tipo_labor"] = tipo_labor

    sql = text(_LABORES_ENRICH_SQL + " ".join(filters) + " ORDER BY rl.fecha DESC")
    rows = (await db.execute(sql, params)).mappings().all()
    return [RegistroLaboresRead(**dict(r)) for r in rows]


@router.post("/labores", response_model=RegistroLaboresRead, status_code=status.HTTP_201_CREATED)
async def create_labor(body: RegistroLaboresCreate, db: AsyncSession = Depends(get_db), _=_auth):
    r = RegistroLabores(**body.model_dump())
    db.add(r)
    await db.flush()
    if r.orden_id:
        await _recalcular_costos_ordenes(db, {r.orden_id})
    await db.commit()
    await db.refresh(r)
    return r


@router.post("/labores/bulk", status_code=status.HTTP_201_CREATED)
async def create_labores_bulk(body: list[RegistroLaboresCreate], db: AsyncSession = Depends(get_db), _=_auth):
    orden_ids: set[int] = set()
    for item in body:
        db.add(RegistroLabores(**item.model_dump()))
        if item.orden_id:
            orden_ids.add(item.orden_id)
    await db.flush()
    await _recalcular_costos_ordenes(db, orden_ids)
    await db.commit()
    return {"creados": len(body)}


@router.put("/labores/{labor_id}", response_model=RegistroLaboresRead)
async def update_labor(
    labor_id: int, body: RegistroLaboresUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(RegistroLabores).where(RegistroLabores.id == labor_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if r.aprobado:
        raise HTTPException(status_code=400, detail="No se puede editar un registro aprobado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(r, field, value)
    await db.commit()
    await db.refresh(r)
    return r


@router.delete("/labores/{labor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_labor(labor_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin):
    result = await db.execute(select(RegistroLabores).where(RegistroLabores.id == labor_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    if r.liquidado:
        raise HTTPException(status_code=400, detail="No se puede eliminar un registro liquidado")
    orden_id = r.orden_id
    await db.delete(r)
    await db.flush()
    if orden_id:
        await _recalcular_costos_ordenes(db, {orden_id})
    await db.commit()


@router.post("/labores/{labor_id}/aprobar", response_model=RegistroLaboresRead)
async def aprobar_labor(labor_id: int, db: AsyncSession = Depends(get_db), _=_auth_admin):
    result = await db.execute(select(RegistroLabores).where(RegistroLabores.id == labor_id))
    r = result.scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    r.aprobado = True
    r.fecha_aprobacion = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(r)
    return r


# ── Resumen por persona ───────────────────────────────────────────────────────

@router.get("/resumen/diario", response_model=list[ResumenDiario])
async def resumen_diario(
    mes: int | None = None,
    anio: int | None = None,
    personal_id: int | None = None,
    aprobado: bool | None = None,
    liquidado: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    params: dict = {}
    mes_filter = ""
    anio_filter = ""
    personal_filter = ""
    aprobado_filter = ""
    liquidado_filter = ""
    if mes is not None:
        mes_filter = "AND EXTRACT(MONTH FROM r.fecha) = :mes"
        params["mes"] = mes
    if anio is not None:
        anio_filter = "AND EXTRACT(YEAR FROM r.fecha) = :anio"
        params["anio"] = anio
    if personal_id is not None:
        personal_filter = "AND r.personal_id = :personal_id"
        params["personal_id"] = personal_id
    if aprobado is not None:
        aprobado_filter = "AND r.aprobado = :aprobado"
        params["aprobado"] = aprobado
    if liquidado is not None:
        liquidado_filter = "AND r.liquidado = :liquidado"
        params["liquidado"] = liquidado

    filters = f"{mes_filter} {anio_filter} {personal_filter} {aprobado_filter} {liquidado_filter}"

    sql = text(f"""
        SELECT
            p.id AS personal_id,
            p.nombre_completo,
            d.fecha,
            COALESCE(h.total_horas, 0)         AS total_horas,
            COALESCE(h.total_horas_monto, 0)   AS total_horas_monto,
            COALESCE(l.total_labores, 0)        AS total_labores,
            COALESCE(l.total_labores_monto, 0)  AS total_labores_monto,
            COALESCE(h.total_horas_monto, 0) + COALESCE(l.total_labores_monto, 0) AS total_general
        FROM (
            SELECT DISTINCT personal_id, fecha FROM registro_horas r WHERE 1=1 {filters}
            UNION
            SELECT DISTINCT personal_id, fecha FROM registro_labores r WHERE 1=1 {filters}
        ) d
        JOIN personal p ON p.id = d.personal_id
        LEFT JOIN (
            SELECT personal_id, fecha,
                   SUM(horas_trabajadas)               AS total_horas,
                   SUM(horas_trabajadas * tarifa_hora) AS total_horas_monto
            FROM registro_horas r WHERE 1=1 {filters}
            GROUP BY personal_id, fecha
        ) h ON h.personal_id = d.personal_id AND h.fecha = d.fecha
        LEFT JOIN (
            SELECT personal_id, fecha,
                   SUM(cantidad)                   AS total_labores,
                   SUM(cantidad * tarifa_unitaria)  AS total_labores_monto
            FROM registro_labores r WHERE 1=1 {filters}
            GROUP BY personal_id, fecha
        ) l ON l.personal_id = d.personal_id AND l.fecha = d.fecha
        ORDER BY d.fecha DESC, p.nombre_completo
    """)
    rows = (await db.execute(sql, params)).mappings().all()
    return [ResumenDiario(**dict(r)) for r in rows]


@router.get("/resumen", response_model=list[ResumenLabores])
async def resumen_labores(
    mes: int | None = None,
    anio: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    params: dict = {}
    mes_filter = ""
    anio_filter = ""
    if mes is not None:
        mes_filter = "AND EXTRACT(MONTH FROM r.fecha) = :mes"
        params["mes"] = mes
    if anio is not None:
        anio_filter = "AND EXTRACT(YEAR FROM r.fecha) = :anio"
        params["anio"] = anio

    sql = text(f"""
        SELECT
            p.id AS personal_id,
            p.nombre_completo,
            COALESCE(h.total_horas, 0)         AS total_horas,
            COALESCE(h.total_horas_monto, 0)   AS total_horas_monto,
            COALESCE(l.total_labores, 0)        AS total_labores,
            COALESCE(l.total_labores_monto, 0)  AS total_labores_monto,
            COALESCE(h.total_horas_monto, 0) + COALESCE(l.total_labores_monto, 0) AS total_general
        FROM personal p
        LEFT JOIN (
            SELECT personal_id,
                   SUM(horas_trabajadas)              AS total_horas,
                   SUM(horas_trabajadas * tarifa_hora) AS total_horas_monto
            FROM registro_horas r WHERE 1=1 {mes_filter} {anio_filter}
            GROUP BY personal_id
        ) h ON p.id = h.personal_id
        LEFT JOIN (
            SELECT personal_id,
                   SUM(cantidad)                   AS total_labores,
                   SUM(cantidad * tarifa_unitaria)  AS total_labores_monto
            FROM registro_labores r WHERE 1=1 {mes_filter} {anio_filter}
            GROUP BY personal_id
        ) l ON p.id = l.personal_id
        WHERE h.personal_id IS NOT NULL OR l.personal_id IS NOT NULL
        ORDER BY total_general DESC
    """)
    rows = (await db.execute(sql, params)).mappings().all()
    return [ResumenLabores(**dict(r)) for r in rows]
