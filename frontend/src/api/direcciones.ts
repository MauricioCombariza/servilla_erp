import api from "./client";

export type ClienteDirecciones = "leonisa" | "vehigrupo";

export interface AjusteDireccionesResult {
  total_filas: number;
  total_columnas: number;
  col_direccion: number;
  col_nombre: number | null;
  filas: string[][];
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
};
