import api from "./client";

export interface GuiaTiempoEntrega {
  serial: string;
  cod_men: string | null;
  mensajero: string | null;
  devoluciones: number | null; // null = tracking sin consultar
  reprogramaciones: number | null; // incluidas en devoluciones; descuentan 5 días
  fecha_inicial: string | null; // llegada a la estación (tracking iMile)
  fecha_entrega: string;
  horas_reales: number | null;
  horas_ajustadas: number | null;
  cumple: boolean | null; // null = falta el tracking
  alertas: AlertaTiempoEntrega[];
}

export type AlertaTiempoEntrega = "sin_tracking" | "negativo" | "mas_7_dias" | "ajuste_al_piso";

export const ETIQUETA_ALERTA: Record<AlertaTiempoEntrega, string> = {
  sin_tracking: "Sin tracking",
  negativo: "Llegada posterior a la entrega",
  mas_7_dias: "Más de 7 días ajustados",
  ajuste_al_piso: "Descuentos mayores al tiempo real",
};

export interface ResumenTiempoEntrega {
  total: number;
  con_tracking: number;
  sin_tracking: number;
  medidas: number; // con tracking y sin datos imposibles: la base del %
  cumplen: number;
  porcentaje_cumple: number | null;
  promedio_horas_reales: number | null;
  promedio_horas_ajustadas: number | null;
  mediana_horas_reales: number | null;
  mediana_horas_ajustadas: number | null;
  p90_horas_reales: number | null;
  p90_horas_ajustadas: number | null;
  con_devoluciones: number;
  porcentaje_con_devoluciones: number | null;
  cumplen_sin_descuento: number;
  porcentaje_cumple_sin_descuento: number | null;
  alertas: Record<AlertaTiempoEntrega, number>;
}

export interface TiempoEntregaResponse {
  desde: string;
  hasta: string;
  ans_horas: number;
  descuento_horas: number;
  descuento_reprogramacion_horas: number;
  resumen: ResumenTiempoEntrega;
  guias: GuiaTiempoEntrega[];
}

export const tiempoEntregaApi = {
  listar: (desde: string, hasta: string) =>
    api.get<TiempoEntregaResponse>("/tiempo-entrega", { params: { desde, hasta } }),

  descargarExcel: (desde: string, hasta: string) =>
    api.get("/tiempo-entrega/excel", { params: { desde, hasta }, responseType: "blob" }),
};
