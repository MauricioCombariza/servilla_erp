import axios from "axios";
import api from "./client";

export interface EnlaceVista {
  token: string;
  fecha: string;
  expira: string;
  ruta: string; // "/ver-zonas/<token>"
}

export interface PaqueteVista {
  id: number;
  ultimos_4: string;
  direccion: string | null;
  zona: string | null;
  fuera_de_zona: boolean;
  aviso: string | null; // "Fuera de zona"
  fecha_escaneo: string;
}

export interface PaquetesNuevos {
  paquetes: PaqueteVista[];
  ultimo_id: number; // se manda como `desde` en la siguiente consulta
}

// Quien mira no tiene sesión: cliente sin el interceptor de client.ts (que manda al login)
const publico = axios.create({ baseURL: "/api" });

/** Paso 2.7: una persona escanea y las demás ven, sin iniciar sesión, los paquetes de sus zonas. */
export const vistaZonasApi = {
  /** Quien escanea: crea o devuelve el enlace del día */
  enlace: () => api.post<EnlaceVista>("/escaneo-vista/enlace"),

  zonas: (token: string) => publico.get<string[]>(`/escaneo-vista/${encodeURIComponent(token)}/zonas`),

  paquetes: (token: string, zonas: string[], desde: number) =>
    publico.get<PaquetesNuevos>(`/escaneo-vista/${encodeURIComponent(token)}/paquetes`, {
      params: { zonas: zonas.join(","), desde },
    }),
};
