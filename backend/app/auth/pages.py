from dataclasses import dataclass


@dataclass(frozen=True)
class PageDef:
    key: str
    label: str
    path: str


PAGE_CATALOG: list[PageDef] = [
    PageDef("clientes", "Clientes y Precios", "/clientes"),
    PageDef("personal", "Personal", "/personal"),
    PageDef("ordenes", "Órdenes", "/ordenes"),
    PageDef("facturacion_resumen", "Resumen Financiero", "/facturacion"),
    PageDef("facturacion_emitidas", "Facturas Emitidas", "/facturacion/emitidas"),
    PageDef("facturacion_recibidas", "Facturas Recibidas", "/facturacion/recibidas"),
    PageDef("facturacion_cxc", "CxC — Por Cobrar", "/facturacion/cobrar"),
    PageDef("facturacion_cxp", "CxP — Por Pagar", "/facturacion/pagar"),
    PageDef("reportes", "Reportes", "/reportes"),
    PageDef("labores", "Registro Labores", "/labores"),
    PageDef("pagos_mensajeros", "Gestión Pagos", "/pagos-mensajeros"),
    PageDef("facturas_transporte", "Facturas Transporte", "/facturas-transporte"),
    PageDef("pagos_ciudades", "Pagos Ciudades", "/pagos-ciudades"),
    PageDef("gastos", "Gastos Admin", "/gastos"),
    PageDef("flujo_caja", "Flujo de Caja", "/flujo-caja"),
    PageDef("nomina", "Nómina", "/nomina"),
    PageDef("gestiones", "Detalle Gestiones", "/gestiones"),
    PageDef("planillas", "Planillas", "/planillas"),
    PageDef("buscar", "Buscar Paquete", "/buscar"),
    PageDef("direcciones", "Ajuste Direcciones", "/direcciones"),
    PageDef("pendientes_entrega", "Pendientes Entrega", "/pendientes-entrega"),
    PageDef("devoluciones", "Devoluciones", "/devoluciones"),
    PageDef("devoluciones_scan", "Escaneo Devoluciones", "/escaneo-devoluciones"),
    PageDef("escaneo_carryt", "Escaneo Carryt", "/escaneo-carryt"),
    PageDef("imile_offload_scan", "Escaneo Offloading iMile", "/imile-offload-scan"),
    PageDef("geocercas", "Geocercas Barrios Unidos", "/geocercas"),
]

PAGE_KEYS: set[str] = {p.key for p in PAGE_CATALOG}
