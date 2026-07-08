from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.pagos_ciudades import FacturaCourierCxp, PrefacturaCourier, PrefacturaPlanilla
from app.models.personal import Personal
from app.schemas.pagos_ciudades import (
    AjustarMontoRequest,
    FacturaCourierCxpRead,
    FacturaCourierCxpUpdate,
    PagarCxpRequest,
    PlanillaCalculada,
    PrefacturaCourierCreate,
    PrefacturaCourierRead,
    RegistrarFacturaRequest,
)

router = APIRouter(prefix="/api/pagos-ciudades", tags=["pagos-ciudades"])
_auth = Depends(require_role("administrador", "contabilidad", "operaciones"))
_auth_admin = Depends(require_role("administrador", "contabilidad"))


_PLANILLAS_SQL = """
    SELECT
        sg.planilla,
        sg.cod_men                                                             AS cod_mensajero,
        MIN(sg.f_esc)                                                          AS fecha_escaner,
        COUNT(*) FILTER (WHERE sg.ambito = 'bogota')                           AS cantidad_local,
        COUNT(*) FILTER (WHERE sg.ambito = 'nacional')                        AS cantidad_nacional,
        COALESCE(ROUND(AVG(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'bogota'), 2), 0)   AS precio_local_promedio,
        COALESCE(ROUND(AVG(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'nacional'), 2), 0) AS precio_nac_promedio,
        COALESCE(SUM(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'bogota'), 0)   AS valor_local,
        COALESCE(SUM(sg.precio_mensajero) FILTER (WHERE sg.ambito = 'nacional'), 0) AS valor_nac,
        COALESCE(SUM(sg.precio_mensajero), 0)                                  AS valor_total
    FROM seriales_gestion sg
    JOIN personal p ON p.codigo = sg.cod_men
    WHERE sg.cod_men = :cod_mensajero
      AND p.tipo_personal IN ('courier_externo', 'transportadora')
      AND sg.estado != 'anulado'
      AND sg.f_esc BETWEEN :desde AND :hasta
    GROUP BY sg.planilla, sg.cod_men
    ORDER BY MIN(sg.f_esc)
"""

_PLANILLAS_POR_LISTA_SQL = _PLANILLAS_SQL.replace(
    "AND sg.f_esc BETWEEN :desde AND :hasta",
    "AND sg.planilla = ANY(:planillas)",
)


async def _planillas_ya_incluidas(db: AsyncSession, planillas: list[str]) -> dict[str, int]:
    if not planillas:
        return {}
    rows = (
        await db.execute(
            text("SELECT planilla, prefactura_id FROM prefactura_planillas WHERE planilla = ANY(:planillas)"),
            {"planillas": planillas},
        )
    ).all()
    return {r.planilla: r.prefactura_id for r in rows}


async def _nombres_mensajeros(db: AsyncSession, codigos: set[str]) -> dict[str, str]:
    if not codigos:
        return {}
    rows = (
        await db.execute(select(Personal.codigo, Personal.nombre_completo).where(Personal.codigo.in_(codigos)))
    ).all()
    return {r.codigo: r.nombre_completo for r in rows}


def _prefactura_to_read(pf: PrefacturaCourier, nombre: str | None) -> PrefacturaCourierRead:
    valor_ajustado = float(pf.valor_ajustado) if pf.valor_ajustado is not None else None
    return PrefacturaCourierRead(
        id=pf.id,
        cod_mensajero=pf.cod_mensajero,
        mensajero_nombre=nombre,
        fecha_generacion=pf.fecha_generacion,
        periodo_desde=pf.periodo_desde,
        periodo_hasta=pf.periodo_hasta,
        cantidad_planillas=pf.cantidad_planillas,
        cantidad_local=pf.cantidad_local,
        cantidad_nacional=pf.cantidad_nacional,
        valor_local=float(pf.valor_local),
        valor_nacional=float(pf.valor_nacional),
        valor_total=float(pf.valor_total),
        estado=pf.estado,
        notas=pf.notas,
        valor_ajustado=valor_ajustado,
        notas_ajuste=pf.notas_ajuste,
        valor_a_pagar=valor_ajustado if valor_ajustado is not None else float(pf.valor_total),
        created_at=pf.created_at,
        planillas=list(pf.planillas),
    )


def _cxp_to_read(cxp: FacturaCourierCxp, nombre: str | None) -> FacturaCourierCxpRead:
    return FacturaCourierCxpRead(
        id=cxp.id,
        prefactura_id=cxp.prefactura_id,
        cod_mensajero=cxp.cod_mensajero,
        mensajero_nombre=nombre,
        numero_factura=cxp.numero_factura,
        fecha_emision=cxp.fecha_emision,
        fecha_vencimiento=cxp.fecha_vencimiento,
        valor_total=float(cxp.valor_total),
        estado=cxp.estado,
        notas=cxp.notas,
        fecha_pago=cxp.fecha_pago,
        created_at=cxp.created_at,
    )


