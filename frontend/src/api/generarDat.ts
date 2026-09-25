import api from "./client";

export type TipoInforme = "centralizado" | "terceros";

export interface SerialError {
  serial: string;
  courrier: string;
}

export interface GenerarDatResult {
  orden: string;
  fecha_ini: string;
  tipo: TipoInforme;
  informe: string;
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
  descargarFormato: () => api.get("/generar-dat/formato", { responseType: "blob" }),

  generar: (orden: string, fechaIni: string, tipo: TipoInforme, informe: string, files: File[]) => {
    const form = new FormData();
    form.append("orden", orden);
    form.append("fecha_ini", fechaIni);
    form.append("tipo", tipo);
    form.append("informe", informe);
    files.forEach((f) => form.append("files", f));
    return api.post<GenerarDatResult>("/generar-dat", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};

export interface SerialPorRevisar {
  serial: string;
  courrier: string;
  motivo: string;
  falta: string;
}

export interface FormatoServillaResult {
  orden: string;
  filas: number;
  excluidos: number;
  nombre: string;
  excel_base64: string;
  por_revisar: SerialPorRevisar[];
}

export const formatoServillaApi = {
  generar: (orden: string) => {
    const form = new FormData();
    form.append("orden", orden);
    return api.post<FormatoServillaResult>("/generar-dat/formato-servilla", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};

export type TipoInformeGlobal = "centralizado" | "entregas";

export interface ItemInformeGlobalInput {
  orden: string;
  nombre: string;
  tipo: TipoInformeGlobal;
  file: File;
}

export interface OperadorInforme {
  operador: string;
  enviada: number;
  entrega: number;
  devoluciones: number;
  dev_iniciales: number;
  nrd: number;
}

export interface ItemInformeGlobal {
  nombre_archivo: string;
  orden: string;
  nombre: string;
  tipo: TipoInformeGlobal;
  registros: number;
  corte: string;
  fecha_minima: string;
  operadores: OperadorInforme[];
  causales: Record<string, number>;
  nombre_excel: string;
  advertencias: string[];
}

export interface InformeGlobalResult {
  items: ItemInformeGlobal[];
  nombre_zip: string;
  zip_base64: string;
}

export const informeGlobalApi = {
  generar: (items: ItemInformeGlobalInput[]) => {
    const form = new FormData();
    form.append("items", JSON.stringify(items.map(({ orden, nombre, tipo }) => ({ orden, nombre, tipo }))));
    items.forEach((it) => form.append("files", it.file));
    return api.post<InformeGlobalResult>("/generar-dat/informe-global", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
