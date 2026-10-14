import api from "./client";

export type ClienteDirecciones = "leonisa" | "vehigrupo";

export interface AjusteDireccionesResult {
  total_filas: number;
  total_columnas: number;
  col_direccion: number;
  col_nombre: number | null;
  direcciones_originales: string[];
  filas: string[][];
}

export interface FilaDirNum {
  serial: string;
  direccion: string;
  direccion_ajustada: string;
  dir_num: string;
}

export interface AjusteDirNumResult {
  total_filas: number;
  sin_dir_num: number;
  filas: FilaDirNum[];
}

export const direccionesApi = {
  ajustar: (file: File, cliente: ClienteDirecciones) => {
    const form = new FormData();
    form.append("file", file);
    form.append("cliente", cliente);
    return api.post<AjusteDireccionesResult>("/direcciones/ajustar", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  descargar: (nombreArchivo: string, filas: string[][], cliente: ClienteDirecciones) =>
    api.post(
      "/direcciones/descargar",
      { cliente, nombre_archivo: nombreArchivo, filas },
      { responseType: "blob" },
    ),

  dirnum: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<AjusteDirNumResult>("/direcciones/dirnum", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  descargarDirnum: (nombreArchivo: string, filas: FilaDirNum[]) =>
    api.post(
      "/direcciones/dirnum/descargar",
      { nombre_archivo: nombreArchivo, filas },
      { responseType: "blob" },
    ),
};
