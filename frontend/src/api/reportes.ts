import api from "./client";

export interface ResumenClienteRow {
  cliente: string;
  cliente_id: number | null;
  entregas: number;
  devoluciones: number;
  total_seriales: number;
  ingreso_cliente: number;
  costo_mensajero: number;
  margen: number;
  margen_pct: number | null;
}

export interface ResumenMensajeroRow {
  cod_men: string;
  nombre: string | null;
  planillas: number;
  total_seriales: number;
  entregas: number;
  devoluciones: number;
  total_mensajero: number;
}

export interface OrdenReporteRow {
  numero_orden: string;
  cliente: string;
  fecha_recepcion: string;
  cantidad_total: number;
  cantidad_entregados: number;
  cantidad_devolucion: number;
  pendientes: number;
  valor_total: number;
  estado: string;
  pct_gestionado: number;
}

export interface FacturacionClienteRow {
  cliente: string;
  num_facturas: number;
  total_facturado: number;
  total_cobrado: number;
  pendiente: number;
}

export interface TendenciaMesRow {
  mes: string;
  total_seriales: number;
  entregas: number;
  devoluciones: number;
  ingreso_estimado: number;
  costo_mensajero: number;
}

export const reportesApi = {
  operacional: (anio: number, mes?: number) =>
    api.get<ResumenClienteRow[]>("/reportes/operacional", {
      params: { anio, ...(mes ? { mes } : {}) },
    }),

  mensajeros: (fecha_desde: string, fecha_hasta: string) =>
    api.get<ResumenMensajeroRow[]>("/reportes/mensajeros", {
      params: { fecha_desde, fecha_hasta },
    }),

  ordenes: (fecha_desde: string, fecha_hasta: string, cliente_id?: number) =>
    api.get<OrdenReporteRow[]>("/reportes/ordenes", {
      params: { fecha_desde, fecha_hasta, ...(cliente_id ? { cliente_id } : {}) },
    }),

  facturacion: (fecha_desde: string, fecha_hasta: string) =>
    api.get<FacturacionClienteRow[]>("/reportes/facturacion", {
      params: { fecha_desde, fecha_hasta },
    }),

  tendencias: (meses: number) =>
    api.get<TendenciaMesRow[]>("/reportes/tendencias", { params: { meses } }),
};
