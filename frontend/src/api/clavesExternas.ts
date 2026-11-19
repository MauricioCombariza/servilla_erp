import api from "./client";

/** Cuenta de un sistema fuera del ERP. Solo metadatos: la clave nunca pasa por el ERP. */
export interface ClaveExterna {
  id: number;
  aplicacion: string;
  sistema: string | null;
  usuario: string;
  categoria: string;
  periodicidad_dias: number | null;
  custodio_1: string | null;
  custodio_2: string | null;
  sobre_no: string | null;
  cofre_no: string | null;
  ambiente: string | null;
  notas: string | null;
  ultimo_cambio: string | null;
  activo: boolean;
  periodicidad_efectiva: number;
  vence_en: string | null;
  dias_restantes: number | null;
  estado: "al_dia" | "por_vencer" | "vencida" | "sin_registro";
}

export type ClaveExternaDatos = Omit<
  ClaveExterna, "id" | "activo" | "periodicidad_efectiva" | "vence_en" | "dias_restantes" | "estado"
>;

export interface CambioClaveExterna {
  id: number;
  clave_id: number;
  fecha: string;
  responsable: string;
  sobre_no: string | null;
  observacion: string | null;
}

export interface CategoriaClave { clave: string; nombre: string; dias: number }
export interface ResumenClaves { vencidas: number; por_vencer: number; sin_registro: number }

const URL = "/admin/claves-externas";

export const clavesExternasApi = {
  list: () => api.get<ClaveExterna[]>(URL),
  categorias: () => api.get<CategoriaClave[]>(`${URL}/categorias`),
  resumen: () => api.get<ResumenClaves>(`${URL}/resumen`),
  create: (d: Partial<ClaveExternaDatos>) => api.post<ClaveExterna>(URL, d),
  update: (id: number, d: Partial<ClaveExternaDatos & { activo: boolean }>) => api.put<ClaveExterna>(`${URL}/${id}`, d),
  historial: (id: number) => api.get<CambioClaveExterna[]>(`${URL}/${id}/cambios`),
  registrarCambio: (id: number, d: Omit<CambioClaveExterna, "id" | "clave_id">) =>
    api.post<ClaveExterna>(`${URL}/${id}/cambios`, d),
};
