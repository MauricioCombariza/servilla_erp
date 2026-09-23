import api from "./client";

export interface SerialError {
  serial: string;
  courrier: string;
}

export interface GenerarDatResult {
  orden: string;
  fecha_ini: string;
  registros: number;
  seriales_excel: number;
  seriales_orden: number;
  nombre_dat: string;
  dat_base64: string;
  errores: SerialError[];
  nombre_errores: string | null;
  errores_base64: string | null;
  no_encontrados_en_orden: string[];
  duplicados_en_excel: string[];
}

export const generarDatApi = {
  generar: (orden: string, fechaIni: string, files: File[]) => {
    const form = new FormData();
    form.append("orden", orden);
    form.append("fecha_ini", fechaIni);
    files.forEach((f) => form.append("files", f));
    return api.post<GenerarDatResult>("/generar-dat", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
