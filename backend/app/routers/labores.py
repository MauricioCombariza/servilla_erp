from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.labores import RegistroHoras, RegistroLabores
from app.models.personal import Personal
from app.schemas.labores import (
    RegistroHorasCreate, RegistroHorasRead, RegistroHorasUpdate,
    RegistroLaboresCreate, RegistroLaboresRead, RegistroLaboresUpdate,
    ResumenLabores,
)

router = APIRouter(prefix="/api/labores", tags=["labores"])
_auth = Depends(require_role("administrador", "operaciones", "contabilidad"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


# ── Registro de horas ─────────────────────────────────────────────────────────

@router.get("/horas", response_model=list[RegistroHorasRead])
async def list_horas(
    personal_id: int | None = None,
    mes: int | None = None,
    anio: int | None = None,
    aprobado: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    from sqlalchemy import extract
    q = select(RegistroHoras).order_by(RegistroHoras.fecha.desc())
    if personal_id is not None:
        q = q.where(RegistroHoras.personal_id == personal_id)
    if mes is not None:
        q = q.where(extract("month", RegistroHoras.fecha) == mes)
    if anio is not None:
        q = q.where(extract("year", RegistroHoras.fecha) == anio)
    if aprobado is not None:
        q = q.where(RegistroHoras.aprobado == aprobado)
    result = await db.execute(q)
    rows = result.scalars().all()
    # Enrich with computed total (GENERATED column)
    return rows


@router.post("/horas", response_model=RegistroHorasRead, status_code=status.HTTP_201_CREATED)
async def create_hora(body: RegistroHorasCreate, db: AsyncSession = Depends(get_db), _=_auth):
    r = RegistroHoras(**body.model_dump())
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


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
    await db.delete(r)
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
    from sqlalchemy import extract
    q = select(RegistroLabores).order_by(RegistroLabores.fecha.desc())
    if personal_id is not None:
        q = q.where(RegistroLabores.personal_id == personal_id)
    if mes is not None:
        q = q.where(extract("month", RegistroLabores.fecha) == mes)
    if anio is not None:
        q = q.where(extract("year", RegistroLabores.fecha) == anio)
    if aprobado is not None:
        q = q.where(RegistroLabores.aprobado == aprobado)
    if tipo_labor:
        q = q.where(RegistroLabores.tipo_labor == tipo_labor)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/labores", response_model=RegistroLaboresRead, status_code=status.HTTP_201_CREATED)
async def create_labor(body: RegistroLaboresCreate, db: AsyncSession = Depends(get_db), _=_auth):
    r = RegistroLabores(**body.model_dump())
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


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
    await db.delete(r)
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

@router.get("/resumen", response_model=list[ResumenLabores])
async def resumen_labores(
    mes: int | None = None,
    anio: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    from sqlalchemy import extract
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
            COALESCE(h.total_horas, 0)       AS total_horas,
            COALESCE(h.total_horas_monto, 0) AS total_horas_monto,
            COALESCE(l.total_labores, 0)     AS total_labores,
            COALESCE(l.total_labores_monto, 0) AS total_labores_monto,
            COALESCE(h.total_horas_monto, 0) + COALESCE(l.total_labores_monto, 0) AS total_general
        FROM personal p
        LEFT JOIN (
            SELECT personal_id,
                   SUM(horas_trabajadas)          AS total_horas,
                   SUM(horas_trabajadas * tarifa_hora) AS total_horas_monto
            FROM registro_horas r WHERE 1=1 {mes_filter} {anio_filter}
            GROUP BY personal_id
        ) h ON p.id = h.personal_id
        LEFT JOIN (
            SELECT personal_id,
                   SUM(cantidad)                    AS total_labores,
                   SUM(cantidad * tarifa_unitaria)  AS total_labores_monto
            FROM registro_labores r WHERE 1=1 {mes_filter} {anio_filter}
            GROUP BY personal_id
        ) l ON p.id = l.personal_id
        WHERE h.personal_id IS NOT NULL OR l.personal_id IS NOT NULL
        ORDER BY total_general DESC
    """)
    rows = (await db.execute(sql, params)).mappings().all()
    return [ResumenLabores(**dict(r)) for r in rows]
