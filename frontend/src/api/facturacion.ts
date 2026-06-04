import api from "./client";

export interface DetalleFactura {
  id?: number;
  orden_id?: number | null;
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
}

export interface Pago {
  id: number;
  factura_id: number;
  fecha_pago: string;
  monto: number;
  metodo_pago: string;
  referencia: string | null;
  observaciones: string | null;
  fecha_creacion: string | null;
}

export interface FacturaEmitida {
  id: number;
  numero_factura: string;
  cliente_id: number;
  cliente: { id: number; nombre_empresa: string; nit: string };
  fecha_emision: string;
  fecha_vencimiento: string;
  periodo_mes: number;
  periodo_anio: number;
  cantidad_items: number;
  subtotal: number;
  descuento: number;
  total: number;
  saldo_pendiente: number;
  estado: "pendiente" | "parcial" | "pagada" | "vencida" | "anulada";
  observaciones: string | null;
  fecha_creacion: string | null;
  detalles: DetalleFactura[];
  pagos: Pago[];
}

export interface FacturaRecibida {
  id: number;
  numero_factura: string;
  personal_id: number;
  personal: { id: number; codigo: string; nombre_completo: string; tipo_personal: string };
  tipo: "courier" | "transportadora" | "materiales" | "otros";
  fecha_recepcion: string;
  fecha_vencimiento: string;
  periodo_mes: number | null;
  periodo_anio: number | null;
  cantidad_items: number;
  subtotal: number;
  descuento: number;
  total: number;
  saldo_pendiente: number;
  estado: "pendiente" | "parcial" | "pagada" | "anulada";
  observaciones: string | null;
  detalles: DetalleFactura[];
  pagos: Pago[];
}

export interface ResumenFinanciero {
  total_por_cobrar: number;
  total_vencido_cobrar: number;
  vence_esta_semana_cobrar: number;
  total_por_pagar: number;
  total_vencido_pagar: number;
  vence_esta_semana_pagar: number;
  facturas_emitidas_mes: number;
  facturas_recibidas_mes: number;
}

export interface CuentaItem {
  id: number;
  tipo: string;
  referencia: string;
  codigo: string | null;
  acreedor_o_deudor: string;
  fecha_vencimiento: string;
  monto: number;
  estado: string;
  dias: number;
  clasificacion: string;
}

export const facturacionApi = {
  // Resumen y cuentas
  resumen: () => api.get<ResumenFinanciero>("/facturacion/resumen"),
  cuentasPorCobrar: () => api.get<CuentaItem[]>("/facturacion/cuentas-por-cobrar"),
  cuentasPorPagar: () => api.get<CuentaItem[]>("/facturacion/cuentas-por-pagar"),

  // Emitidas
  listEmitidas: (params?: { cliente_id?: number; estado?: string; periodo_mes?: number; periodo_anio?: number }) =>
    api.get<FacturaEmitida[]>("/facturacion/emitidas", { params }),
  getEmitida: (id: number) => api.get<FacturaEmitida>(`/facturacion/emitidas/${id}`),
  createEmitida: (data: Partial<FacturaEmitida> & { ordenes_ids?: number[] }) =>
    api.post<FacturaEmitida>("/facturacion/emitidas", data),
  updateEmitida: (id: number, data: Partial<FacturaEmitida>) =>
    api.put<FacturaEmitida>(`/facturacion/emitidas/${id}`, data),
  anularEmitida: (id: number) => api.delete(`/facturacion/emitidas/${id}`),
  registrarPagoEmitida: (id: number, pago: Omit<Pago, "id" | "factura_id" | "fecha_creacion">) =>
    api.post<Pago>(`/facturacion/emitidas/${id}/pagos`, pago),

  // Recibidas
  listRecibidas: (params?: { personal_id?: number; tipo?: string; estado?: string }) =>
    api.get<FacturaRecibida[]>("/facturacion/recibidas", { params }),
  getRecibida: (id: number) => api.get<FacturaRecibida>(`/facturacion/recibidas/${id}`),
  createRecibida: (data: Partial<FacturaRecibida>) =>
    api.post<FacturaRecibida>("/facturacion/recibidas", data),
  updateRecibida: (id: number, data: Partial<FacturaRecibida>) =>
    api.put<FacturaRecibida>(`/facturacion/recibidas/${id}`, data),
  registrarPagoRecibida: (id: number, pago: Omit<Pago, "id" | "factura_id" | "fecha_creacion">) =>
    api.post<Pago>(`/facturacion/recibidas/${id}/pagos`, pago),
};
