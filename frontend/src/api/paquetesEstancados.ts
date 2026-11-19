import api from "./client";

export interface PaqueteEstancado {
  serial: string;
  zona: string | null;
  localidad: string | null;
  direccion: string | null;
  destinatario: string | null;
  f_emi: string | null;
  primer_ingreso: string;
  dias: number;
  lecturas: number;
  codigo: string | null;
  mensajero: string | null;
  fecha_asignacion: string | null;
  origen_asignacion: "serial" | "zona" | null;
  imile_estado: string | null;
  devolucion: string | null; // estado en devoluciones; null = no está en devolución
  motivo_descarte: string | null; // por qué no es un paquete real (tula, serial cortado…); null = sí lo es
}

export interface GrupoEstancados {
  clave: string; // código del mensajero ("" = sin asignar) o zona ("" = sin zona)
  nombre: string;
  paquetes: number;
  max_dias: number;
}

export interface PaquetesEstancadosResponse {
  corte: string;
  dias_min: number;
  total: number;
  devoluciones_ocultas: number;
  descartados_ocultos: number;
  paquetes: PaqueteEstancado[];
  por_mensajero: GrupoEstancados[];
  por_zona: GrupoEstancados[];
}

export interface FiltrosEstancados {
  zona?: string;
  codigo?: string;
  incluir_devoluciones?: boolean;
  incluir_descartados?: boolean;
}

export const paquetesEstancadosApi = {
  listar: (diasMin = 2, incluirDevoluciones = false, incluirDescartados = false) =>
    api.get<PaquetesEstancadosResponse>("/paquetes-estancados", {
      params: { dias_min: diasMin, incluir_devoluciones: incluirDevoluciones, incluir_descartados: incluirDescartados },
    }),

  descargarExcel: (diasMin: number, filtros: FiltrosEstancados) =>
    api.get("/paquetes-estancados/excel", {
      params: { dias_min: diasMin, ...filtros },
      responseType: "blob",
    }),
};
