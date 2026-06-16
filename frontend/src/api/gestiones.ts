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

export interface BloquearRangoRequest {
  fecha_desde: string;
  fecha_hasta: string;
  cod_men?: string;
}

export interface BloquearRangoResult {
  seriales_actualizados: number;
  planillas_afectadas: number;
}

export interface MarcarRevisadaResult {
  planilla: string;
  revisada: boolean;
}

export interface BulkPatchItem {
  id: number;
  precio_mensajero?: number;
  precio_cliente?: number;
  cod_men?: string;
  mensajero_id?: number;
}

export interface BulkPatchResult {
  actualizados: number;
}

export interface PrecioCourierRequest {
  precio_local: number;
  precio_nacional: number;
}

export interface PrecioCourierResult {
  planilla: string;
  seriales_actualizados: number;
  bogota: number;
  nacional: number;
}

export interface CiudadGrupo {
  ciudad: string;
  ambito: string;  // 'bogota' | 'nacional'
  seriales: number;
}

export interface PrecioCiudadesRequest {
  precio_local: number;
  precio_nacional: number;
  ciudades_local: string[];
  ciudades_nacional: string[];
}

export interface PrecioCiudadesResult {
  planilla: string;
  seriales_actualizados: number;
  local: number;
  nacional: number;
  sin_ciudad: number;
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
    planilla?: string;
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

  bloquearRango: (data: BloquearRangoRequest) =>
    api.post<BloquearRangoResult>("/gestiones/planillas/bloquear-rango", data),

  marcarRevisada: (planilla: string) =>
    api.post<MarcarRevisadaResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/revisar`
    ),

  desmarcarRevisada: (planilla: string) =>
    api.delete<MarcarRevisadaResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/revisar`
    ),

  recalcular: (data: RecalcularRequest) =>
    api.post<RecalcularResult>("/gestiones/recalcular", data),

  bulkPatch: (items: BulkPatchItem[]) =>
    api.patch<BulkPatchResult>("/gestiones/bulk", { items }),

  precioCourier: (planilla: string, data: PrecioCourierRequest) =>
    api.post<PrecioCourierResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/precio-courier`,
      data
    ),

  ciudadesPlanilla: (planilla: string) =>
    api.get<CiudadGrupo[]>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/ciudades`
    ),

  precioCiudades: (planilla: string, data: PrecioCiudadesRequest) =>
    api.post<PrecioCiudadesResult>(
      `/gestiones/planillas/${encodeURIComponent(planilla)}/precio-ciudades`,
      data
    ),
};
