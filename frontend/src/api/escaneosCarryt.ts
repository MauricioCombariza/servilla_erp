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
};
