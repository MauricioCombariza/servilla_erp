"""Seguimiento de tareas y proyectos.

- Día y semana de una tarea: los da `fecha_programada` (semana ISO, lunes a domingo).
- Demorada: sigue abierta (pendiente / en_progreso) y su `fecha_limite` — o, si no tiene,
  su `fecha_programada` — ya pasó (hora de Bogotá).
- Visibilidad: administrador ve todas las tareas; el resto, las que tiene como responsable
  o creó. Los proyectos son del equipo: los ven todos los que tienen la página, y el detalle
  de un proyecto muestra todas sus tareas.
- Recurrentes: las plantillas se materializan perezosamente en tareas_seguimiento hasta la
  fecha que se consulta (tope hoy + HORIZONTE_MAX_DIAS); el UNIQUE (recurrente_id,
  fecha_programada) hace la generación idempotente.
- Reparto de un proyecto: `distribuir` propone una semana por tarea (balanceando el esfuerzo
  o en bloques consecutivos); la propuesta se puede guardar y luego mover a mano.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.seguimiento import Proyecto, TareaRecurrente, TareaSeguimiento
from app.models.usuarios import Usuario
from app.services.calendario_service import es_domingo_o_festivo

TZ = ZoneInfo("America/Bogota")
ROL_ADMIN = "administrador"
ABIERTAS = ("pendiente", "en_progreso")
HORIZONTE_MAX_DIAS = 400


def hoy_bogota() -> date:
    return datetime.now(TZ).date()


# ── Fechas / semanas ISO (funciones puras) ───────────────────────────────────

def semanas_en_anio(anio: int) -> int:
    return date(anio, 12, 28).isocalendar().week


def lunes_iso(anio: int, semana: int) -> date:
    return date.fromisocalendar(anio, semana, 1)


def clave_semana(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def semanas_rango(desde: date, hasta: date) -> list[date]:
    """Lunes de cada semana ISO que toca el rango [desde, hasta]."""
    lunes, fin = lunes_de(desde), lunes_de(hasta)
    out = []
    while lunes <= fin:
        out.append(lunes)
        lunes += timedelta(days=7)
    return out


def primer_dia_habil(lunes: date, desde: date, hasta: date) -> date:
    """Primer día de la semana (lunes a sábado, no festivo) dentro de [desde, hasta]."""
    for i in range(7):
        d = lunes + timedelta(days=i)
        if desde <= d <= hasta and not es_domingo_o_festivo(d):
            return d
    return max(lunes, desde) if max(lunes, desde) <= hasta else hasta


def es_demorada(estado: str, fecha_programada: date, fecha_limite: date | None, hoy: date) -> bool:
    return estado in ABIERTAS and (fecha_limite or fecha_programada) < hoy


def dias_atraso(estado: str, fecha_programada: date, fecha_limite: date | None, hoy: date) -> int:
    if not es_demorada(estado, fecha_programada, fecha_limite, hoy):
        return 0
    return (hoy - (fecha_limite or fecha_programada)).days


@dataclass
class ItemReparto:
    peso: float
    fija: date | None = None


def distribuir(items: list[ItemReparto], desde: date, hasta: date, secuencial: bool = False) -> list[date]:
    """Devuelve una fecha programada por item (mismo orden que `items`).

    - Las fijas conservan su fecha y suman carga a su semana.
    - secuencial=False: de mayor a menor peso, cada una a la semana con menos carga
      (empate → la más temprana). Balancea el esfuerzo.
    - secuencial=True: respeta el orden y reparte en bloques consecutivos proporcionales al
      peso (las primeras tareas en las primeras semanas).
    - La fecha dentro de la semana es su primer día hábil dentro del rango.
    """
    if hasta < desde:
        raise ValueError("rango inválido")
    semanas = semanas_rango(desde, hasta)
    carga = {lun: 0.0 for lun in semanas}
    resultado: list[date | None] = [None] * len(items)

    libres = []
    for i, it in enumerate(items):
        if it.fija is not None:
            resultado[i] = it.fija
            lun = lunes_de(it.fija)
            if lun in carga:
                carga[lun] += it.peso
        else:
            libres.append(i)

    if secuencial:
        total = sum(items[i].peso for i in libres) or 1.0
        acumulado = 0.0
        n = len(semanas)
        for i in libres:
            medio = acumulado + items[i].peso / 2
            idx = min(int(medio / total * n), n - 1)
            acumulado += items[i].peso
            lun = semanas[idx]
            carga[lun] += items[i].peso
            resultado[i] = primer_dia_habil(lun, desde, hasta)
    else:
        for i in sorted(libres, key=lambda j: -items[j].peso):  # sorted es estable
            lun = min(semanas, key=lambda s: (carga[s], s))
            carga[lun] += items[i].peso
            resultado[i] = primer_dia_habil(lun, desde, hasta)

    return resultado  # type: ignore[return-value]


def _ajustar_habil(d: date, limite: date | None) -> date | None:
    while es_domingo_o_festivo(d):
        d += timedelta(days=1)
        if limite and d > limite:
            return None
    return d


def fechas_recurrencia(
    frecuencia: str,
    dias_semana: list[int] | None,
    dia_mes: int | None,
    inicio: date,
    fin: date | None,
    saltar_festivos: bool,
    desde: date,
    hasta: date,
) -> list[date]:
    """Fechas en que toca una plantilla dentro de [desde, hasta].

    diaria/semanal: se saltan domingos y festivos si `saltar_festivos`.
    mensual: el día `dia_mes` (o el último del mes si no existe); si cae domingo/festivo y
    `saltar_festivos`, se corre al siguiente día hábil.
    """
    ini = max(inicio, desde)
    fin_ef = min(fin, hasta) if fin else hasta
    if fin_ef < ini:
        return []
    out: list[date] = []
    if frecuencia in ("diaria", "semanal"):
        dias = set(dias_semana or ([] if frecuencia == "semanal" else range(1, 8)))
        d = ini
        while d <= fin_ef:
            if d.isoweekday() in dias and not (saltar_festivos and es_domingo_o_festivo(d)):
                out.append(d)
            d += timedelta(days=1)
    elif frecuencia == "mensual" and dia_mes:
        y, m = ini.year, ini.month
        while date(y, m, 1) <= fin_ef:
            d = date(y, m, min(dia_mes, calendar.monthrange(y, m)[1]))
            if saltar_festivos:
                d = _ajustar_habil(d, fin)
            if d and ini <= d <= fin_ef:
                out.append(d)
            m += 1
            if m > 12:
                y, m = y + 1, 1
    return out


# ── Acceso y validaciones ────────────────────────────────────────────────────

def es_admin(user: dict) -> bool:
    return user.get("rol") == ROL_ADMIN


def _visible(user: dict):
    if es_admin(user):
        return None
    uid = user.get("id")
    return or_(TareaSeguimiento.responsable_id == uid, TareaSeguimiento.creado_por == uid)


def _puede_editar_tarea(user: dict, t: TareaSeguimiento) -> bool:
    return es_admin(user) or user.get("id") in (t.responsable_id, t.creado_por)


def _puede_editar_proyecto(user: dict, p: Proyecto) -> bool:
    return es_admin(user) or user.get("id") in (p.responsable_id, p.creado_por)


def _prohibido():
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos sobre este registro")


def _no_existe(que: str):
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{que} no existe")


async def _validar_usuario(db: AsyncSession, uid: int | None) -> None:
    if uid is None:
        return
    ok = await db.scalar(select(Usuario.id).where(Usuario.id == uid, Usuario.activo == True))  # noqa: E712
    if not ok:
        raise HTTPException(status_code=400, detail=f"Responsable {uid} no existe o está inactivo")


async def _validar_proyecto(db: AsyncSession, pid: int | None) -> None:
    if pid is None:
        return
    if not await db.scalar(select(Proyecto.id).where(Proyecto.id == pid)):
        raise HTTPException(status_code=400, detail=f"Proyecto {pid} no existe")


async def listar_responsables(db: AsyncSession) -> list[dict]:
    rows = await db.execute(
        select(Usuario.id, Usuario.nombre_completo, Usuario.username)
        .where(Usuario.activo == True)  # noqa: E712
        .order_by(Usuario.nombre_completo)
    )
    return [{"id": r.id, "nombre": r.nombre_completo, "username": r.username} for r in rows]


# ── Recurrentes: materialización ─────────────────────────────────────────────

async def asegurar_recurrentes(db: AsyncSession, hasta: date, hoy: date | None = None) -> int:
    """Genera las tareas de las plantillas activas hasta `hasta`. Devuelve cuántas insertó."""
    hoy = hoy or hoy_bogota()
    hasta = min(hasta, hoy + timedelta(days=HORIZONTE_MAX_DIAS))
    plantillas = (await db.execute(
        select(TareaRecurrente).where(
            TareaRecurrente.activa == True,  # noqa: E712
            TareaRecurrente.fecha_inicio <= hasta,
            or_(TareaRecurrente.generado_hasta.is_(None), TareaRecurrente.generado_hasta < hasta),
            or_(TareaRecurrente.fecha_fin.is_(None),
                TareaRecurrente.generado_hasta.is_(None),
                TareaRecurrente.generado_hasta < TareaRecurrente.fecha_fin),
        )
    )).scalars().all()

    insertadas = 0
    for p in plantillas:
        desde = (p.generado_hasta + timedelta(days=1)) if p.generado_hasta else p.fecha_inicio
        fechas = fechas_recurrencia(p.frecuencia, p.dias_semana, p.dia_mes, p.fecha_inicio, p.fecha_fin,
                                    p.saltar_festivos, desde, hasta)
        if fechas:
            stmt = pg_insert(TareaSeguimiento).values([
                {
                    "titulo": p.titulo, "descripcion": p.descripcion, "proyecto_id": p.proyecto_id,
                    "recurrente_id": p.id, "responsable_id": p.responsable_id, "creado_por": p.creado_por,
                    "fecha_programada": f, "prioridad": p.prioridad, "estado": "pendiente",
                }
                for f in fechas
            ]).on_conflict_do_nothing(constraint="uq_tareas_seg_recurrente_fecha")
            res = await db.execute(stmt)
            insertadas += res.rowcount or 0
        p.generado_hasta = hasta
    if plantillas:
        await db.commit()
    return insertadas


async def _resetear_futuras(db: AsyncSession, rec_id: int, hoy: date) -> None:
    """Borra las tareas futuras aún pendientes de una plantilla (para regenerarlas)."""
    await db.execute(delete(TareaSeguimiento).where(
        TareaSeguimiento.recurrente_id == rec_id,
        TareaSeguimiento.fecha_programada >= hoy,
        TareaSeguimiento.estado == "pendiente",
    ))


# ── Tareas: consultas ────────────────────────────────────────────────────────

_Resp = aliased(Usuario)


def _select_tareas():
    return (
        select(TareaSeguimiento, Proyecto.nombre.label("proyecto_nombre"),
               _Resp.nombre_completo.label("responsable_nombre"))
        .outerjoin(Proyecto, Proyecto.id == TareaSeguimiento.proyecto_id)
        .outerjoin(_Resp, _Resp.id == TareaSeguimiento.responsable_id)
    )


def _to_out(t: TareaSeguimiento, proyecto_nombre: str | None, responsable_nombre: str | None, hoy: date) -> dict:
    iso = t.fecha_programada.isocalendar()
    return {
        "id": t.id, "titulo": t.titulo, "descripcion": t.descripcion,
        "proyecto_id": t.proyecto_id, "proyecto_nombre": proyecto_nombre,
        "recurrente_id": t.recurrente_id,
        "responsable_id": t.responsable_id, "responsable_nombre": responsable_nombre,
        "creado_por": t.creado_por,
        "fecha_programada": t.fecha_programada, "fecha_limite": t.fecha_limite,
        "prioridad": t.prioridad, "estado": t.estado, "esfuerzo_horas": t.esfuerzo_horas,
        "completada_en": t.completada_en,
        "anio_iso": iso.year, "semana_iso": iso.week,
        "demorada": es_demorada(t.estado, t.fecha_programada, t.fecha_limite, hoy),
        "dias_atraso": dias_atraso(t.estado, t.fecha_programada, t.fecha_limite, hoy),
    }


_ORDEN_PRIORIDAD = case(
    {"critica": 0, "alta": 1, "media": 2, "baja": 3}, value=TareaSeguimiento.prioridad, else_=4
)


async def _ejecutar(db: AsyncSession, stmt, hoy: date) -> list[dict]:
    rows = (await db.execute(stmt)).all()
    return [_to_out(r[0], r.proyecto_nombre, r.responsable_nombre, hoy) for r in rows]


def _filtros(user: dict, responsable_id: int | None, proyecto_id: int | None, estado: str | None) -> list:
    conds = []
    vis = _visible(user)
    if vis is not None:
        conds.append(vis)
    if responsable_id is not None:
        conds.append(TareaSeguimiento.responsable_id == responsable_id)
    if proyecto_id is not None:
        conds.append(TareaSeguimiento.proyecto_id == proyecto_id)
    if estado:
        conds.append(TareaSeguimiento.estado == estado)
    return conds


async def listar_tareas(
    db: AsyncSession, user: dict, desde: date, hasta: date, hoy: date,
    responsable_id: int | None = None, proyecto_id: int | None = None, estado: str | None = None,
    incluir_canceladas: bool = False,
) -> list[dict]:
    await asegurar_recurrentes(db, hasta, hoy)
    conds = _filtros(user, responsable_id, proyecto_id, estado)
    conds += [TareaSeguimiento.fecha_programada >= desde, TareaSeguimiento.fecha_programada <= hasta]
    if not incluir_canceladas and not estado:
        conds.append(TareaSeguimiento.estado != "cancelada")
    stmt = _select_tareas().where(and_(*conds)).order_by(
        TareaSeguimiento.fecha_programada, _ORDEN_PRIORIDAD, TareaSeguimiento.id
    )
    return await _ejecutar(db, stmt, hoy)


async def listar_demoradas(
    db: AsyncSession, user: dict, hoy: date,
    responsable_id: int | None = None, proyecto_id: int | None = None,
) -> list[dict]:
    await asegurar_recurrentes(db, hoy, hoy)
    conds = _filtros(user, responsable_id, proyecto_id, None)
    vence = func.coalesce(TareaSeguimiento.fecha_limite, TareaSeguimiento.fecha_programada)
    conds += [TareaSeguimiento.estado.in_(ABIERTAS), vence < hoy]
    stmt = _select_tareas().where(and_(*conds)).order_by(vence, _ORDEN_PRIORIDAD, TareaSeguimiento.id)
    return await _ejecutar(db, stmt, hoy)


async def semana_detalle(db: AsyncSession, user: dict, anio: int, semana: int, hoy: date,
                         responsable_id: int | None = None, proyecto_id: int | None = None) -> dict:
    if not 1 <= semana <= semanas_en_anio(anio):
        raise HTTPException(status_code=400, detail=f"El año {anio} tiene {semanas_en_anio(anio)} semanas")
    lunes = lunes_iso(anio, semana)
    domingo = lunes + timedelta(days=6)
    tareas = await listar_tareas(db, user, lunes, domingo, hoy, responsable_id, proyecto_id)
    dias = [{"fecha": lunes + timedelta(days=i), "tareas": []} for i in range(7)]
    for t in tareas:
        dias[t["fecha_programada"].weekday()]["tareas"].append(t)
    return {"anio": anio, "semana": semana, "lunes": lunes, "domingo": domingo, "dias": dias}


async def semanas_anio(db: AsyncSession, user: dict, anio: int, hoy: date,
                       responsable_id: int | None = None, proyecto_id: int | None = None) -> dict:
    n = semanas_en_anio(anio)
    inicio = lunes_iso(anio, 1)
    fin = lunes_iso(anio, n) + timedelta(days=6)
    await asegurar_recurrentes(db, fin, hoy)

    conds = _filtros(user, responsable_id, proyecto_id, None)
    conds += [TareaSeguimiento.fecha_programada >= inicio, TareaSeguimiento.fecha_programada <= fin,
              TareaSeguimiento.estado != "cancelada"]
    vence = func.coalesce(TareaSeguimiento.fecha_limite, TareaSeguimiento.fecha_programada)
    sem = func.extract("week", TareaSeguimiento.fecha_programada)
    stmt = (
        select(
            sem.label("semana"),
            func.count().label("total"),
            func.count().filter(TareaSeguimiento.estado == "completada").label("completadas"),
            func.count().filter(TareaSeguimiento.estado.in_(ABIERTAS)).label("pendientes"),
            func.count().filter(and_(TareaSeguimiento.estado.in_(ABIERTAS), vence < hoy)).label("demoradas"),
        )
        .where(and_(*conds))
        .group_by(sem)
    )
    por_semana = {int(r.semana): r for r in (await db.execute(stmt)).all()}
    iso_hoy = hoy.isocalendar()
    semanas = []
    for s in range(1, n + 1):
        lun = lunes_iso(anio, s)
        r = por_semana.get(s)
        semanas.append({
            "anio": anio, "semana": s, "lunes": lun, "domingo": lun + timedelta(days=6),
            "total": r.total if r else 0, "completadas": r.completadas if r else 0,
            "pendientes": r.pendientes if r else 0, "demoradas": r.demoradas if r else 0,
            "es_actual": iso_hoy.year == anio and iso_hoy.week == s,
        })
    return {"anio": anio, "semana_actual": iso_hoy.week if iso_hoy.year == anio else None, "semanas": semanas}


async def resumen(db: AsyncSession, user: dict, hoy: date) -> dict:
    lunes = lunes_de(hoy)
    domingo = lunes + timedelta(days=6)
    manana = hoy + timedelta(days=1)
    await asegurar_recurrentes(db, max(domingo, manana), hoy)
    conds = _filtros(user, None, None, None) + [TareaSeguimiento.estado != "cancelada"]
    vence = func.coalesce(TareaSeguimiento.fecha_limite, TareaSeguimiento.fecha_programada)
    f = TareaSeguimiento.fecha_programada
    abierta = TareaSeguimiento.estado.in_(ABIERTAS)
    r = (await db.execute(
        select(
            func.count().filter(and_(f == hoy, abierta)).label("hoy"),
            func.count().filter(and_(f == manana, abierta)).label("manana"),
            func.count().filter(and_(f >= lunes, f <= domingo)).label("semana_total"),
            func.count().filter(and_(f >= lunes, f <= domingo, TareaSeguimiento.estado == "completada"))
            .label("semana_completadas"),
            func.count().filter(and_(abierta, vence < hoy)).label("demoradas"),
        ).where(and_(*conds))
    )).one()
    proyectos = [
        {"id": p["id"], "nombre": p["nombre"], "categoria": p["categoria"],
         "avance": p["avance"], "demoradas": p["demoradas"]}
        for p in await listar_proyectos(db, hoy, solo_activos=True)
    ]
    iso = hoy.isocalendar()
    return {
        "hoy": hoy, "anio_iso": iso.year, "semana_iso": iso.week,
        "tareas_hoy": r.hoy, "tareas_manana": r.manana,
        "semana_total": r.semana_total, "semana_completadas": r.semana_completadas,
        "demoradas": r.demoradas, "proyectos": proyectos,
    }


# ── Tareas: escritura ────────────────────────────────────────────────────────

async def _obtener_tarea(db: AsyncSession, tarea_id: int) -> TareaSeguimiento:
    t = await db.get(TareaSeguimiento, tarea_id)
    if not t:
        raise _no_existe("La tarea")
    return t


async def tarea_out(db: AsyncSession, tarea_id: int, hoy: date) -> dict:
    rows = await _ejecutar(db, _select_tareas().where(TareaSeguimiento.id == tarea_id), hoy)
    if not rows:
        raise _no_existe("La tarea")
    return rows[0]


async def crear_tarea(db: AsyncSession, user: dict, data: dict, hoy: date) -> dict:
    data = dict(data)
    data["responsable_id"] = data.get("responsable_id") or user.get("id")
    await _validar_usuario(db, data["responsable_id"])
    await _validar_proyecto(db, data.get("proyecto_id"))
    t = TareaSeguimiento(**data, creado_por=user.get("id"), estado="pendiente")
    db.add(t)
    await db.commit()
    return await tarea_out(db, t.id, hoy)


def _aplicar_estado(t: TareaSeguimiento, estado: str) -> None:
    if estado == "completada" and t.estado != "completada":
        t.completada_en = datetime.now(TZ)
    elif estado != "completada":
        t.completada_en = None
    t.estado = estado


async def actualizar_tarea(db: AsyncSession, user: dict, tarea_id: int, cambios: dict, hoy: date) -> dict:
    t = await _obtener_tarea(db, tarea_id)
    if not _puede_editar_tarea(user, t):
        raise _prohibido()
    if "responsable_id" in cambios:
        await _validar_usuario(db, cambios["responsable_id"])
    if "proyecto_id" in cambios:
        await _validar_proyecto(db, cambios["proyecto_id"])
    estado = cambios.pop("estado", None)
    for k, v in cambios.items():
        setattr(t, k, v)
    if estado:
        _aplicar_estado(t, estado)
    await db.commit()
    return await tarea_out(db, t.id, hoy)


async def cambiar_estado(db: AsyncSession, user: dict, tarea_id: int, estado: str, hoy: date) -> dict:
    return await actualizar_tarea(db, user, tarea_id, {"estado": estado}, hoy)


async def eliminar_tarea(db: AsyncSession, user: dict, tarea_id: int) -> None:
    t = await _obtener_tarea(db, tarea_id)
    if not _puede_editar_tarea(user, t):
        raise _prohibido()
    if t.recurrente_id is not None:
        # Borrarla haría que se regenerara: se cancela en su lugar.
        t.estado = "cancelada"
        t.completada_en = None
    else:
        await db.delete(t)
    await db.commit()


# ── Proyectos ────────────────────────────────────────────────────────────────

def _stats_proyecto(hoy: date):
    vence = func.coalesce(TareaSeguimiento.fecha_limite, TareaSeguimiento.fecha_programada)
    return (
        select(
            TareaSeguimiento.proyecto_id.label("pid"),
            func.count().filter(TareaSeguimiento.estado != "cancelada").label("total"),
            func.count().filter(TareaSeguimiento.estado == "completada").label("completadas"),
            func.count().filter(and_(TareaSeguimiento.estado.in_(ABIERTAS), vence < hoy)).label("demoradas"),
        )
        .where(TareaSeguimiento.proyecto_id.is_not(None))
        .group_by(TareaSeguimiento.proyecto_id)
        .subquery()
    )


def _proyecto_out(p: Proyecto, responsable_nombre: str | None, total, completadas, demoradas) -> dict:
    total, completadas, demoradas = total or 0, completadas or 0, demoradas or 0
    return {
        "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion, "categoria": p.categoria,
        "responsable_id": p.responsable_id, "responsable_nombre": responsable_nombre,
        "fecha_inicio": p.fecha_inicio, "fecha_fin": p.fecha_fin, "estado": p.estado, "color": p.color,
        "total_tareas": total, "completadas": completadas, "demoradas": demoradas,
        "avance": round(completadas * 100 / total, 1) if total else 0.0,
    }


async def listar_proyectos(db: AsyncSession, hoy: date, categoria: str | None = None,
                           estado: str | None = None, solo_activos: bool = False) -> list[dict]:
    st = _stats_proyecto(hoy)
    stmt = (
        select(Proyecto, _Resp.nombre_completo.label("responsable_nombre"), st.c.total, st.c.completadas,
               st.c.demoradas)
        .outerjoin(st, st.c.pid == Proyecto.id)
        .outerjoin(_Resp, _Resp.id == Proyecto.responsable_id)
    )
    if categoria:
        stmt = stmt.where(Proyecto.categoria == categoria)
    if estado:
        stmt = stmt.where(Proyecto.estado == estado)
    if solo_activos:
        stmt = stmt.where(Proyecto.estado.in_(("planeado", "en_curso")))
    stmt = stmt.order_by(Proyecto.fecha_inicio, Proyecto.id)
    rows = (await db.execute(stmt)).all()
    return [_proyecto_out(r[0], r.responsable_nombre, r.total, r.completadas, r.demoradas) for r in rows]


async def detalle_proyecto(db: AsyncSession, proyecto_id: int, hoy: date) -> dict:
    p = await db.get(Proyecto, proyecto_id)
    if not p:
        raise _no_existe("El proyecto")
    await asegurar_recurrentes(db, p.fecha_fin, hoy)
    stmt = _select_tareas().where(TareaSeguimiento.proyecto_id == proyecto_id).order_by(
        TareaSeguimiento.fecha_programada, _ORDEN_PRIORIDAD, TareaSeguimiento.id
    )
    tareas = await _ejecutar(db, stmt, hoy)
    resp_nombre = await db.scalar(select(Usuario.nombre_completo).where(Usuario.id == p.responsable_id)) \
        if p.responsable_id else None

    vigentes = [t for t in tareas if t["estado"] != "cancelada"]
    inicio = min([p.fecha_inicio] + [t["fecha_programada"] for t in vigentes])
    fin = max([p.fecha_fin] + [t["fecha_programada"] for t in vigentes])
    semanas = []
    for lun in semanas_rango(inicio, fin):
        de_semana = [t for t in vigentes if lunes_de(t["fecha_programada"]) == lun]
        iso = lun.isocalendar()
        semanas.append({
            "anio": iso.year, "semana": iso.week, "lunes": lun, "total": len(de_semana),
            "completadas": sum(t["estado"] == "completada" for t in de_semana),
            "demoradas": sum(t["demorada"] for t in de_semana),
        })
    out = _proyecto_out(
        p, resp_nombre, len(vigentes),
        sum(t["estado"] == "completada" for t in vigentes),
        sum(t["demorada"] for t in vigentes),
    )
    out.update({"semanas": semanas, "tareas": tareas})
    return out


async def crear_proyecto(db: AsyncSession, user: dict, data: dict, hoy: date) -> dict:
    data = dict(data)
    data["responsable_id"] = data.get("responsable_id") or user.get("id")
    await _validar_usuario(db, data["responsable_id"])
    p = Proyecto(**data, creado_por=user.get("id"))
    db.add(p)
    await db.commit()
    return await detalle_proyecto(db, p.id, hoy)


async def actualizar_proyecto(db: AsyncSession, user: dict, proyecto_id: int, cambios: dict, hoy: date) -> dict:
    p = await db.get(Proyecto, proyecto_id)
    if not p:
        raise _no_existe("El proyecto")
    if not _puede_editar_proyecto(user, p):
        raise _prohibido()
    if "responsable_id" in cambios:
        await _validar_usuario(db, cambios["responsable_id"])
    for k, v in cambios.items():
        setattr(p, k, v)
    if p.fecha_fin < p.fecha_inicio:
        raise HTTPException(status_code=400, detail="fecha_fin debe ser posterior o igual a fecha_inicio")
    await db.commit()
    return await detalle_proyecto(db, p.id, hoy)


async def eliminar_proyecto(db: AsyncSession, user: dict, proyecto_id: int) -> None:
    p = await db.get(Proyecto, proyecto_id)
    if not p:
        raise _no_existe("El proyecto")
    if not _puede_editar_proyecto(user, p):
        raise _prohibido()
    await db.delete(p)  # ON DELETE CASCADE a sus tareas y plantillas
    await db.commit()


def _peso(esfuerzo: Decimal | None) -> float:
    return float(esfuerzo) if esfuerzo and esfuerzo > 0 else 1.0


async def distribuir_proyecto(db: AsyncSession, user: dict, proyecto_id: int, req: dict, hoy: date) -> dict:
    p = await db.get(Proyecto, proyecto_id)
    if not p:
        raise _no_existe("El proyecto")
    if req["aplicar"] and not _puede_editar_proyecto(user, p):
        raise _prohibido()
    desde = req.get("fecha_inicio") or p.fecha_inicio
    hasta = req.get("fecha_fin") or p.fecha_fin
    if hasta < desde:
        raise HTTPException(status_code=400, detail="fecha_fin debe ser posterior o igual a fecha_inicio")

    tareas = req["tareas"]
    usa_horas = any(t.get("esfuerzo_horas") for t in tareas)
    items = [ItemReparto(_peso(t.get("esfuerzo_horas")), t.get("fecha_programada")) for t in tareas]
    fechas = distribuir(items, desde, hasta, req["secuencial"])

    for t in tareas:
        if t.get("responsable_id"):
            await _validar_usuario(db, t["responsable_id"])

    carga: dict[str, float] = {clave_semana(lun): 0.0 for lun in semanas_rango(desde, hasta)}
    propuesta = []
    for t, f, it in zip(tareas, fechas, items):
        iso = f.isocalendar()
        carga[clave_semana(f)] = carga.get(clave_semana(f), 0.0) + (it.peso if usa_horas else 1.0)
        propuesta.append({
            "titulo": t["titulo"], "descripcion": t.get("descripcion"),
            "esfuerzo_horas": t.get("esfuerzo_horas"), "prioridad": t.get("prioridad", "media"),
            "responsable_id": t.get("responsable_id") or p.responsable_id,
            "fecha_programada": f, "anio_iso": iso.year, "semana_iso": iso.week,
        })

    if req["aplicar"]:
        for pr in propuesta:
            db.add(TareaSeguimiento(
                titulo=pr["titulo"], descripcion=pr["descripcion"], proyecto_id=p.id,
                responsable_id=pr["responsable_id"], creado_por=user.get("id"),
                fecha_programada=pr["fecha_programada"], prioridad=pr["prioridad"],
                esfuerzo_horas=pr["esfuerzo_horas"], estado="pendiente",
            ))
        await db.commit()

    return {"aplicado": req["aplicar"], "semanas": len(carga), "propuesta": propuesta, "carga_por_semana": carga}


# ── Recurrentes: CRUD ────────────────────────────────────────────────────────

async def listar_recurrentes(db: AsyncSession, user: dict) -> list[TareaRecurrente]:
    stmt = select(TareaRecurrente).order_by(TareaRecurrente.activa.desc(), TareaRecurrente.titulo)
    if not es_admin(user):
        uid = user.get("id")
        stmt = stmt.where(or_(TareaRecurrente.responsable_id == uid, TareaRecurrente.creado_por == uid))
    return list((await db.execute(stmt)).scalars().all())


async def _obtener_recurrente(db: AsyncSession, user: dict, rec_id: int) -> TareaRecurrente:
    r = await db.get(TareaRecurrente, rec_id)
    if not r:
        raise _no_existe("La plantilla")
    if not (es_admin(user) or user.get("id") in (r.responsable_id, r.creado_por)):
        raise _prohibido()
    return r


async def crear_recurrente(db: AsyncSession, user: dict, data: dict) -> TareaRecurrente:
    data = dict(data)
    data["responsable_id"] = data.get("responsable_id") or user.get("id")
    await _validar_usuario(db, data["responsable_id"])
    await _validar_proyecto(db, data.get("proyecto_id"))
    r = TareaRecurrente(**data, creado_por=user.get("id"))
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def actualizar_recurrente(db: AsyncSession, user: dict, rec_id: int, data: dict, hoy: date) -> TareaRecurrente:
    r = await _obtener_recurrente(db, user, rec_id)
    data = dict(data)
    data["responsable_id"] = data.get("responsable_id") or r.responsable_id
    await _validar_usuario(db, data["responsable_id"])
    await _validar_proyecto(db, data.get("proyecto_id"))
    for k, v in data.items():
        setattr(r, k, v)
    await _resetear_futuras(db, r.id, hoy)
    ayer = hoy - timedelta(days=1)
    if r.generado_hasta is not None:
        r.generado_hasta = min(r.generado_hasta, ayer) if r.fecha_inicio <= ayer else None
    await db.commit()
    await db.refresh(r)
    return r


async def eliminar_recurrente(db: AsyncSession, user: dict, rec_id: int, hoy: date) -> None:
    r = await _obtener_recurrente(db, user, rec_id)
    await _resetear_futuras(db, r.id, hoy)
    await db.delete(r)  # las tareas pasadas quedan como historial (recurrente_id → NULL)
    await db.commit()

