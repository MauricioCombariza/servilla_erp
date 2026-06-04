import api from "./client";
import type { GastoAdmin, GastoAdminResumen, GastoFijo, PagoGastoFijo } from "@/types/domain";

export const gastosApi = {
  list: (params?: { mes?: number; anio?: number; categoria?: string; estado?: string }) =>
    api.get<GastoAdmin[]>("/gastos/", { params }),

  resumen: (params?: { mes?: number; anio?: number }) =>
    api.get<GastoAdminResumen[]>("/gastos/resumen", { params }),

  create: (data: Omit<GastoAdmin, "id" | "fecha_creacion">) =>
    api.post<GastoAdmin>("/gastos/", data),

  update: (id: number, data: Partial<GastoAdmin>) =>
    api.put<GastoAdmin>(`/gastos/${id}`, data),

  delete: (id: number) => api.delete(`/gastos/${id}`),

  listFijos: (activo?: boolean) =>
    api.get<GastoFijo[]>("/gastos/fijos", { params: activo !== undefined ? { activo } : {} }),

  createFijo: (data: Omit<GastoFijo, "id" | "activo" | "created_at" | "pagos">) =>
    api.post<GastoFijo>("/gastos/fijos", data),

  updateFijo: (id: number, data: Partial<GastoFijo>) =>
    api.put<GastoFijo>(`/gastos/fijos/${id}`, data),

  registrarPagoFijo: (
    gastoFijoId: number,
    data: Omit<PagoGastoFijo, "id" | "gasto_fijo_id" | "created_at">
  ) => api.post<PagoGastoFijo>(`/gastos/fijos/${gastoFijoId}/pagos`, data),
};
