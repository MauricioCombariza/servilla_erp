import api from "./client";

export interface Pendiente {
  personal_id: number; codigo: string; nombre_completo: string; tipo_personal: string;
  total_seriales: number; total_mensajero: number; total_horas: number; total_horas_monto: number;
  total_labores: number; total_labores_monto: number; total_subsidio: number;
  total_pendiente: number; ya_liquidado: boolean;
}

export interface Liquidacion {
  id: number; numero_liquidacion: string; personal_id: number;
  periodo_mes: number; periodo_anio: number; fecha_generacion: string;
  fecha_pago_programada: string; total_entregas: number; cantidad_entregas: number;
  total_horas: number; total_labores: number; total_subsidio: number;
  bonificaciones: number; descuentos: number;
  total_a_pagar: number; estado: string; fecha_pago_real: string | null;
  metodo_pago: string; referencia_pago: string | null; observaciones: string | null;
}

export const liqApi = {
  pendientes: (mes: number, anio: number) =>
    api.get<Pendiente[]>("/liquidaciones/pendientes", { params: { mes, anio } }),
  list: (params: object) => api.get<Liquidacion[]>("/liquidaciones/", { params }),
  generar: (data: object) => api.post<Liquidacion>("/liquidaciones/generar", data),
  aprobar: (id: number) => api.post<Liquidacion>(`/liquidaciones/${id}/aprobar`),
  pagar: (id: number, data: object) => api.post<Liquidacion>(`/liquidaciones/${id}/pagar`, data),
  delete: (id: number) => api.delete(`/liquidaciones/${id}`),
};
