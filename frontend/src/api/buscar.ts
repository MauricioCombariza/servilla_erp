import api from "./client";

export interface PaqueteItem {
  clave: string;
  fuente: "Histórico" | "ERP";
  nombre: string | null;
  direccion: string | null;
  ciudad: string | null;
  fecha: string | null;
  cod_men: string | null;
  estado: string | null;
  cliente: string | null;
  planilla: string | null;
  tipo_gestion: string | null;
}

export interface BuscarResultado {
  total: number;
  historico: number;
  erp: number;
  items: PaqueteItem[];
}

export type BuscarModo = "serial" | "nombre" | "telefono";

export const buscarApi = {
  buscarPaquete: (q: string, modo: BuscarModo) =>
    api.get<BuscarResultado>("/buscar/paquete", { params: { q, modo } }),
};
