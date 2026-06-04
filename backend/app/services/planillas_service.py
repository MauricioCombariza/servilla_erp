from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clientes import PrecioCliente
from app.models.gestiones import SerialGestion
from app.schemas.gestiones import (
    CambiarMensajeroRequest,
    PlanillaActionResult,
    PlanillaResumen,
    RecalcularRequest,
    RecalcularResult,
)

logger = logging.getLogger(__name__)


async def resumen_planillas(
    db: AsyncSession,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    cod_men: str | None = None,
) -> list[PlanillaResumen]:
    q = select(SerialGestion)
    if fecha_desde:
        q = q.where(SerialGestion.f_esc >= fecha_desde)
    if fecha_hasta:
        q = q.where(SerialGestion.f_esc <= fecha_hasta)
    if cod_men:
        q = q.where(SerialGestion.cod_men == cod_men)

    seriales = list((await db.execute(q)).scalars().all())

    groups: dict[tuple[str, str], list[SerialGestion]] = {}
    for sg in seriales:
        groups.setdefault((sg.planilla, sg.cod_men), []).append(sg)

    result: list[PlanillaResumen] = []
    for (planilla, cmn), items in groups.items():
        total = len(items)
        entregas = sum(1 for s in items if s.tipo_gestion == "Entrega")
        devoluciones = sum(1 for s in items if s.tipo_gestion == "Devolucion")
        total_cli = sum(float(s.precio_cliente) for s in items)
        total_men = sum(float(s.precio_mensajero) for s in items)
        avg_men = total_men / total if total else 0.0

        estados: dict[str, int] = {}
        for s in items:
            estados[s.estado] = estados.get(s.estado, 0) + 1

        con_precio_cero = sum(1 for s in items if float(s.precio_mensajero) == 0)
        bloqueada = all(s.editado_manualmente for s in items)
        fecha_esc = min((s.f_esc for s in items), default=None)

        first = items[0]
        mensajero_nombre = first.mensajero.nombre_completo if first.mensajero else None

        result.append(
            PlanillaResumen(
                planilla=planilla,
                cod_men=cmn,
                mensajero_nombre=mensajero_nombre,
                mensajero_id=first.mensajero_id,
                fecha_escaner=fecha_esc,
                entregas=entregas,
                devoluciones=devoluciones,
                total_seriales=total,
                total_cliente=round(total_cli, 2),
                total_mensajero=round(total_men, 2),
                precio_promedio_mensajero=round(avg_men, 2),
                estados=estados,
                bloqueada=bloqueada,
                con_precio_cero=con_precio_cero,
            )
        )

    result.sort(key=lambda r: r.fecha_escaner or date.min, reverse=True)
    return result


async def cambiar_mensajero_planilla(
    planilla: str,
    req: CambiarMensajeroRequest,
    db: AsyncSession,
) -> PlanillaActionResult:
    result = await db.execute(
        text("""
            UPDATE seriales_gestion
            SET cod_men = :cod_men,
                mensajero_id = :men_id,
                editado_manualmente = TRUE
            WHERE planilla = :planilla
              AND editado_manualmente = FALSE
        """),
        {"cod_men": req.cod_men, "men_id": req.mensajero_id, "planilla": planilla},
    )
    await db.commit()
    return PlanillaActionResult(planilla=planilla, seriales_actualizados=result.rowcount)


async def cambiar_precio_planilla(
    planilla: str,
    precio_mensajero: float,
    db: AsyncSession,
) -> PlanillaActionResult:
    result = await db.execute(
        text("""
            UPDATE seriales_gestion
            SET precio_mensajero = :precio,
                editado_manualmente = TRUE
            WHERE planilla = :planilla
              AND editado_manualmente = FALSE
        """),
        {"precio": precio_mensajero, "planilla": planilla},
    )
    await db.commit()
    return PlanillaActionResult(planilla=planilla, seriales_actualizados=result.rowcount)


async def bloquear_planilla(planilla: str, db: AsyncSession) -> PlanillaActionResult:
    result = await db.execute(
        text("UPDATE seriales_gestion SET editado_manualmente = TRUE WHERE planilla = :p"),
        {"p": planilla},
    )
    await db.commit()
    return PlanillaActionResult(planilla=planilla, seriales_actualizados=result.rowcount)


async def desbloquear_planilla(planilla: str, db: AsyncSession) -> PlanillaActionResult:
    result = await db.execute(
        text("UPDATE seriales_gestion SET editado_manualmente = FALSE WHERE planilla = :p"),
        {"p": planilla},
    )
    await db.commit()
    return PlanillaActionResult(planilla=planilla, seriales_actualizados=result.rowcount)


async def recalcular_precios(req: RecalcularRequest, db: AsyncSession) -> RecalcularResult:
    rows_p = (
        await db.execute(
            select(
                PrecioCliente.cliente_id,
                PrecioCliente.tipo_servicio,
                PrecioCliente.ambito,
                PrecioCliente.precio_entrega,
                PrecioCliente.costo_mensajero_entrega,
            ).where(PrecioCliente.activo == True)  # noqa: E712
        )
    ).all()

    precios_cli: dict = {}
    precios_men: dict = {}
    for r in rows_p:
        key = (r.cliente_id, r.tipo_servicio.lower(), r.ambito.lower())
        precios_cli[key] = float(r.precio_entrega or 0)
        precios_men[key] = float(r.costo_mensajero_entrega or 0)

    q = select(SerialGestion).where(SerialGestion.editado_manualmente == False)  # noqa: E712
    if req.solo_precio_cero:
        q = q.where(SerialGestion.precio_mensajero == 0)
    if req.fecha_desde:
        q = q.where(SerialGestion.f_esc >= req.fecha_desde)
    if req.fecha_hasta:
        q = q.where(SerialGestion.f_esc <= req.fecha_hasta)
    if req.cliente_id:
        q = q.where(SerialGestion.cliente_id == req.cliente_id)
    if req.cod_men:
        q = q.where(SerialGestion.cod_men == req.cod_men)

    seriales = list((await db.execute(q)).scalars().all())
    actualizados = 0
    sin_precio = 0

    for sg in seriales:
        key = (sg.cliente_id, sg.tipo_envio.lower(), sg.ambito.lower())
        p_men = precios_men.get(key)
        p_cli = precios_cli.get(key)
        if p_men is None:
            sin_precio += 1
        else:
            sg.precio_mensajero = p_men
            if p_cli is not None:
                sg.precio_cliente = p_cli
            actualizados += 1

    await db.commit()
    logger.info("Recalcular: actualizados=%d sin_precio=%d", actualizados, sin_precio)
    return RecalcularResult(
        seriales_actualizados=actualizados,
        seriales_sin_precio=sin_precio,
        errores=[],
    )