# ── Planillas disponibles ──────────────────────────────────────────────────────

@router.get("/planillas", response_model=list[PlanillaCalculada])
async def planillas_disponibles(
    cod_mensajero: str,
    desde: date,
    hasta: date,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    rows = (
        await db.execute(text(_PLANILLAS_SQL), {"cod_mensajero": cod_mensajero, "desde": desde, "hasta": hasta})
    ).mappings().all()
    incluidas = await _planillas_ya_incluidas(db, [r["planilla"] for r in rows])
    return [
        PlanillaCalculada(
            **r,
            ya_incluida=r["planilla"] in incluidas,
            prefactura_id=incluidas.get(r["planilla"]),
        )
        for r in rows
    ]


# ── Prefacturas ─────────────────────────────────────────────────────────────────

@router.post("/prefacturas", response_model=PrefacturaCourierRead, status_code=status.HTTP_201_CREATED)
async def crear_prefactura(
    body: PrefacturaCourierCreate,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    if not body.planillas:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos una planilla")

    ya_incluidas = await _planillas_ya_incluidas(db, body.planillas)
    if ya_incluidas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Las siguientes planillas ya están en otra prefactura: {', '.join(ya_incluidas)}",
        )

    rows = (
        await db.execute(
            text(_PLANILLAS_POR_LISTA_SQL),
            {"cod_mensajero": body.cod_mensajero, "planillas": body.planillas},
        )
    ).mappings().all()
    if not rows:
        raise HTTPException(status_code=400, detail="No se encontraron datos para las planillas seleccionadas")

    prefactura = PrefacturaCourier(
        cod_mensajero=body.cod_mensajero,
        fecha_generacion=date.today(),
        periodo_desde=body.periodo_desde,
        periodo_hasta=body.periodo_hasta,
        cantidad_planillas=len(rows),
        cantidad_local=sum(r["cantidad_local"] for r in rows),
        cantidad_nacional=sum(r["cantidad_nacional"] for r in rows),
        valor_local=sum(float(r["valor_local"]) for r in rows),
        valor_nacional=sum(float(r["valor_nac"]) for r in rows),
        valor_total=sum(float(r["valor_total"]) for r in rows),
        estado="borrador",
        notas=body.notas,
        valor_ajustado=body.valor_ajustado,
        notas_ajuste=body.notas_ajuste,
    )
    db.add(prefactura)
    await db.flush()

    for r in rows:
        db.add(
            PrefacturaPlanilla(
                prefactura_id=prefactura.id,
                planilla=r["planilla"],
                fecha_escaner=r["fecha_escaner"],
                cantidad_local=r["cantidad_local"],
                cantidad_nacional=r["cantidad_nacional"],
                precio_local=r["precio_local_promedio"],
                precio_nac=r["precio_nac_promedio"],
                valor_local=r["valor_local"],
                valor_nac=r["valor_nac"],
                valor_total=r["valor_total"],
            )
        )

    await db.commit()
    await db.refresh(prefactura)
    nombres = await _nombres_mensajeros(db, {prefactura.cod_mensajero})
    return _prefactura_to_read(prefactura, nombres.get(prefactura.cod_mensajero))


@router.get("/prefacturas", response_model=list[PrefacturaCourierRead])
async def listar_prefacturas(
    estado: str | None = None,
    cod_mensajero: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = select(PrefacturaCourier).order_by(PrefacturaCourier.fecha_generacion.desc())
    if estado:
        q = q.where(PrefacturaCourier.estado == estado)
    if cod_mensajero:
        q = q.where(PrefacturaCourier.cod_mensajero == cod_mensajero)
    rows = (await db.execute(q)).scalars().all()
    nombres = await _nombres_mensajeros(db, {r.cod_mensajero for r in rows})
    return [_prefactura_to_read(r, nombres.get(r.cod_mensajero)) for r in rows]


async def _get_prefactura_or_404(db: AsyncSession, prefactura_id: int) -> PrefacturaCourier:
    pf = (
        await db.execute(select(PrefacturaCourier).where(PrefacturaCourier.id == prefactura_id))
    ).scalar_one_or_none()
    if pf is None:
        raise HTTPException(status_code=404, detail="Prefactura no encontrada")
    return pf


@router.post("/prefacturas/{prefactura_id}/aprobar", response_model=PrefacturaCourierRead)
async def aprobar_prefactura(
    prefactura_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    pf = await _get_prefactura_or_404(db, prefactura_id)
    if pf.estado != "borrador":
        raise HTTPException(status_code=400, detail="Solo se pueden aprobar prefacturas en borrador")
    pf.estado = "aprobada"
    await db.commit()
    await db.refresh(pf)
    nombres = await _nombres_mensajeros(db, {pf.cod_mensajero})
    return _prefactura_to_read(pf, nombres.get(pf.cod_mensajero))


@router.put("/prefacturas/{prefactura_id}/ajuste", response_model=PrefacturaCourierRead)
async def ajustar_monto_prefactura(
    prefactura_id: int,
    body: AjustarMontoRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    pf = await _get_prefactura_or_404(db, prefactura_id)
    if pf.estado != "borrador":
        raise HTTPException(status_code=400, detail="Solo se puede ajustar el monto de prefacturas en borrador")
    pf.valor_ajustado = body.valor_ajustado
    pf.notas_ajuste = body.notas_ajuste
    await db.commit()
    await db.refresh(pf)
    nombres = await _nombres_mensajeros(db, {pf.cod_mensajero})
    return _prefactura_to_read(pf, nombres.get(pf.cod_mensajero))


@router.delete("/prefacturas/{prefactura_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_prefactura(
    prefactura_id: int,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    pf = await _get_prefactura_or_404(db, prefactura_id)
    if pf.estado != "borrador":
        raise HTTPException(status_code=400, detail="Solo se pueden eliminar prefacturas en borrador")
    await db.delete(pf)
    await db.commit()


@router.post("/prefacturas/{prefactura_id}/registrar-factura", response_model=FacturaCourierCxpRead)
async def registrar_factura(
    prefactura_id: int,
    body: RegistrarFacturaRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    pf = await _get_prefactura_or_404(db, prefactura_id)
    if pf.estado != "aprobada":
        raise HTTPException(status_code=400, detail="La prefactura debe estar aprobada para registrar la factura")

    existente = (
        await db.execute(select(FacturaCourierCxp).where(FacturaCourierCxp.prefactura_id == prefactura_id))
    ).scalar_one_or_none()
    if existente is not None:
        raise HTTPException(status_code=400, detail="Esta prefactura ya tiene una factura registrada")

    cxp = FacturaCourierCxp(
        prefactura_id=prefactura_id,
        cod_mensajero=pf.cod_mensajero,
        estado="pendiente",
        **body.model_dump(),
    )
    db.add(cxp)
    pf.estado = "facturada"
    await db.commit()
    await db.refresh(cxp)
    nombres = await _nombres_mensajeros(db, {cxp.cod_mensajero})
    return _cxp_to_read(cxp, nombres.get(cxp.cod_mensajero))


# ── Cuentas por pagar ───────────────────────────────────────────────────────────

@router.get("/cxp", response_model=list[FacturaCourierCxpRead])
async def listar_cxp(
    estado: str | None = None,
    cod_mensajero: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    await db.execute(
        text(
            "UPDATE facturas_courier_cxp SET estado = 'vencida' "
            "WHERE estado = 'pendiente' AND fecha_vencimiento < CURRENT_DATE"
        )
    )
    await db.commit()

    q = select(FacturaCourierCxp).order_by(FacturaCourierCxp.fecha_vencimiento)
    if estado:
        q = q.where(FacturaCourierCxp.estado == estado)
    if cod_mensajero:
        q = q.where(FacturaCourierCxp.cod_mensajero == cod_mensajero)
    rows = (await db.execute(q)).scalars().all()
    nombres = await _nombres_mensajeros(db, {r.cod_mensajero for r in rows})
    return [_cxp_to_read(r, nombres.get(r.cod_mensajero)) for r in rows]


async def _get_cxp_or_404(db: AsyncSession, cxp_id: int) -> FacturaCourierCxp:
    cxp = (
        await db.execute(select(FacturaCourierCxp).where(FacturaCourierCxp.id == cxp_id))
    ).scalar_one_or_none()
    if cxp is None:
        raise HTTPException(status_code=404, detail="Factura CxP no encontrada")
    return cxp


@router.post("/cxp/{cxp_id}/pagar", response_model=FacturaCourierCxpRead)
async def pagar_cxp(
    cxp_id: int,
    body: PagarCxpRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    cxp = await _get_cxp_or_404(db, cxp_id)
    if cxp.estado == "pagada":
        raise HTTPException(status_code=400, detail="Esta factura ya está pagada")
    cxp.estado = "pagada"
    cxp.fecha_pago = body.fecha_pago
    if body.notas:
        cxp.notas = body.notas
    await db.commit()
    await db.refresh(cxp)
    nombres = await _nombres_mensajeros(db, {cxp.cod_mensajero})
    return _cxp_to_read(cxp, nombres.get(cxp.cod_mensajero))


@router.put("/cxp/{cxp_id}", response_model=FacturaCourierCxpRead)
async def editar_cxp(
    cxp_id: int,
    body: FacturaCourierCxpUpdate,
    db: AsyncSession = Depends(get_db),
    _=_auth_admin,
):
    cxp = await _get_cxp_or_404(db, cxp_id)
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(cxp, field, val)
    await db.commit()
    await db.refresh(cxp)
    nombres = await _nombres_mensajeros(db, {cxp.cod_mensajero})
    return _cxp_to_read(cxp, nombres.get(cxp.cod_mensajero))
