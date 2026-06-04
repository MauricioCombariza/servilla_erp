from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.nomina import NominaEmpleado, NominaParametro, NominaProvision
from app.schemas.nomina import (
    CalcularProvisionesRequest,
    NominaEmpleadoCreate, NominaEmpleadoRead, NominaEmpleadoUpdate,
    NominaParametroRead, NominaParametroUpdate,
    NominaProvisionRead, ResumenNomina,
)

router = APIRouter(prefix="/api/nomina", tags=["nomina"])
_auth = Depends(require_role("administrador", "contabilidad"))

# Tasas 2025 Colombia (usadas si no existen registros en nomina_parametros)
_DEFAULTS = {
    "arl": 0.00522,
    "eps": 0.085,
    "afp": 0.12,
    "caja": 0.04,
    "prima": 1 / 12,
    "cesantias": 1 / 12,
    "int_cesantias": 0.12,
    "vacaciones": 1 / 24,
    "auxilio_transporte": 162_000.0,
}


async def _get_tasas(db: AsyncSession) -> dict:
    rows = (
        await db.execute(
            select(NominaParametro).where(NominaParametro.activo == True)  # noqa: E712
        )
    ).scalars().all()
    tasas = {**_DEFAULTS}
    for r in rows:
        tasas[r.parametro] = float(r.valor)
    return tasas


# ── Empleados ─────────────────────────────────────────────────────────────────

@router.get("/empleados", response_model=list[NominaEmpleadoRead])
async def list_empleados(
    activo: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(NominaEmpleado).order_by(NominaEmpleado.nombre_completo)
    if activo is not None:
        q = q.where(NominaEmpleado.activo == activo)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/empleados", response_model=NominaEmpleadoRead, status_code=status.HTTP_201_CREATED)
async def create_empleado(body: NominaEmpleadoCreate, db: AsyncSession = Depends(get_db), _=_auth):
    e = NominaEmpleado(**body.model_dump())
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


@router.put("/empleados/{empleado_id}", response_model=NominaEmpleadoRead)
async def update_empleado(
    empleado_id: int, body: NominaEmpleadoUpdate, db: AsyncSession = Depends(get_db), _=_auth
):
    result = await db.execute(select(NominaEmpleado).where(NominaEmpleado.id == empleado_id))
    e = result.scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(e, field, value)
    await db.commit()
    await db.refresh(e)
    return e


# ── Provisiones ───────────────────────────────────────────────────────────────

@router.get("/provisiones", response_model=list[NominaProvisionRead])
async def list_provisiones(
    mes: int | None = None,
    anio: int | None = None,
    empleado_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(NominaProvision).order_by(
        NominaProvision.periodo_anio.desc(),
        NominaProvision.periodo_mes.desc(),
    )
    if mes is not None:
        q = q.where(NominaProvision.periodo_mes == mes)
    if anio is not None:
        q = q.where(NominaProvision.periodo_anio == anio)
    if empleado_id is not None:
        q = q.where(NominaProvision.empleado_id == empleado_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/provisiones/calcular", response_model=ResumenNomina)
async def calcular_provisiones(
    body: CalcularProvisionesRequest, db: AsyncSession = Depends(get_db), _=_auth
):
    empleados = (
        await db.execute(
            select(NominaEmpleado).where(NominaEmpleado.activo == True)  # noqa: E712
        )
    ).scalars().all()

    if not empleados:
        raise HTTPException(status_code=400, detail="No hay empleados activos")

    tasas = await _get_tasas(db)
    total_salarios = 0.0
    total_ss = 0.0
    total_prov = 0.0
    total_costo = 0.0

    for emp in empleados:
        sal = float(emp.salario_mensual)
        aux_t = float(tasas["auxilio_transporte"]) if emp.tiene_auxilio_transporte else 0.0
        aux_ns = float(emp.auxilio_no_salarial)

        arl = round(sal * tasas["arl"], 2)
        eps = round(sal * tasas["eps"], 2)
        afp = round(sal * tasas["afp"], 2)
        caja = round(sal * tasas["caja"], 2)
        prima = round(sal * tasas["prima"], 2)
        ces = round(sal * tasas["cesantias"], 2)
        int_ces = round(ces * tasas["int_cesantias"], 2)
        vac = round(sal * tasas["vacaciones"], 2)

        ss = arl + eps + afp + caja
        prov = prima + ces + int_ces + vac
        costo_emp = sal + aux_t + aux_ns + ss + prov

        total_salarios += sal
        total_ss += ss
        total_prov += prov
        total_costo += costo_emp

        # upsert provision
        existing = (
            await db.execute(
                select(NominaProvision).where(
                    NominaProvision.empleado_id == emp.id,
                    NominaProvision.periodo_mes == body.periodo_mes,
                    NominaProvision.periodo_anio == body.periodo_anio,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.salario_base = sal
            existing.auxilio_transporte = aux_t
            existing.auxilio_no_salarial = aux_ns
            existing.arl = arl
            existing.eps = eps
            existing.afp = afp
            existing.caja_compensacion = caja
            existing.prima = prima
            existing.cesantias = ces
            existing.int_cesantias = int_ces
            existing.vacaciones = vac
        else:
            prov_rec = NominaProvision(
                empleado_id=emp.id,
                periodo_mes=body.periodo_mes,
                periodo_anio=body.periodo_anio,
                salario_base=sal,
                auxilio_transporte=aux_t,
                auxilio_no_salarial=aux_ns,
                arl=arl,
                eps=eps,
                afp=afp,
                caja_compensacion=caja,
                prima=prima,
                cesantias=ces,
                int_cesantias=int_ces,
                vacaciones=vac,
            )
            db.add(prov_rec)

    await db.commit()

    return ResumenNomina(
        periodo_mes=body.periodo_mes,
        periodo_anio=body.periodo_anio,
        total_empleados=len(empleados),
        total_salarios=round(total_salarios, 2),
        total_seguridad_social=round(total_ss, 2),
        total_provisiones=round(total_prov, 2),
        costo_total=round(total_costo, 2),
    )


# ── Parámetros ────────────────────────────────────────────────────────────────

@router.get("/parametros", response_model=list[NominaParametroRead])
async def list_parametros(db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(
        select(NominaParametro).order_by(NominaParametro.parametro)
    )
    return result.scalars().all()


@router.post(
    "/parametros",
    response_model=NominaParametroRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_parametro(
    body: NominaParametroRead,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    p = NominaParametro(**body.model_dump(exclude={"id"}))
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@router.put("/parametros/{param_id}", response_model=NominaParametroRead)
async def update_parametro(
    param_id: int,
    body: NominaParametroUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(select(NominaParametro).where(NominaParametro.id == param_id))
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Parámetro no encontrado")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    await db.commit()
    await db.refresh(p)
    return p
