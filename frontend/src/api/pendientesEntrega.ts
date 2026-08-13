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

export const pendientesEntregaApi = {
  resumen: (tipo: TipoPersonalPendientes, diasCorte = 60) =>
    api.get<PendientesEntregaResumen>("/pendientes-entrega/resumen", {
      params: { tipo, dias_corte: diasCorte },
    }),

  descargarExcel: (codigo: string, tipo: TipoPersonalPendientes, diasCorte = 60) =>
    api.get(`/pendientes-entrega/${codigo}/excel`, {
      params: { tipo, dias_corte: diasCorte },
      responseType: "blob",
    }),
};
