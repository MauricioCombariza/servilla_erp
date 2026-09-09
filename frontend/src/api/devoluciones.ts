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
  fecha_escaneo: string | null;
}

export interface DevolucionEscaneo extends Devolucion {
  ya_escaneado: boolean;
  escaneado_previamente_en: string | null;
}

export interface CargaMasivaDevolucionesResult {
  total_filas: number;
  nuevas: number;
  actualizadas: number;
  errores: string[];
}

export interface SerialVerificado {
  serial: string;
  clasificacion: "entrega" | "devolucion" | "ninguna";
  fuente: "seriales_gestion" | "devoluciones" | null;
  estado_detalle: string | null;
  cliente: string | null;
  planilla: string | null;
  cod_men: string | null;
  fecha: string | null;
}

export interface VerificarSerialesResult {
  items: SerialVerificado[];
  total_devoluciones: number;
  total_entregas: number;
  total_ninguna: number;
}

export const devolucionesApi = {
  list: (params?: { estado?: string; q?: string; limit?: number; offset?: number }) =>
    api.get<Devolucion[]>("/devoluciones/", { params }),

  create: (data: {
    serial: string;
    nombre?: string;
    telefono?: string;
    direccion?: string;
    localidad?: string;
    estado?: string;
  }) => api.post<Devolucion>("/devoluciones/", data),

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
    api.patch<DevolucionEscaneo>(`/devoluciones/serial/${encodeURIComponent(serial)}`, {
      estado: "devolucion",
    }),

  escaneadosDia: (fecha?: string) =>
    api.get<Devolucion[]>("/devoluciones/escaneados-dia", {
      params: fecha ? { fecha } : undefined,
    }),

  generarDocumento: (
    items: { serial: string; nombre: string | null; direccion: string | null; localidad: string | null }[]
  ) => api.post("/devoluciones/documento", { items }, { responseType: "blob" }),

  reporteDia: (fecha: string) =>
    api.get("/devoluciones/reporte-dia", { params: { fecha }, responseType: "blob" }),

  reporteDiaWord: (fecha: string) =>
    api.get("/devoluciones/reporte-dia/word", { params: { fecha }, responseType: "blob" }),

  reporteDiaExcel: (fecha: string) =>
    api.get("/devoluciones/reporte-dia/excel", { params: { fecha }, responseType: "blob" }),

  verificarSeriales: (seriales: string[]) =>
    api.post<VerificarSerialesResult>("/devoluciones/verificar-seriales", { seriales }),

  verificarSerialesExcel: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/devoluciones/verificar-seriales-excel", form, {
      headers: { "Content-Type": "multipart/form-data" },
      responseType: "blob",
    });
  },
};
