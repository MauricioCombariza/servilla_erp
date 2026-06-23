from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import ARRAY, Numeric, String, bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gestiones import SerialGestion
from app.models.planillas_revisadas import PlanillaRevisada
from app.schemas.gestiones import (
    BloquearRangoRequest,
    BloquearRangoResult,
    BulkPatchRequest,
    BulkPatchResult,
    CambiarMensajeroRequest,
    CiudadGrupo,
    MarcarRevisadaResult,
    PlanillaActionResult,
    PlanillaResumen,
    PrecioCiudadesRequest,
    PrecioCiudadesResult,
    PrecioCourierRequest,
    PrecioCourierResult,
    RecalcularRequest,
    RecalcularResult,
)

logger = logging.getLogger(__name__)


async def resumen_planillas(
    db: AsyncSession,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    cod_men: str | None = None,
    planilla: str | None = None,
) -> list[PlanillaResumen]:
    q = select(SerialGestion)
    if fecha_desde:
        q = q.where(SerialGestion.f_esc >= fecha_desde)
    if fecha_hasta:
        q = q.where(SerialGestion.f_esc <= fecha_hasta)
    if cod_men:
        q = q.where(SerialGestion.cod_men == cod_men)
    if planilla:
        q = q.where(SerialGestion.planilla == planilla)

    seriales = list((await db.execute(q)).scalars().all())

    # Cargar planillas revisadas para lookup O(1)
    revisadas_rows = (await db.execute(select(PlanillaRevisada.lot_esc))).scalars().all()
    revisadas: set[str] = set(revisadas_rows)

    groups: dict[tuple[str, str], list[SerialGestion]] = {}
    for sg in seriales:
        groups.setdefault((sg.planilla, sg.cod_men), []).append(sg)

    result: list[PlanillaResumen] = []
    for (plan, cmn), items in groups.items():
        total = len(items)
        entregas = sum(1 for s in items if s.tipo_gestion == "Entrega")
        devoluciones = sum(1 for s in items if s.tipo_gestion == "Devolucion")
        total_cli = sum(float(s.precio_cliente) for s in items)
        total_men = sum(float(s.precio_mensajero) for s in items)
        avg_men = total_men / total if total else 0.0
        avg_cli = total_cli / total if total else 0.0

        estados: dict[str, int] = {}
        for s in items:
            estados[s.estado] = estados.get(s.estado, 0) + 1

        con_precio_cero = sum(1 for s in items if float(s.precio_mensajero) == 0)
        bloqueada = all(s.editado_manualmente for s in items)
        fecha_esc = min((s.f_esc for s in items), default=None)

        first = items[0]
        mensajero_nombre = first.mensajero.nombre_completo if first.mensajero else None
        mensajero_tipo = first.mensajero.tipo_personal if first.mensajero else None
        precio_local_men = float(first.mensajero.precio_local) if first.mensajero and first.mensajero.precio_local else None
        precio_nac_men = float(first.mensajero.precio_nacional) if first.mensajero and first.mensajero.precio_nacional else None

        result.append(
            PlanillaResumen(
                planilla=plan,
                cod_men=cmn,
                mensajero_nombre=mensajero_nombre,
                mensajero_id=first.mensajero_id,
                tipo_personal=mensajero_tipo,
                fecha_escaner=fecha_esc,
                entregas=entregas,
                devoluciones=devoluciones,
                total_seriales=total,
                total_cliente=round(total_cli, 2),
                total_mensajero=round(total_men, 2),
                precio_promedio_mensajero=round(avg_men, 2),
                precio_promedio_cliente=round(avg_cli, 2),
                estados=estados,
                bloqueada=bloqueada,
                con_precio_cero=con_precio_cero,
                revisada=(plan in revisadas),
                precio_local_mensajero=precio_local_men,
                precio_nacional_mensajero=precio_nac_men,
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
    # Filtros opcionales del WHERE sobre seriales_gestion
    filtros = ["sg.editado_manualmente = FALSE"]
    params: dict = {}

    if req.solo_precio_cero:
        filtros.append("sg.precio_mensajero = 0")
    if req.fecha_desde:
        filtros.append("sg.f_esc >= :fecha_desde")
        params["fecha_desde"] = req.fecha_desde
    if req.fecha_hasta:
        filtros.append("sg.f_esc <= :fecha_hasta")
        params["fecha_hasta"] = req.fecha_hasta
    if req.cliente_id:
        filtros.append("sg.cliente_id = :cliente_id")
        params["cliente_id"] = req.cliente_id
    if req.cod_men:
        filtros.append("sg.cod_men = :cod_men")
        params["cod_men"] = req.cod_men

    where_clause = " AND ".join(filtros)

    # CTE que selecciona, por cada serial candidato, el precio vigente más reciente
    # según (cliente_id, tipo_envio, ambito, f_esc). DISTINCT ON garantiza una fila
    # por serial tomando el precio con vigencia_desde más alta.
    # Regla de precio: entrega y devolución tienen el mismo precio (precio_entrega).
    # Excepción: editado_manualmente=TRUE indica precio especial (ej. motivo 21 = $0)
    # que no debe ser sobreescrito.
    update_sql = text(f"""
        WITH candidatos AS (
            SELECT sg.id,
                   sg.tipo_gestion,
                   sg.precio_cliente,
                   sg.editado_manualmente,
                   sg.cliente_id,
                   sg.tipo_envio,
                   sg.ambito,
                   sg.f_esc,
                   sg.mensajero_id
            FROM seriales_gestion sg
            WHERE {where_clause}
              AND sg.editado_manualmente = FALSE
        ),
        precio_vigente AS (
            SELECT DISTINCT ON (c.id)
                   c.id                          AS serial_id,
                   c.tipo_gestion,
                   c.precio_cliente              AS precio_cli_actual,
                   c.ambito,
                   pc.precio_entrega,
                   pc.costo_mensajero_entrega,
                   pc.costo_mensajero_devolucion,
                   men.tipo_personal             AS tipo_men,
                   men.precio_local              AS men_local,
                   men.precio_nacional           AS men_nac
            FROM candidatos c
            JOIN precios_cliente pc
              ON pc.cliente_id    = c.cliente_id
             AND pc.tipo_servicio = c.tipo_envio
             AND pc.ambito        = c.ambito
             AND pc.activo        = TRUE
             AND pc.vigencia_desde <= c.f_esc
             AND (pc.vigencia_hasta IS NULL OR pc.vigencia_hasta >= c.f_esc)
            LEFT JOIN personal men ON men.id = c.mensajero_id
            ORDER BY c.id, pc.vigencia_desde DESC
        ),
        updated AS (
            UPDATE seriales_gestion sg
            SET precio_cliente   = CASE
                                     WHEN pv.precio_entrega > 0 THEN pv.precio_entrega
                                     ELSE pv.precio_cli_actual
                                   END,
                precio_mensajero = CASE
                                     WHEN pv.tipo_men = 'courier_externo' THEN
                                         CASE pv.ambito
                                             WHEN 'bogota'
                                             THEN COALESCE(NULLIF(pv.men_local, 0), pv.costo_mensajero_entrega)
                                             ELSE COALESCE(NULLIF(pv.men_nac,   0), pv.costo_mensajero_entrega)
                                         END
                                     WHEN pv.tipo_gestion = 'Entrega'
                                     THEN pv.costo_mensajero_entrega
                                     ELSE pv.costo_mensajero_devolucion
                                   END
            FROM precio_vigente pv
            WHERE sg.id = pv.serial_id
            RETURNING sg.id
        )
        SELECT COUNT(*) AS actualizados FROM updated
    """)

    # Seriales sin precio: los que quedan con precio_mensajero = 0 tras el UPDATE
    count_sql = text(f"""
        SELECT COUNT(*) AS sin_precio
        FROM seriales_gestion sg
        WHERE sg.precio_mensajero = 0
          AND {where_clause}
    """)

    result = (await db.execute(update_sql, params)).mappings().one()
    actualizados = int(result["actualizados"])

    sin_precio_row = (await db.execute(count_sql, params)).mappings().one()
    sin_precio = int(sin_precio_row["sin_precio"])

    await db.commit()
    logger.info("Recalcular: actualizados=%d sin_precio=%d", actualizados, sin_precio)
    return RecalcularResult(
        seriales_actualizados=actualizados,
        seriales_sin_precio=sin_precio,
        errores=[],
    )


async def bloquear_por_rango(req: BloquearRangoRequest, db: AsyncSession) -> BloquearRangoResult:
    params: dict = {"fd": req.fecha_desde, "fh": req.fecha_hasta}
    cod_filter = "AND sg.cod_men = :cod_men" if req.cod_men else ""
    if req.cod_men:
        params["cod_men"] = req.cod_men

    result = (
        await db.execute(
            text(f"""
                WITH updated AS (
                    UPDATE seriales_gestion sg
                    SET editado_manualmente = TRUE
                    WHERE sg.f_esc BETWEEN :fd AND :fh
                      {cod_filter}
                    RETURNING sg.planilla
                )
                SELECT COUNT(*) AS seriales, COUNT(DISTINCT planilla) AS planillas
                FROM updated
            """),
            params,
        )
    ).mappings().one()

    await db.commit()
    return BloquearRangoResult(
        seriales_actualizados=int(result["seriales"]),
        planillas_afectadas=int(result["planillas"]),
    )


async def marcar_revisada(planilla: str, revisado_por: str | None, db: AsyncSession) -> MarcarRevisadaResult:
    existing = (
        await db.execute(select(PlanillaRevisada).where(PlanillaRevisada.lot_esc == planilla))
    ).scalar_one_or_none()

    if existing is None:
        db.add(PlanillaRevisada(
            lot_esc=planilla,
            fecha_revision=date.today(),
            revisado_por=revisado_por,
        ))
        await db.commit()

    return MarcarRevisadaResult(planilla=planilla, revisada=True)


async def desmarcar_revisada(planilla: str, db: AsyncSession) -> MarcarRevisadaResult:
    await db.execute(
        delete(PlanillaRevisada).where(PlanillaRevisada.lot_esc == planilla)
    )
    await db.commit()
    return MarcarRevisadaResult(planilla=planilla, revisada=False)


async def cambiar_precio_courier(
    planilla: str,
    req: PrecioCourierRequest,
    db: AsyncSession,
) -> PrecioCourierResult:
    result = (
        await db.execute(
            text("""
                WITH updated AS (
                    UPDATE seriales_gestion
                    SET precio_mensajero = CASE ambito WHEN 'bogota' THEN :pl::numeric ELSE :pn::numeric END,
                        editado_manualmente = TRUE
                    WHERE planilla = :planilla
                    RETURNING ambito
                )
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN ambito = 'bogota' THEN 1 ELSE 0 END) AS bogota,
                    SUM(CASE WHEN ambito != 'bogota' THEN 1 ELSE 0 END) AS nacional
                FROM updated
            """),
            {"pl": req.precio_local, "pn": req.precio_nacional, "planilla": planilla},
        )
    ).mappings().one()
    await db.execute(
        text("""
            UPDATE personal
            SET precio_local    = :pl,
                precio_nacional = :pn
            WHERE id = (
                SELECT mensajero_id FROM seriales_gestion
                WHERE planilla = :planilla AND mensajero_id IS NOT NULL
                LIMIT 1
            )
            AND tipo_personal = 'courier_externo'
        """),
        {"pl": req.precio_local, "pn": req.precio_nacional, "planilla": planilla},
    )
    await db.commit()
    return PrecioCourierResult(
        planilla=planilla,
        seriales_actualizados=int(result["total"]),
        bogota=int(result["bogota"] or 0),
        nacional=int(result["nacional"] or 0),
    )


async def bulk_patch_seriales(req: BulkPatchRequest, db: AsyncSession) -> BulkPatchResult:
    ids = [item.id for item in req.items]
    rows = (await db.execute(
        select(SerialGestion).where(SerialGestion.id.in_(ids))
    )).scalars().all()
    seriales = {sg.id: sg for sg in rows}

    for item in req.items:
        sg = seriales.get(item.id)
        if sg is None:
            continue
        if item.precio_mensajero is not None:
            sg.precio_mensajero = item.precio_mensajero
        if item.precio_cliente is not None:
            sg.precio_cliente = item.precio_cliente
        if item.cod_men is not None:
            sg.cod_men = item.cod_men
        if item.mensajero_id is not None:
            sg.mensajero_id = item.mensajero_id
        sg.editado_manualmente = True

    await db.commit()
    return BulkPatchResult(actualizados=len(ids))


async def recalcular_bloqueados_sin_precio(planilla: str, db: AsyncSession) -> RecalcularResult:
    """Corrige seriales bloqueados (editado_manualmente=TRUE) con precio_mensajero=0.

    Desbloquea temporalmente solo esos seriales, corre el recálculo desde precios_cliente
    y los vuelve a bloquear si recibieron un precio > 0.
    """
    await db.execute(
        text("""
            UPDATE seriales_gestion
            SET editado_manualmente = FALSE
            WHERE planilla = :p AND precio_mensajero = 0 AND editado_manualmente = TRUE
        """),
        {"p": planilla},
    )

    update_sql = text("""
        WITH candidatos AS (
            SELECT sg.id,
                   sg.tipo_gestion,
                   sg.precio_cliente,
                   sg.cliente_id,
                   sg.tipo_envio,
                   sg.ambito,
                   sg.f_esc,
                   sg.mensajero_id
            FROM seriales_gestion sg
            WHERE sg.planilla = :planilla
              AND sg.editado_manualmente = FALSE
              AND sg.precio_mensajero = 0
        ),
        precio_vigente AS (
            SELECT DISTINCT ON (c.id)
                   c.id                          AS serial_id,
                   c.tipo_gestion,
                   c.precio_cliente              AS precio_cli_actual,
                   c.ambito,
                   pc.precio_entrega,
                   pc.costo_mensajero_entrega,
                   pc.costo_mensajero_devolucion,
                   men.tipo_personal             AS tipo_men,
                   men.precio_local              AS men_local,
                   men.precio_nacional           AS men_nac
            FROM candidatos c
            JOIN precios_cliente pc
              ON pc.cliente_id    = c.cliente_id
             AND pc.tipo_servicio = c.tipo_envio
             AND pc.ambito        = c.ambito
             AND pc.activo        = TRUE
             AND pc.vigencia_desde <= c.f_esc
             AND (pc.vigencia_hasta IS NULL OR pc.vigencia_hasta >= c.f_esc)
            LEFT JOIN personal men ON men.id = c.mensajero_id
            ORDER BY c.id, pc.vigencia_desde DESC
        ),
        updated AS (
            UPDATE seriales_gestion sg
            SET precio_cliente   = CASE
                                     WHEN pv.precio_entrega > 0 THEN pv.precio_entrega
                                     ELSE pv.precio_cli_actual
                                   END,
                precio_mensajero = CASE
                                     WHEN pv.tipo_men = 'courier_externo' THEN
                                         CASE pv.ambito
                                             WHEN 'bogota'
                                             THEN COALESCE(NULLIF(pv.men_local, 0), pv.costo_mensajero_entrega)
                                             ELSE COALESCE(NULLIF(pv.men_nac,   0), pv.costo_mensajero_entrega)
                                         END
                                     WHEN pv.tipo_gestion = 'Entrega'
                                     THEN pv.costo_mensajero_entrega
                                     ELSE pv.costo_mensajero_devolucion
                                   END,
                editado_manualmente = TRUE
            FROM precio_vigente pv
            WHERE sg.id = pv.serial_id
            RETURNING sg.id
        )
        SELECT COUNT(*) AS actualizados FROM updated
    """)

    result = (await db.execute(update_sql, {"planilla": planilla})).mappings().one()
    actualizados = int(result["actualizados"])

    sin_precio_row = (await db.execute(
        text("""
            SELECT COUNT(*) AS sin_precio
            FROM seriales_gestion
            WHERE planilla = :planilla AND precio_mensajero = 0
        """),
        {"planilla": planilla},
    )).mappings().one()
    sin_precio = int(sin_precio_row["sin_precio"])

    await db.commit()
    return RecalcularResult(
        seriales_actualizados=actualizados,
        seriales_sin_precio=sin_precio,
        errores=[],
    )


async def ciudades_planilla(planilla: str, db: AsyncSession) -> list[CiudadGrupo]:
    from app.services.bases_web import sync_ciudades_planilla
    await sync_ciudades_planilla(planilla, db)

    rows = (
        await db.execute(
            text("""
                SELECT
                    COALESCE(sg.ciudad, '(Sin ciudad)') AS ciudad,
                    sg.ambito                           AS ambito,
                    COUNT(*)::int                       AS seriales
                FROM seriales_gestion sg
                WHERE sg.planilla = :planilla
                GROUP BY COALESCE(sg.ciudad, '(Sin ciudad)'), sg.ambito
                ORDER BY COUNT(*) DESC
            """),
            {"planilla": planilla},
        )
    ).mappings().all()
    return [CiudadGrupo(ciudad=r["ciudad"], ambito=r["ambito"], seriales=r["seriales"]) for r in rows]


async def precio_por_ciudades(
    planilla: str,
    req: PrecioCiudadesRequest,
    db: AsyncSession,
) -> PrecioCiudadesResult:
    params: dict = {
        "planilla": planilla,
        "pl": req.precio_local,
        "pn": req.precio_nacional,
        "ciudades_local": req.ciudades_local,
        "ciudades_nacional": req.ciudades_nacional,
    }

    sql = text("""
        WITH clasificacion AS (
            SELECT unnest(:ciudades_local)    AS ciudad, 'local'    AS tipo
            UNION ALL
            SELECT unnest(:ciudades_nacional) AS ciudad, 'nacional' AS tipo
        ),
        updated AS (
            UPDATE seriales_gestion sg
            SET precio_mensajero    = CASE cl.tipo WHEN 'local' THEN :pl ELSE :pn END,
                ambito              = CASE cl.tipo WHEN 'local' THEN 'bogota' ELSE 'nacional' END,
                editado_manualmente = TRUE
            FROM clasificacion cl
            WHERE sg.planilla = :planilla
              AND COALESCE(sg.ciudad, '(Sin ciudad)') = cl.ciudad
            RETURNING CASE cl.tipo WHEN 'local' THEN 1 ELSE 0 END AS es_local
        )
        SELECT
            COUNT(*)                 AS total,
            SUM(es_local)            AS local,
            COUNT(*) - SUM(es_local) AS nacional
        FROM updated
    """).bindparams(
        bindparam("ciudades_local",    type_=ARRAY(String)),
        bindparam("ciudades_nacional", type_=ARRAY(String)),
        bindparam("pl",                type_=Numeric),
        bindparam("pn",                type_=Numeric),
    )
    result = (await db.execute(sql, params)).mappings().one()

    await db.execute(
        text("""
            UPDATE personal
            SET precio_local    = :pl,
                precio_nacional = :pn
            WHERE id = (
                SELECT mensajero_id FROM seriales_gestion
                WHERE planilla = :planilla AND mensajero_id IS NOT NULL
                LIMIT 1
            )
            AND tipo_personal = 'courier_externo'
        """),
        {"pl": req.precio_local, "pn": req.precio_nacional, "planilla": planilla},
    )
    await db.commit()
    total = int(result["total"] or 0)
    local = int(result["local"] or 0)
    return PrecioCiudadesResult(
        planilla=planilla,
        seriales_actualizados=total,
        local=local,
        nacional=total - local,
        sin_ciudad=0,
    )
