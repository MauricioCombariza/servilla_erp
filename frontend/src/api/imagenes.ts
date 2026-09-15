import api from "./client";

export interface ImagenGuia {
  serial: string;
  encontrado: boolean;
  image_url: string;
  no_entidad: string | null;
  servicio: string | null;
  nombred: string | null;
  dirdes1: string | null;
  ciudad1: string | null;
  cod_sec: string | null;
  retorno: string | null;
  ret_esc: string | null;
  orden: string | null;
  planilla: string | null;
  f_emi: string | null;
  f_lleva: string | null;
  cod_men: string | null;
  dir_num: string | null;
  comentario: string | null;
}

export const imagenesApi = {
  obtenerImagen: (serial: string) =>
    api.get<ImagenGuia>(`/imagenes/${encodeURIComponent(serial)}`),
};
