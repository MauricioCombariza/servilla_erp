import api from "./client";

export interface Devolucion {
  id: number;
  serial: string;
  nombre: string | null;
  telefono: string | null;
  direccion: string | null;
  localidad: string | null;
  estado: string;
  fecha_carga: string;
  fecha_actualizacion: string;
}

export interface CargaMasivaDevolucionesResult {
  total_filas: number;
  nuevas: number;
  actualizadas: number;
  errores: string[];
}

export const devolucionesApi = {
  list: (params?: { estado?: string; q?: string; limit?: number; offset?: number }) =>
    api.get<Devolucion[]>("/devoluciones/", { params }),

  cargaMasiva: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<CargaMasivaDevolucionesResult>("/devoluciones/carga-masiva", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  updateEstado: (id: number, estado: string) =>
    api.patch<Devolucion>(`/devoluciones/${id}`, { estado }),

  escanearSerial: (serial: string) =>
    api.patch<Devolucion>(`/devoluciones/serial/${encodeURIComponent(serial)}`, {
      estado: "devolucion",
    }),

  generarDocumento: (
    items: { serial: string; nombre: string | null; direccion: string | null; localidad: string | null }[]
  ) => api.post("/devoluciones/documento", { items }, { responseType: "blob" }),
};
