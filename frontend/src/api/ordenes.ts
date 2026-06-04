import api from "./client";
import type { Orden } from "@/types/domain";

export interface CargaMasivaResult {
  total_filas: number;
  seriales_nuevos: number;
  ordenes_nuevas: number;
  ordenes_actualizadas: number;
  errores: string[];
}

export const ordenesApi = {
  list: (params?: {
    cliente_id?: number;
    estado?: string;
    facturado?: boolean;
    fecha_desde?: string;
    fecha_hasta?: string;
    limit?: number;
    offset?: number;
  }) => api.get<Orden[]>("/ordenes/", { params }),

  get: (id: number) => api.get<Orden>(`/ordenes/${id}`),

  create: (data: Omit<Orden, "id" | "costo_total" | "utilidad_total" | "fecha_creacion" | "fecha_modificacion">) =>
    api.post<Orden>("/ordenes/", data),

  update: (id: number, data: Partial<Orden>) =>
    api.put<Orden>(`/ordenes/${id}`, data),

  anular: (id: number) => api.delete(`/ordenes/${id}`),

  cargaMasiva: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<CargaMasivaResult>("/ordenes/carga-masiva", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
