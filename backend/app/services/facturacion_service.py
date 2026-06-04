"""
Lógica de negocio de facturación.

Invariantes:
- saldo_pendiente nunca queda negativo al registrar un pago.
- Al crear una factura emitida, las ordenes vinculadas se marcan como facturadas.
- Al anular una factura emitida, las ordenes vinculadas se desmarcan.
- estado = 'pagada' cuando saldo_pendiente <= 0; 'parcial' cuando saldo < total; 'pendiente' si no hubo pagos.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.facturacion import (
    DetalleFacturaEmitida,
    DetalleFacturaRecibida,
    FacturaEmitida,
    FacturaRecibida,
    PagoRealizado,
    PagoRecibido,
)
from app.schemas.facturacion import (
    FacturaEmitidaCreate,
    FacturaRecibidaCreate,
    PagoCreate,
    ResumenFinanciero,
)


# ── Facturas emitidas ──────────────────────────────────────────────────────────

async def crear_factura_emitida(
    body: FacturaEmitidaCreate, db: AsyncSession, usuario_id: int | None = None
) -> FacturaEmitida:
    """Crea la factura + detalles, y marca las órdenes vinculadas como facturadas."""

    # Verificar que las órdenes no estén ya en otra factura activa
    if body.ordenes_ids:
        rows = (
            await db.execute(
                text("""
                    SELECT o.numero_orden, fe.numero_factura
                    FROM detalle_facturas_emitidas dfe
                    JOIN facturas_emitidas fe ON dfe.factura_id = fe.id
                    JOIN ordenes o ON dfe.orden_id = o.id
                    WHERE dfe.orden_id = ANY(:ids) AND fe.estado != 'anulada'
                """),
                {"ids": body.ordenes_ids},
            )
        ).fetchall()
        if rows:
            dup = ", ".join(f"{r[0]} → {r[1]}" for r in rows)
            raise ValueError(f"Órdenes ya vinculadas a otra factura: {dup}")

    factura = FacturaEmitida(
        numero_factura=body.numero_factura,
        cliente_id=body.cliente_id,
        fecha_emision=body.fecha_emision,
        fecha_vencimiento=body.fecha_vencimiento,
        periodo_mes=body.periodo_mes,
        periodo_anio=body.periodo_anio,
        cantidad_items=body.cantidad_items,
        subtotal=body.subtotal,
        descuento=body.descuento,
        total=body.total,
        saldo_pendiente=body.total,
        estado="pendiente",
        observaciones=body.observaciones,
    )
    db.add(factura)
    await db.flush()  # necesitamos el id antes de los detalles

    # Detalle principal / detalles proporcionados
    if body.detalles:
        for d in body.detalles:
            db.add(DetalleFacturaEmitida(factura_id=factura.id, **d.model_dump()))
    else:
        # Detalle genérico si no se proporcionaron ítems
        db.add(
            DetalleFacturaEmitida(
                factura_id=factura.id,
                descripcion=body.observaciones or f"Facturación {body.periodo_mes}/{body.periodo_anio}",
                cantidad=body.cantidad_items,
                precio_unitario=body.total / max(body.cantidad_items, 1),
                subtotal=body.total,
            )
        )

    # Vincular órdenes y marcarlas como facturadas
    for orden_id in body.ordenes_ids:
        db.add(
            DetalleFacturaEmitida(
                factura_id=factura.id,
                orden_id=orden_id,
                descripcion=f"Orden #{orden_id}",
                cantidad=1,
                precio_unitario=0,
                subtotal=0,
            )
        )
        await db.execute(
            text("UPDATE ordenes SET facturado = TRUE WHERE id = :id"),
            {"id": orden_id},
        )

    await db.commit()
    await db.refresh(factura)
    return factura


async def registrar_pago_recibido(
    factura: FacturaEmitida, body: PagoCreate, db: AsyncSession, usuario_id: int | None = None
) -> tuple[PagoRecibido, FacturaEmitida]:
    """Registra el pago y actualiza saldo_pendiente + estado."""
    monto_efectivo = min(body.monto, float(factura.saldo_pendiente))

    pago = PagoRecibido(
        factura_id=factura.id,
        fecha_pago=body.fecha_pago,
        monto=monto_efectivo,
        metodo_pago=body.metodo_pago,
        referencia=body.referencia,
        observaciones=body.observaciones,
        usuario_registro_id=usuario_id,
    )
    db.add(pago)

    nuevo_saldo = max(float(factura.saldo_pendiente) - monto_efectivo, 0)
    factura.saldo_pendiente = nuevo_saldo
    factura.estado = "pagada" if nuevo_saldo <= 0 else "parcial"

    await db.commit()
    await db.refresh(factura)
    await db.refresh(pago)
    return pago, factura


async def anular_factura_emitida(factura: FacturaEmitida, db: AsyncSession) -> None:
    """Anula la factura y desmarca sus órdenes vinculadas."""
    for detalle in factura.detalles:
        if detalle.orden_id:
            await db.execute(
                text("UPDATE ordenes SET facturado = FALSE WHERE id = :id"),
                {"id": detalle.orden_id},
            )
    factura.estado = "anulada"
    await db.commit()


# ── Facturas recibidas ─────────────────────────────────────────────────────────

async def crear_factura_recibida(
    body: FacturaRecibidaCreate, db: AsyncSession
) -> FacturaRecibida:
    factura = FacturaRecibida(
        numero_factura=body.numero_factura,
        personal_id=body.personal_id,
        tipo=body.tipo,
        fecha_recepcion=body.fecha_recepcion,
        fecha_vencimiento=body.fecha_vencimiento,
        periodo_mes=body.periodo_mes,
        periodo_anio=body.periodo_anio,
        cantidad_items=body.cantidad_items,
        subtotal=body.subtotal,
        descuento=body.descuento,
        total=body.total,
        saldo_pendiente=body.total,
        estado="pendiente",
        observaciones=body.observaciones,
    )
    db.add(factura)
    await db.flush()

    for d in body.detalles:
        # DetalleFacturaRecibida no tiene orden_id — se excluye del dict
        db.add(DetalleFacturaRecibida(
            factura_id=factura.id,
            **d.model_dump(exclude={"orden_id"}),
        ))

    await db.commit()
    await db.refresh(factura)
    return factura


async def registrar_pago_realizado(
    factura: FacturaRecibida, body: PagoCreate, db: AsyncSession, usuario_id: int | None = None
) -> tuple[PagoRealizado, FacturaRecibida]:
    monto_efectivo = min(body.monto, float(factura.saldo_pendiente))

    pago = PagoRealizado(
        factura_id=factura.id,
        fecha_pago=body.fecha_pago,
        monto=monto_efectivo,
        metodo_pago=body.metodo_pago,
        referencia=body.referencia,
        observaciones=body.observaciones,
        usuario_registro_id=usuario_id,
    )
    db.add(pago)

    nuevo_saldo = max(float(factura.saldo_pendiente) - monto_efectivo, 0)
    factura.saldo_pendiente = nuevo_saldo
    factura.estado = "pagada" if nuevo_saldo <= 0 else "parcial"

    await db.commit()
    await db.refresh(factura)
    await db.refresh(pago)
    return pago, factura


# ── Resumen financiero ────────────────────────────────────────────────────────

async def get_resumen_financiero(db: AsyncSession) -> ResumenFinanciero:
    today = date.today()
    semana = text("CURRENT_DATE + INTERVAL '7 days'")

    async def _scalar(sql: str, params: dict | None = None) -> float:
        r = await db.execute(text(sql), params or {})
        val = r.scalar()
        return float(val or 0)

    total_cobrar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_emitidas WHERE estado NOT IN ('pagada','anulada')"
    )
    vencido_cobrar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_emitidas WHERE estado='vencida'"
    )
    semana_cobrar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_emitidas "
        "WHERE estado IN ('pendiente','parcial') AND fecha_vencimiento BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'"
    )
    total_pagar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_recibidas WHERE estado NOT IN ('pagada','anulada')"
    )
    vencido_pagar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_recibidas "
        "WHERE estado NOT IN ('pagada','anulada') AND fecha_vencimiento < CURRENT_DATE"
    )
    semana_pagar = await _scalar(
        "SELECT SUM(saldo_pendiente) FROM facturas_recibidas "
        "WHERE estado IN ('pendiente','parcial') AND fecha_vencimiento BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'"
    )

    mes = today.month
    anio = today.year
    emitidas_mes = await _scalar(
        "SELECT SUM(total) FROM facturas_emitidas WHERE periodo_mes=:m AND periodo_anio=:a AND estado!='anulada'",
        {"m": mes, "a": anio},
    )
    recibidas_mes = await _scalar(
        "SELECT SUM(total) FROM facturas_recibidas WHERE periodo_mes=:m AND periodo_anio=:a AND estado!='anulada'",
        {"m": mes, "a": anio},
    )

    return ResumenFinanciero(
        total_por_cobrar=total_cobrar,
        total_vencido_cobrar=vencido_cobrar,
        vence_esta_semana_cobrar=semana_cobrar,
        total_por_pagar=total_pagar,
        total_vencido_pagar=vencido_pagar,
        vence_esta_semana_pagar=semana_pagar,
        facturas_emitidas_mes=emitidas_mes,
        facturas_recibidas_mes=recibidas_mes,
    )
