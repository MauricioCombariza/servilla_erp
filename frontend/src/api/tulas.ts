import api from "./client";

/** ok | repetido | bloqueado | error | sin_confirmar | omitido (ingreso en iMile apagado) */
export type ImileEstado = string | null;

export interface Tula {
  id: number;
  codigo: string | null;
  sin_etiqueta: boolean;
  total_esperado: number | null;
  estado: string; // abierta | cerrada
  usuario: string;
  fecha: string;
  fecha_apertura: string;
  fecha_cierre: string | null;
  leidos: number;
  contador: number; // lo que se muestra grande (Paso 2.4): baja con esperado, sube sin etiqueta
  diferencia: number | null; // positiva: faltan · negativa: sobran
}

/** Respuesta al abrir: qué dijo iMile del total (Paso 2.3), si se le preguntó */
export interface TulaAbierta extends Tula {
  imile_total: string | null;
}

export interface TulaSerial {
  serial: string;
  en_tabla: boolean;
  zona: string | null;
  localidad: string | null; // de la base de despacho: se muestra si va fuera de zona
  fecha_escaneo: string;
  imile_estado: ImileEstado;
  imile_mensaje: string | null;
}

export interface TulaDetalle extends Tula {
  seriales: TulaSerial[];
  // Contra lo que iMile dice que trae la tula (Paso 2.3); null si iMile no lo dijo
  faltantes: string[] | null;
  no_esperados: string[] | null;
}

export interface DestinoPaquete {
  serial: string;
  ultimos_4: string;
  en_tabla: boolean;
  direccion: string | null;
  direccion_estandarizada: string | null;
  localidad: string | null;
  zona: string | null;
  fuera_de_zona: boolean;
  aviso: string | null; // "No está en la tabla" | "Fuera de zona"
}

/** Lo leído hoy entre todos los usuarios */
export interface ResumenDelDia {
  fecha: string;
  tulas: number;
  paquetes: number; // cada serial contado una sola vez
}

export interface EscaneoResult {
  tula: Tula;
  destino: DestinoPaquete;
  ya_escaneado: boolean;
  imile: { estado: ImileEstado; mensaje: string | null };
}

/** detail del 409 al abrir una tula con otra abierta */
export interface TulaAbiertaConflicto {
  mensaje: string;
  tula_abierta: Tula;
}

export interface SerialSinLeer {
  serial: string;
  ultimos_4: string;
  zona: string | null;
  localidad: string | null;
  direccion: string | null;
}

/** Paquetes de la base de despacho del día que no se han leído en ninguna tula */
export interface SinLeerDelDia {
  fecha: string;
  total: number;
  seriales: SerialSinLeer[];
}

export const tulasApi = {
  abierta: () => api.get<Tula | null>("/tulas/abierta"),

  /** Paquetes de la base de despacho subidos hoy: 0 = falta subir la base */
  baseDelDia: () => api.get<{ paquetes_hoy: number }>("/tulas/base-del-dia"),

  delDia: () => api.get<ResumenDelDia>("/tulas/del-dia"),

  sinLeer: () => api.get<SinLeerDelDia>("/tulas/sin-leer"),

  detalle: (id: number) => api.get<TulaDetalle>(`/tulas/${id}`),

  abrir: (body: { codigo: string | null; total_esperado?: number | null; cerrar_anterior?: boolean }) =>
    api.post<TulaAbierta>("/tulas/", body),

  fijarTotal: (id: number, totalEsperado: number | null) =>
    api.patch<Tula>(`/tulas/${id}/total`, { total_esperado: totalEsperado }),

  escanear: (id: number, serial: string) => api.post<EscaneoResult>(`/tulas/${id}/seriales`, { serial }),

  reintentarImile: (id: number, serial: string) =>
    api.post<TulaSerial>(`/tulas/${id}/seriales/${encodeURIComponent(serial)}/reintentar-imile`),

  cerrar: (id: number) => api.post<TulaDetalle>(`/tulas/${id}/cerrar`),
};
