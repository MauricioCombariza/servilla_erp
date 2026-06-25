import api from "./client";
import type {
  NominaEmpleado,
  NominaParametro,
  NominaProvision,
  PagoOperativo,
  PeriodoHistorico,
  ResumenNomina,
  ResumenNominaDetallado,
  RosterEntry,
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

  getResumen: () =>
    api.get<ResumenNominaDetallado>("/nomina/resumen"),

  listHistorico: () =>
    api.get<PeriodoHistorico[]>("/nomina/provisiones/historico"),

  listParametros: () =>
    api.get<NominaParametro[]>("/nomina/parametros"),

  createParametro: (data: { parametro: string; valor: number; descripcion?: string; vigencia_desde: string }) =>
    api.post<NominaParametro>("/nomina/parametros", data),

  updateParametro: (id: number, data: { valor?: number; descripcion?: string; activo?: boolean }) =>
    api.put<NominaParametro>(`/nomina/parametros/${id}`, data),

  listPagos: (params?: { mes?: number; anio?: number }) =>
    api.get<PagoOperativo[]>("/nomina/pagos", { params }),

  upsertPago: (data: Omit<PagoOperativo, "id" | "estado" | "fecha_pago" | "created_at">) =>
    api.post<PagoOperativo>("/nomina/pagos", data),

  marcarPagado: (id: number, fecha_pago: string) =>
    api.put<PagoOperativo>(`/nomina/pagos/${id}/marcar-pagado`, { fecha_pago }),

  deleteProvisiones: (mes: number, anio: number) =>
    api.delete(`/nomina/provisiones`, { params: { mes, anio } }),

  deleteEmpleado: (id: number) =>
    api.delete(`/nomina/empleados/${id}`),

  getRoster: (mes: number, anio: number) =>
    api.get<RosterEntry[]>("/nomina/roster", { params: { mes, anio } }),

  addToRoster: (empleado_id: number, mes: number, anio: number) =>
    api.post<RosterEntry>("/nomina/roster", { empleado_id, mes, anio }),

  removeFromRoster: (entryId: number) =>
    api.delete(`/nomina/roster/${entryId}`),

  inicializarRoster: (mes: number, anio: number) =>
    api.post<RosterEntry[]>("/nomina/roster/inicializar", null, { params: { mes, anio } }),

  copiarMesAnterior: (mes: number, anio: number) =>
    api.post<RosterEntry[]>("/nomina/roster/copiar-mes-anterior", null, { params: { mes, anio } }),
};
