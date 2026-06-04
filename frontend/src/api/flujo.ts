import api from "./client";
import type { FlujoCaja60Dias, ResumenMensualFlujo } from "@/types/domain";

export const flujoApi = {
  flujo60dias: () => api.get<FlujoCaja60Dias[]>("/flujo/"),

  resumenMensual: (anio?: number) =>
    api.get<ResumenMensualFlujo[]>("/flujo/resumen-mensual", {
      params: anio !== undefined ? { anio } : {},
    }),
};
