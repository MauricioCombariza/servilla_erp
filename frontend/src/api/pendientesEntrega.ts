import api from "./client";

export type TipoPersonalPendientes = "courier_externo" | "mensajero";

export interface DesgloseMesRow {
  mes: string;
  pendientes: number;
}

export interface PendientesEntregaRow {
  cod_men: string;
  nombre: string;
  email: string | null;
  tiene_email: boolean;
  pendientes: number;
  desglose_mensual: DesgloseMesRow[];
}

export interface PendientesEntregaResumen {
  tipo_personal: TipoPersonalPendientes;
  corte_desde: string;
  personas: PendientesEntregaRow[];
}

export interface ResumenMensualRow {
  anomes: string;
  mes: string;
  courier_externo: number;
  mensajero: number;
  total: number;
}

export interface ResumenMensualResponse {
  corte_desde: string;
  meses: ResumenMensualRow[];
}

export const pendientesEntregaApi = {
  resumen: (tipo: TipoPersonalPendientes, diasCorte = 60) =>
    api.get<PendientesEntregaResumen>("/pendientes-entrega/resumen", {
      params: { tipo, dias_corte: diasCorte },
    }),

  resumenMensual: (diasCorte = 60) =>
    api.get<ResumenMensualResponse>("/pendientes-entrega/resumen-mensual", {
      params: { dias_corte: diasCorte },
    }),

  descargarExcel: (codigo: string, tipo: TipoPersonalPendientes, diasCorte = 60) =>
    api.get(`/pendientes-entrega/${codigo}/excel`, {
      params: { tipo, dias_corte: diasCorte },
      responseType: "blob",
    }),

  descargarExcelMensual: (anomes: string, diasCorte = 60) =>
    api.get(`/pendientes-entrega/excel-mensual`, {
      params: { anomes, dias_corte: diasCorte },
      responseType: "blob",
    }),
};
