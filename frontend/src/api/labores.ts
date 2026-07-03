import api from "./client";
import type { RegistroHoras, RegistroLabores, ResumenLabores } from "@/types/domain";

type FiltrosPeriodo = { personal_id?: number; mes?: number; anio?: number; aprobado?: boolean };

export interface HoraBulkItem {
  orden_id: number;
  horas_trabajadas: number;
  tarifa_hora: number;
}

export interface RegistroHorasBulkCreate {
  personal_id: number;
  fecha: string;
  tipo_trabajo: string;
  observaciones?: string | null;
  items: HoraBulkItem[];
}

export const laboresApi = {
  listHoras: (params?: FiltrosPeriodo) =>
    api.get<RegistroHoras[]>("/labores/horas", { params }),

  createHora: (data: Omit<RegistroHoras, "id" | "total" | "aprobado" | "aprobado_por" | "fecha_aprobacion" | "liquidado" | "fecha_creacion">) =>
    api.post<RegistroHoras>("/labores/horas", data),

  createHorasBulk: (data: RegistroHorasBulkCreate) =>
    api.post<{ creados: number }>("/labores/horas/bulk", data),

  updateHora: (id: number, data: Partial<RegistroHoras>) =>
    api.put<RegistroHoras>(`/labores/horas/${id}`, data),

  deleteHora: (id: number) => api.delete(`/labores/horas/${id}`),

  aprobarHora: (id: number) => api.post<RegistroHoras>(`/labores/horas/${id}/aprobar`),

  aprobarHorasLote: (params: { mes?: number; anio?: number; personal_id?: number }) =>
    api.post<{ aprobados: number }>("/labores/horas/aprobar-lote", null, { params }),

  listLabores: (params?: FiltrosPeriodo & { tipo_labor?: string }) =>
    api.get<RegistroLabores[]>("/labores/labores", { params }),

  createLabor: (data: Omit<RegistroLabores, "id" | "total" | "aprobado" | "aprobado_por" | "fecha_aprobacion" | "liquidado" | "fecha_creacion">) =>
    api.post<RegistroLabores>("/labores/labores", data),

  createLaboresBulk: (data: Omit<RegistroLabores, "id" | "total" | "aprobado" | "aprobado_por" | "fecha_aprobacion" | "liquidado" | "fecha_creacion">[]) =>
    api.post<{ creados: number }>("/labores/labores/bulk", data),

  updateLabor: (id: number, data: Partial<RegistroLabores>) =>
    api.put<RegistroLabores>(`/labores/labores/${id}`, data),

  deleteLabor: (id: number) => api.delete(`/labores/labores/${id}`),

  aprobarLabor: (id: number) => api.post<RegistroLabores>(`/labores/labores/${id}/aprobar`),

  aprobarLaboresLote: (params: { mes?: number; anio?: number; personal_id?: number }) =>
    api.post<{ aprobados: number }>("/labores/labores/aprobar-lote", null, { params }),

  resumen: (params?: { mes?: number; anio?: number }) =>
    api.get<ResumenLabores[]>("/labores/resumen", { params }),

  resumenDiario: (params?: { mes?: number; anio?: number; personal_id?: number; aprobado?: boolean; liquidado?: boolean }) =>
    api.get<(ResumenLabores & { fecha: string })[]>("/labores/resumen/diario", { params }),

  lookupPersonalCodigo: (codigo: string) =>
    api.get<{ id: number; nombre_completo: string; identificacion?: string; codigo: string }>(`/personal/by-code/${codigo}`),

  getTarifa: (tipo: string) =>
    api.get<{ tipo_servicio: string; tarifa: number }>(`/labores/tarifas/${tipo}`),
};
