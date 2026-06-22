from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.nomina import NominaEmpleado, NominaParametro, NominaProvision, PagoOperativo
from app.schemas.nomina import (
    CalcularProvisionesRequest,
    EmpleadoResumen,
    MarcarPagadoRequest,
    NominaEmpleadoCreate, NominaEmpleadoRead, NominaEmpleadoUpdate,
    NominaParametroCreate, NominaParametroRead, NominaParametroUpdate,
    NominaProvisionRead, PeriodoHistorico, ResumenNomina, ResumenNominaDetallado,
    PagoOperativoCreate, PagoOperativoRead,
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
    "auxilio_transporte": 249_095.0,
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


def _ultimo_dia_mes(mes: int, anio: int) -> date:
    if mes == 12:
        return date(anio + 1, 1, 1) - timedelta(days=1)
    return date(anio, mes + 1, 1) - timedelta(days=1)


def _calc(sal: float, aux_t: float, aux_ns: float, tasas: dict) -> dict:
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
    return {
        "arl": arl, "eps": eps, "afp": afp, "caja": caja,
        "prima": prima, "cesantias": ces, "int_cesantias": int_ces, "vacaciones": vac,
        "ss": ss, "prov": prov,
        "costo": sal + aux_t + aux_ns + ss + prov,
    }


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
    corte = _ultimo_dia_mes(body.periodo_mes, body.periodo_anio)
    empleados = (
        await db.execute(
            select(NominaEmpleado).where(
                NominaEmpleado.activo == True,  # noqa: E712
                or_(
                    NominaEmpleado.fecha_ingreso == None,  # noqa: E711
                    NominaEmpleado.fecha_ingreso <= corte,
                ),
            )
        )
    ).scalars().all()

    if not empleados:
        raise HTTPException(status_code=400, detail="No hay empleados activos para este período")

    tasas = await _get_tasas(db)
    total_salarios = 0.0
    total_ss = 0.0
    total_prov = 0.0
    total_costo = 0.0

    for emp in empleados:
        sal = float(emp.salario_mensual)
        aux_t = float(tasas["auxilio_transporte"]) if emp.tiene_auxilio_transporte else 0.0
        aux_ns = float(emp.auxilio_no_salarial)
        c = _calc(sal, aux_t, aux_ns, tasas)

        total_salarios += sal
        total_ss += c["ss"]
        total_prov += c["prov"]
        total_costo += c["costo"]

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
            existing.arl = c["arl"]
            existing.eps = c["eps"]
            existing.afp = c["afp"]
            existing.caja_compensacion = c["caja"]
            existing.prima = c["prima"]
            existing.cesantias = c["cesantias"]
            existing.int_cesantias = c["int_cesantias"]
            existing.vacaciones = c["vacaciones"]
        else:
            db.add(NominaProvision(
                empleado_id=emp.id,
                periodo_mes=body.periodo_mes,
                periodo_anio=body.periodo_anio,
                salario_base=sal,
                auxilio_transporte=aux_t,
                auxilio_no_salarial=aux_ns,
                arl=c["arl"],
                eps=c["eps"],
                afp=c["afp"],
                caja_compensacion=c["caja"],
                prima=c["prima"],
                cesantias=c["cesantias"],
                int_cesantias=c["int_cesantias"],
                vacaciones=c["vacaciones"],
            ))

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


@router.get("/resumen", response_model=ResumenNominaDetallado)
async def get_resumen(db: AsyncSession = Depends(get_db), _=_auth):
    empleados = (
        await db.execute(
            select(NominaEmpleado)
            .where(NominaEmpleado.activo == True)  # noqa: E712
            .order_by(NominaEmpleado.nombre_completo)
        )
    ).scalars().all()

    tasas = await _get_tasas(db)
    rows: list[EmpleadoResumen] = []
    tots = {k: 0.0 for k in [
        "sal", "aux_t", "aux_ns", "arl", "eps", "afp", "caja",
        "prima", "cesantias", "int_cesantias", "vacaciones", "ss", "prov", "costo",
    ]}

    for emp in empleados:
        sal = float(emp.salario_mensual)
        aux_t = float(tasas["auxilio_transporte"]) if emp.tiene_auxilio_transporte else 0.0
        aux_ns = float(emp.auxilio_no_salarial)
        c = _calc(sal, aux_t, aux_ns, tasas)

        rows.append(EmpleadoResumen(
            id=emp.id,
            nombre_completo=emp.nombre_completo,
            cargo=emp.cargo,
            salario_mensual=sal,
            auxilio_no_salarial=aux_ns,
            auxilio_transporte=aux_t,
            arl=c["arl"], eps=c["eps"], afp=c["afp"], caja_compensacion=c["caja"],
            prima=c["prima"], cesantias=c["cesantias"],
            int_cesantias=c["int_cesantias"], vacaciones=c["vacaciones"],
            total_seguridad_social=c["ss"],
            total_provisiones=c["prov"],
            costo_total=c["costo"],
        ))
        tots["sal"] += sal; tots["aux_t"] += aux_t; tots["aux_ns"] += aux_ns
        for k in ["arl", "eps", "afp", "caja", "prima", "cesantias", "int_cesantias", "vacaciones", "ss", "prov", "costo"]:
            tots[k] += c[k]

    return ResumenNominaDetallado(
        total_empleados=len(empleados),
        empleados=rows,
        total_salarios=round(tots["sal"], 2),
        total_aux_no_salarial=round(tots["aux_ns"], 2),
        total_aux_transporte=round(tots["aux_t"], 2),
        total_nomina_base=round(tots["sal"] + tots["aux_ns"] + tots["aux_t"], 2),
        total_arl=round(tots["arl"], 2),
        total_eps=round(tots["eps"], 2),
        total_afp=round(tots["afp"], 2),
        total_caja=round(tots["caja"], 2),
        total_seguridad_social=round(tots["ss"], 2),
        total_prima=round(tots["prima"], 2),
        total_cesantias=round(tots["cesantias"], 2),
        total_int_cesantias=round(tots["int_cesantias"], 2),
        total_vacaciones=round(tots["vacaciones"], 2),
        total_provisiones=round(tots["prov"], 2),
        costo_total=round(tots["costo"], 2),
    )


@router.get("/provisiones/historico", response_model=list[PeriodoHistorico])
async def get_provisiones_historico(db: AsyncSession = Depends(get_db), _=_auth):
    result = await db.execute(
        select(
            NominaProvision.periodo_anio,
            NominaProvision.periodo_mes,
            func.count(NominaProvision.empleado_id).label("total_empleados"),
            func.sum(
                func.coalesce(NominaProvision.salario_base, 0)
                + func.coalesce(NominaProvision.auxilio_transporte, 0)
                + func.coalesce(NominaProvision.auxilio_no_salarial, 0)
                + func.coalesce(NominaProvision.arl, 0)
                + func.coalesce(NominaProvision.eps, 0)
                + func.coalesce(NominaProvision.afp, 0)
                + func.coalesce(NominaProvision.caja_compensacion, 0)
                + func.coalesce(NominaProvision.prima, 0)
                + func.coalesce(NominaProvision.cesantias, 0)
                + func.coalesce(NominaProvision.int_cesantias, 0)
                + func.coalesce(NominaProvision.vacaciones, 0)
            ).label("costo_total"),
        )
        .group_by(NominaProvision.periodo_anio, NominaProvision.periodo_mes)
        .order_by(NominaProvision.periodo_anio.desc(), NominaProvision.periodo_mes.desc())
        .limit(12)
    )
    return [
        PeriodoHistorico(
            periodo_mes=r.periodo_mes,
            periodo_anio=r.periodo_anio,
            total_empleados=r.total_empleados,
            costo_total=float(r.costo_total),
        )
        for r in result.all()
    ]


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
    body: NominaParametroCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    p = NominaParametro(**body.model_dump())
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


# ── Pagos Operativos ──────────────────────────────────────────────────────────

@router.get("/pagos", response_model=list[PagoOperativoRead])
async def list_pagos(
    mes: int | None = None,
    anio: int | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(PagoOperativo).order_by(
        PagoOperativo.periodo_anio.desc(),
        PagoOperativo.periodo_mes.desc(),
        PagoOperativo.tipo,
    )
    if mes is not None:
        q = q.where(PagoOperativo.periodo_mes == mes)
    if anio is not None:
        q = q.where(PagoOperativo.periodo_anio == anio)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/pagos", response_model=PagoOperativoRead, status_code=status.HTTP_201_CREATED)
async def upsert_pago(body: PagoOperativoCreate, db: AsyncSession = Depends(get_db), _=_auth):
    existing = (
        await db.execute(
            select(PagoOperativo).where(
                PagoOperativo.tipo == body.tipo,
                PagoOperativo.periodo_mes == body.periodo_mes,
                PagoOperativo.periodo_anio == body.periodo_anio,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.monto_total = body.monto_total
        existing.fecha_vencimiento = body.fecha_vencimiento
        existing.observaciones = body.observaciones
        await db.commit()
        await db.refresh(existing)
        return existing

    pago = PagoOperativo(**body.model_dump())
    db.add(pago)
    await db.commit()
    await db.refresh(pago)
    return pago


@router.put("/pagos/{pago_id}/marcar-pagado", response_model=PagoOperativoRead)
async def marcar_pagado(
    pago_id: int,
    body: MarcarPagadoRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    result = await db.execute(select(PagoOperativo).where(PagoOperativo.id == pago_id))
    pago = result.scalar_one_or_none()
    if pago is None:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    pago.estado = "pagado"
    pago.fecha_pago = body.fecha_pago
    await db.commit()
    await db.refresh(pago)
    return pago
