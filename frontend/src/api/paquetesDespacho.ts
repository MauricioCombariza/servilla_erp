import api from "./client";

export interface PaqueteSinSector {
  serial: string;
  direccion: string | null;
}

export interface CargaDespachoResult {
  archivo: string;
  f_emi: string;
  total: number;
  creados: number;
  reemplazados: number;
  sin_sector: PaqueteSinSector[];
  devoluciones: number; // paquetes que no caen en ninguna zona
}

/** detail del 400 cuando al Excel le faltan columnas */
export interface ColumnasFaltantes {
  mensaje: string;
  faltantes: string[];
  columnas_archivo: string[];
}

export interface PaqueteDespacho {
  serial: string;
  nombre: string | null;
  telefono: string | null;
  direccion: string | null;
  direccion_estandarizada: string | null;
  codigo_postal: string | null;
  localidad: string | null;
  zona: string | null;
  f_emi: string;
  estado: string;
  fecha_modificacion: string;
}

export const paquetesDespachoApi = {
  cargar: (file: File, fEmi: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("f_emi", fEmi);
    return api.post<CargaDespachoResult>("/paquetes-despacho/cargar", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  sinSector: (fEmi: string) =>
    api.get<PaqueteDespacho[]>("/paquetes-despacho/", { params: { f_emi: fEmi, solo_sin_sector: true } }),

  /** Excel de devoluciones del día (fuera de zona): serial, nombre, telefono, direccion, localidad */
  devolucionesExcel: (fEmi: string) =>
    api.get("/paquetes-despacho/devoluciones", { params: { f_emi: fEmi }, responseType: "blob" }),

  corregirDireccion: (serial: string, direccion: string) =>
    api.patch<PaqueteDespacho>(`/paquetes-despacho/${encodeURIComponent(serial)}/direccion`, { direccion }),
};
