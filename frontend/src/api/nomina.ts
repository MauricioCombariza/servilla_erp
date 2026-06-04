import api from "./client";
import type {
  NominaEmpleado,
  NominaProvision,
  ResumenNomina,
} from "@/types/domain";

export const nominaApi = {
  listEmpleados: (activo?: boolean) =>
    api.get<NominaEmpleado[]>("/nomina/empleados", {
      params: activo !== undefined ? { activo } : {},
    }),

  createEmpleado: (data: Omit<NominaEmpleado, "id" | "activo" | "fecha_creacion">) =>
    api.post<NominaEmpleado>("/nomina/empleados", data),

  updateEmpleado: (id: number, data: Partial<NominaEmpleado>) =>
    api.put<NominaEmpleado>(`/nomina/empleados/${id}`, data),

  listProvisiones: (params?: { mes?: number; anio?: number; empleado_id?: number }) =>
    api.get<NominaProvision[]>("/nomina/provisiones", { params }),

  calcularProvisiones: (periodo_mes: number, periodo_anio: number) =>
    api.post<ResumenNomina>("/nomina/provisiones/calcular", { periodo_mes, periodo_anio }),
};
