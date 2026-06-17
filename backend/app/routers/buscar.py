from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.clientes import Cliente
from app.models.gestiones import SerialGestion
from app.models.ordenes import Orden
from app.schemas.buscar import BuscarResultado, PaqueteItem

router = APIRouter(prefix="/api/buscar", tags=["buscar"])
_auth = Depends(require_role("administrador", "logistica", "mensajero"))

LIMIT = 100


def _fmt_date(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _serial_to_item(sg: SerialGestion) -> PaqueteItem:
    cliente_nombre = sg.cliente.nombre_empresa if sg.cliente else None
    mensajero_nombre = (
        sg.mensajero.nombre_completo if sg.mensajero else sg.cod_men or None
    )
    return PaqueteItem(
        clave=sg.serial,
        tipo="serial",
        numero_orden=sg.orden,
        cliente=cliente_nombre,
        mensajero=mensajero_nombre,
        ciudad=sg.ciudad,
        fecha=_fmt_date(sg.f_emi),
        estado=sg.estado,
        planilla=sg.planilla,
        tipo_gestion=sg.tipo_gestion,
    )


def _orden_to_item(o: Orden) -> PaqueteItem:
    cliente_nombre = o.cliente.nombre_empresa if o.cliente else None
    return PaqueteItem(
        clave=o.numero_orden,
        tipo="orden",
        numero_orden=o.numero_orden,
        cliente=cliente_nombre,
        mensajero=None,
        ciudad=o.ciudad_destino.nombre if o.ciudad_destino else None,
        fecha=_fmt_date(o.fecha_recepcion),
        estado=o.estado,
        planilla=None,
        tipo_gestion=None,
    )


@router.get("/paquete", response_model=BuscarResultado)
async def buscar_paquete(
    q: str = Query(min_length=2, max_length=200),
    modo: str = Query(default="serial", pattern="^(serial|orden|cliente)$"),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    term = f"%{q.strip()}%"
    items: list[PaqueteItem] = []

    if modo == "serial":
        stmt = (
            select(SerialGestion)
            .where(SerialGestion.serial.ilike(term))
            .order_by(SerialGestion.f_emi.desc())
            .limit(LIMIT)
        )
        rows = (await db.execute(stmt)).scalars().all()
        items = [_serial_to_item(r) for r in rows]

    elif modo == "orden":
        # seriales_gestion with matching orden field
        stmt_sg = (
            select(SerialGestion)
            .where(SerialGestion.orden.ilike(term))
            .order_by(SerialGestion.f_emi.desc())
            .limit(LIMIT)
        )
        sg_rows = (await db.execute(stmt_sg)).scalars().all()
        sg_items = [_serial_to_item(r) for r in sg_rows]

        # ordenes table
        stmt_o = (
            select(Orden)
            .where(Orden.numero_orden.ilike(term))
            .order_by(Orden.fecha_recepcion.desc())
            .limit(LIMIT)
        )
        o_rows = (await db.execute(stmt_o)).scalars().all()
        o_items = [_orden_to_item(r) for r in o_rows]

        # merge, dedup by (clave, tipo)
        seen: set[tuple[str, str]] = set()
        for item in sg_items + o_items:
            key = (item.clave, item.tipo)
            if key not in seen:
                seen.add(key)
                items.append(item)

    elif modo == "cliente":
        palabras = [p for p in q.strip().split() if p]
        stmt = select(SerialGestion).order_by(SerialGestion.f_emi.desc()).limit(LIMIT)
        # filter via joined cliente
        stmt = stmt.join(Cliente, SerialGestion.cliente_id == Cliente.id)
        for palabra in palabras:
            stmt = stmt.where(Cliente.nombre_empresa.ilike(f"%{palabra}%"))
        rows = (await db.execute(stmt)).scalars().all()
        items = [_serial_to_item(r) for r in rows]

    n_seriales = sum(1 for i in items if i.tipo == "serial")
    n_ordenes = sum(1 for i in items if i.tipo == "orden")

    return BuscarResultado(
        total=len(items),
        seriales=n_seriales,
        ordenes=n_ordenes,
        items=items,
    )
