import api from "./client";

export interface EscaneoCarryt {
  id: number;
  cliente: string;
  fecha: string;
  cod_men: string;
  nombre_mensajero: string;
  serial: string;
  fecha_creacion: string | null;
}

export const escaneosCarrytApi = {
  registrar: (data: { serial: string; cod_men: string; nombre_mensajero: string }) =>
    api.post<EscaneoCarryt>("/escaneos-carryt/", data),

  listarDelDia: (cod_men: string) =>
    api.get<EscaneoCarryt[]>("/escaneos-carryt/", { params: { cod_men } }),

  buscarPorSerial: (serial: string) =>
    api.get<EscaneoCarryt>("/escaneos-carryt/buscar", { params: { serial } }),

  reasignar: (id: number, data: { cod_men: string; nombre_mensajero: string }) =>
    api.patch<EscaneoCarryt>(`/escaneos-carryt/${id}`, data),

  descargarExcelDia: () =>
    api.get("/escaneos-carryt/excel-dia", { responseType: "blob" }),

  descargarExcelRutasUnicas: () =>
    api.get("/escaneos-carryt/excel-rutas-unicas", { responseType: "blob" }),

  descargarExcelRango: (fecha_desde: string, fecha_hasta: string) =>
    api.get("/escaneos-carryt/excel-rango", {
      params: { fecha_desde, fecha_hasta },
      responseType: "blob",
    }),
};
