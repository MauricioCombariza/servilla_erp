import api from "./client";

export interface Mensajero {
  codigo: string;
  nombre: string;
}

export interface ZonasMensajero extends Mensajero {
  fecha: string;
  zonas: string[];
  nombre_imile: string | null; // si en iMile aparece con otro nombre (Paso 3.3)
}

export interface ZonaDelDia {
  zona: string;
  paquetes_leidos: number;
  mensajero: Mensajero | null;
}

export interface AsignacionSerial {
  serial: string;
  ultimos_4: string;
  zona: string | null;
  mensajero_anterior: Mensajero | null; // a quién lo tenía (por zona o por serial)
  ya_era_suyo: boolean;
}

export interface SerialDelMensajero {
  serial: string;
  ultimos_4: string;
  zona: string | null;
  origen: "zona" | "serial"; // serial = reasignado uno a uno
  imile_estado: string | null; // Paso 3.3: ok | repetido | bloqueado | error | sin_confirmar; null = sin mandar
  imile_mensaje: string | null;
}

/** Avance del envío a iMile ("Asignar repartidor") de los paquetes del mensajero */
export interface EnvioImile {
  nombre_imile: string; // con el que se busca en iMile
  total: number;
  hechos: number;
  asignados: number;
  fallidos: number;
  en_curso: boolean;
  error: string | null;
}

/** Cuántos paquetes lleva cada mensajero en el día (sus zonas + reasignados) */
export interface TotalMensajero extends Mensajero {
  zonas: string[];
  paquetes: number;
  reasignados: number;
}

/** detail del 409 al pedir zonas que ya tiene otro mensajero */
export interface ChoqueZonas {
  mensaje: string;
  choques: { zona: string; codigo: string; nombre: string }[];
}

const m = (codigo: string) => `/asignacion-zonas/mensajero/${encodeURIComponent(codigo)}`;

/** Pasos 3.1 y 3.2 con sesión del ERP: siempre sobre el día de hoy (hora de Bogotá). */
export const asignacionZonasApi = {
  tablero: () => api.get<ZonaDelDia[]>("/asignacion-zonas/"),

  totales: () => api.get<TotalMensajero[]>("/asignacion-zonas/mensajeros"),

  mensajero: (codigo: string) => api.get<ZonasMensajero>(m(codigo)),

  asignar: (codigo: string, zonas: string[], reasignar = false) =>
    api.put<ZonasMensajero>(m(codigo), { zonas, reasignar }),

  asignarSerial: (codigo: string, serial: string) =>
    api.post<AsignacionSerial>(`${m(codigo)}/seriales`, { serial }),

  quitarSerial: (codigo: string, serial: string) =>
    api.delete(`${m(codigo)}/seriales/${encodeURIComponent(serial)}`),

  seriales: (codigo: string) => api.get<SerialDelMensajero[]>(`${m(codigo)}/seriales`),

  /** Paso 3.3: manda a iMile, en segundo plano, los paquetes que le faltan */
  asignarEnImile: (codigo: string) => api.post<EnvioImile>(`${m(codigo)}/imile`),

  envioImile: (codigo: string) => api.get<EnvioImile | null>(`${m(codigo)}/imile`),

  fijarNombreImile: (codigo: string, nombreImile: string | null) =>
    api.put<ZonasMensajero>(`${m(codigo)}/nombre-imile`, { nombre_imile: nombreImile }),
};
