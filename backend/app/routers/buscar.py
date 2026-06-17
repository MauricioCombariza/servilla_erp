import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.gestiones import SerialGestion
from app.schemas.buscar import BuscarResultado, PaqueteItem
from app.services.bases_web import buscar_histo

router = APIRouter(prefix="/api/buscar", tags=["buscar"])
_auth = Depends(require_role("administrador", "logistica", "mensajero"))

LIMIT = 100


def _fmt_date(d) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _histo_row_to_item(row: dict) -> PaqueteItem:
    f_emi = row.get("f_emi")
    fecha = _fmt_date(f_emi) if f_emi else None
    return PaqueteItem(
        clave=str(row.get("serial") or ""),
        fuente="Histórico",
        nombre=str(row.get("nombred") or "").strip().title() or None,
        direccion=str(row.get("dirdes1") or "").strip() or None,
        ciudad=str(row.get("ciudad1") or "").strip().title() or None,
        fecha=fecha,
        cod_men=str(row.get("cod_men") or "").strip() or None,
        estado=str(row.get("cod_esc") or "").strip() or None,
    )


def _sg_to_item(sg: SerialGestion) -> PaqueteItem:
    cliente_nombre = sg.cliente.nombre_empresa if sg.cliente else None
    mensajero = (
        sg.mensajero.nombre_completo if sg.mensajero else sg.cod_men or None
    )
    return PaqueteItem(
        clave=sg.serial,
        fuente="ERP",
        nombre=None,
        direccion=None,
        ciudad=sg.ciudad,
        fecha=_fmt_date(sg.f_emi),
        cod_men=mensajero,
        estado=sg.estado,
        cliente=cliente_nombre,
        planilla=sg.planilla,
        tipo_gestion=sg.tipo_gestion,
    )


@router.get("/paquete", response_model=BuscarResultado)
async def buscar_paquete(
    q: str = Query(min_length=2, max_length=200),
    modo: str = Query(default="serial", pattern="^(serial|nombre|telefono)$"),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    q = q.strip()
    items: list[PaqueteItem] = []

    if modo == "serial":
        # Buscar en paralelo: histórico MySQL y ERP PostgreSQL
        histo_task = buscar_histo(q, "serial")
        erp_stmt = (
            select(SerialGestion)
            .where(SerialGestion.serial.ilike(f"%{q}%"))
            .order_by(SerialGestion.f_emi.desc())
            .limit(LIMIT)
        )
        histo_rows, erp_result = await asyncio.gather(
            histo_task,
            db.execute(erp_stmt),
        )
        histo_items = [_histo_row_to_item(r) for r in histo_rows]
        erp_items = [_sg_to_item(r) for r in erp_result.scalars().all()]

        # Merge: ERP primero, luego histórico sin duplicar serial
        seen_serials: set[str] = set()
        for item in erp_items:
            seen_serials.add(item.clave)
            items.append(item)
        for item in histo_items:
            if item.clave not in seen_serials:
                seen_serials.add(item.clave)
                items.append(item)

    elif modo == "nombre":
        histo_rows = await buscar_histo(q, "nombre")
        items = [_histo_row_to_item(r) for r in histo_rows]

    elif modo == "telefono":
        # El histórico no tiene teléfono — sin resultados
        items = []

    n_historico = sum(1 for i in items if i.fuente == "Histórico")
    n_erp = sum(1 for i in items if i.fuente == "ERP")

    return BuscarResultado(
        total=len(items),
        historico=n_historico,
        erp=n_erp,
        items=items,
    )
