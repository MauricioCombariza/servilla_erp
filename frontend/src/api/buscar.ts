import api from "./client";

export interface PaqueteItem {
  clave: string;
  tipo: "serial" | "orden";
  numero_orden: string | null;
  cliente: string | null;
  mensajero: string | null;
  ciudad: string | null;
  fecha: string | null;
  estado: string;
  planilla: string | null;
  tipo_gestion: string | null;
}

export interface BuscarResultado {
  total: number;
  seriales: number;
  ordenes: number;
  items: PaqueteItem[];
}

export type BuscarModo = "serial" | "orden" | "cliente";

export const buscarApi = {
  buscarPaquete: (q: string, modo: BuscarModo) =>
    api.get<BuscarResultado>("/buscar/paquete", { params: { q, modo } }),
};
