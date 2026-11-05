import api from "@/api/client";
import type { DestinoPaquete } from "@/api/tulas";
import { kvGuardar, kvLeer } from "./idb";

/**
 * La base de despacho de los últimos días guardada en el celular, para mostrar el destino
 * de cada paquete al instante aunque no haya señal. Se actualiza con ETag: si no cambió,
 * el servidor responde 304 sin mandar nada.
 */
type PaqueteBase = { s: string; z: string | null; l: string | null; d: string | null };
export type PersonaBase = { codigo: string; nombre: string; nombre_imile: string | null };

type BaseGuardada = {
  etag: string;
  fecha: string;
  paquetes: PaqueteBase[];
  personal: PersonaBase[];
  zonas: string[];
  actualizada: number;
};

const CLAVE = "base";
let enMemoria: { base: BaseGuardada; porSerial: Map<string, PaqueteBase> } | null = null;

function cargarEnMemoria(base: BaseGuardada) {
  enMemoria = { base, porSerial: new Map(base.paquetes.map((p) => [p.s, p])) };
}

/** Trae la base del servidor si cambió. Sin señal se queda con la guardada. */
export async function actualizarBase(): Promise<void> {
  if (!enMemoria) {
    const guardada = await kvLeer<BaseGuardada>(CLAVE);
    if (guardada) cargarEnMemoria(guardada);
  }
  try {
    const r = await api.get<Omit<BaseGuardada, "etag" | "actualizada">>("/paquetes-despacho/base", {
      headers: enMemoria ? { "If-None-Match": enMemoria.base.etag } : {},
      validateStatus: (s) => s === 200 || s === 304,
      timeout: 20_000,
    });
    if (r.status === 304 || !r.data) return;
    const base: BaseGuardada = { ...r.data, etag: String(r.headers["etag"] ?? ""), actualizada: Date.now() };
    cargarEnMemoria(base);
    await kvGuardar(CLAVE, base);
  } catch {
    // Sin señal o sin permiso: se sigue con lo que haya
  }
}

export function baseCargada(): boolean {
  return enMemoria !== null;
}

/** Destino según la base del celular (provisional: el servidor confirma al sincronizar). */
export function destinoLocal(serialCrudo: string): DestinoPaquete | null {
  if (!enMemoria) return null;
  const serial = serialCrudo.trim();
  const p = enMemoria.porSerial.get(serial);
  const ultimos_4 = serial.slice(-4);
  if (!p) {
    return {
      serial, ultimos_4, en_tabla: false, direccion: null, direccion_estandarizada: null,
      localidad: null, zona: null, fuera_de_zona: false, aviso: "No está en la tabla",
    };
  }
  return {
    serial, ultimos_4, en_tabla: true, direccion: p.d, direccion_estandarizada: p.d, localidad: p.l,
    zona: p.z, fuera_de_zona: p.z === null, aviso: p.z === null ? "Fuera de zona" : null,
  };
}

export function personaLocal(codigo: string): PersonaBase | null {
  return enMemoria?.base.personal.find((p) => p.codigo === codigo.trim()) ?? null;
}

export function zonasLocales(): string[] {
  return enMemoria?.base.zonas ?? [];
}
