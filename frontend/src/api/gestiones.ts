import api from "./client";
import type { PlanillaResumen, SerialGestion } from "@/types/domain";

export interface RecalcularRequest {
  fecha_desde?: string;
  fecha_hasta?: string;
  cliente_id?: number;
  cod_men?: string;
  solo_precio_cero?: boolean;
}

export interface RecalcularResult {
  seriales_actualizados: number;
  seriales_sin_precio: number;
  errores: string[];
}

export interface PlanillaActionResult {
  planilla: string;
  seriales_actualizados: number;
}

export const gestionesApi = {
  list: (params?: {
    planilla?: string;
    cod_men?: string;
    estado?: string;
    cliente_id?: number;
    fecha_desde?: string;
    fecha_hasta?: string;
    limit?: number;
    offset?: number;
  }) => api.get<SerialGestion[]>("/gestiones/", { params }),

  get: (id: number) => api.get<SerialGestion>(`/gestiones/${id}`),

  patch: (id: number, data: Partial<SerialGestion>) =>
    api.patch<SerialGestion>(`/gestiones/${id}`, data),

  planillasResumen: (params?: {
    fecha_desde?: string;
    fecha_hasta?: string;
    cod_men?: string;
  }) => api.get<PlanillaResumen[]>("/gestiones/planillas/resumen", { params }),

  cambiarMensajero: (planilla: string, cod_men: string, mensajero_id?: number) =>
    api.patch<PlanillaActionResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/mensajero`,
      { cod_men, mensajero_id }
    ),

  cambiarPrecio: (planilla: string, precio_mensajero: number) =>
    api.patch<PlanillaActionResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/precio`,
      { precio_mensajero }
    ),

  bloquear: (planilla: string) =>
    api.post<PlanillaActionResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/bloquear`
    ),

  desbloquear: (planilla: string) =>
    api.delete<PlanillaActionResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/bloquear`
    ),

  recalcular: (data: RecalcularRequest) =>
    api.post<RecalcularResult>("/gestiones/recalcular", data),
};
