import api from "./client";

export interface AjusteDireccionesResult {
  total_filas: number;
  total_columnas: number;
  col_direccion: number;
  filas: string[][];
}

export const direccionesApi = {
  ajustar: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<AjusteDireccionesResult>("/direcciones/ajustar", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  descargar: (nombreArchivo: string, filas: string[][]) =>
    api.post("/direcciones/descargar", { nombre_archivo: nombreArchivo, filas }, { responseType: "blob" }),
};
