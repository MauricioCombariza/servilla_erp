import { create } from "zustand";
import api from "@/api/client";
import { colaAgregar, colaQuitar, colaReemplazar, colaTodas, type EnCola } from "./idb";

/**
 * Cola de lo que se hace en el celular (abrir tula, leer paquete, cerrar, asignar…).
 *
 * Cada operación se guarda primero en el celular con un op_id único y luego se manda a
 * POST /api/flujo/sync, en orden. Si se corta la señal se reintenta sola (cada vez más
 * espaciado, máx. 30 s) y al volver la señal se manda enseguida. El servidor recuerda
 * cada op_id: reenviar lo mismo nunca duplica nada.
 *
 * Si abrir una tula choca con otra abierta en el servidor (409), la cola se detiene hasta
 * que la persona decida (resolverConflicto); lo leído en esa tula no se pierde.
 */
export type TipoOp =
  | "abrir_tula" | "serial" | "total" | "cerrar_tula"
  | "asignar_zonas" | "asignar_serial" | "quitar_serial";

export type Op = {
  op_id: string;
  tipo: TipoOp;
  tula_local_id?: string;
  tula_id?: number;
  datos?: Record<string, unknown>;
  hora: string;
};

export type ResultadoOp = { op_id: string; status: number; body: unknown };

type RespuestaSync = { resultados: ResultadoOp[]; tulas: Record<string, number>; pendientes: number };

// status 409: había otra tula abierta en el servidor · 422: el código no sirve (p. ej. se
// leyó algo que no es la etiqueta). En los dos casos lo leído después espera a que se decida.
export type Bloqueo = { seq: number; op: Op; status: number; detalle: unknown };

type EstadoCola = {
  pendientes: number;
  enviando: boolean;
  sinSenal: boolean;
  ultimoEnvio: number | null;
  bloqueo: Bloqueo | null;
};

export const useCola = create<EstadoCola>(() => ({
  pendientes: 0, enviando: false, sinSenal: !navigator.onLine, ultimoEnvio: null, bloqueo: null,
}));

const MAX_POR_LOTE = 50;
const ESPERA_MAX_MS = 30_000;

type Oyente = (op: Op, r: ResultadoOp, tulas: Record<string, number>) => void;
const oyentes = new Set<Oyente>();

/** Avisa cada resultado que llega del servidor. Devuelve la función para dejar de oír. */
export function alResultado(fn: Oyente): () => void {
  oyentes.add(fn);
  return () => oyentes.delete(fn);
}

export function nuevoId(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  // Navegadores viejos (o http sin TLS): UUID v4 con getRandomValues
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

async function contar() {
  useCola.setState({ pendientes: (await colaTodas<Op>()).length });
}

export async function encolar(op: Omit<Op, "op_id" | "hora">): Promise<Op> {
  const completa: Op = { ...op, op_id: nuevoId(), hora: new Date().toISOString() };
  await colaAgregar(completa);
  await contar();
  void sincronizar();
  return completa;
}

/** Lo que todavía no ha llegado al servidor (para pintar la pantalla al recargar). */
export async function pendientesEnCola(): Promise<Op[]> {
  return (await colaTodas<Op>()).map((e) => e.valor);
}

// ── Envío ────────────────────────────────────────────────────────────────────

let corriendo = false;
let otraVez = false;
let intentosFallidos = 0;
let temporizador: ReturnType<typeof setTimeout> | null = null;

function lote(todas: EnCola<Op>[]): EnCola<Op>[] {
  const l: EnCola<Op>[] = [];
  for (const e of todas) {
    l.push(e);
    // Después de abrir una tula se espera su respuesta: si choca (409) no se manda lo que sigue
    if (e.valor.tipo === "abrir_tula" || l.length >= MAX_POR_LOTE) break;
  }
  return l;
}

function reintentarEn(ms: number) {
  if (temporizador) clearTimeout(temporizador);
  temporizador = setTimeout(() => void sincronizar(), ms);
}

export async function sincronizar(): Promise<void> {
  if (corriendo) {
    otraVez = true;
    return;
  }
  if (useCola.getState().bloqueo) return;
  corriendo = true;
  useCola.setState({ enviando: true });
  try {
    for (;;) {
      otraVez = false;
      const todas = await colaTodas<Op>();
      useCola.setState({ pendientes: todas.length });
      if (todas.length === 0) break;
      const envio = lote(todas);
      let resp: RespuestaSync;
      try {
        resp = (await api.post<RespuestaSync>("/flujo/sync", { ops: envio.map((e) => e.valor) }, { timeout: 15_000 })).data;
      } catch (e) {
        const status = (e as { response?: { status?: number } })?.response?.status;
        intentosFallidos += 1;
        useCola.setState({ sinSenal: status === undefined });
        // Espera creciente con algo de azar, para que no reintenten todos a la vez
        const espera = Math.min(ESPERA_MAX_MS, 1000 * 2 ** Math.min(intentosFallidos, 5)) + Math.random() * 1000;
        reintentarEn(espera);
        return;
      }
      intentosFallidos = 0;
      useCola.setState({ sinSenal: false, ultimoEnvio: Date.now() });

      const porOp = new Map(resp.resultados.map((r) => [r.op_id, r]));
      const hechas: number[] = [];
      let bloqueo: Bloqueo | null = null;
      for (const e of envio) {
        const r = porOp.get(e.valor.op_id);
        if (!r) break; // el servidor paró ahí (falla suya): se reintenta desde esta
        if (e.valor.tipo === "abrir_tula" && (r.status === 409 || r.status === 422)) {
          bloqueo = { seq: e.seq, op: e.valor, status: r.status, detalle: (r.body as { detail?: unknown })?.detail };
        } else {
          hechas.push(e.seq);
        }
        oyentes.forEach((fn) => fn(e.valor, r, resp.tulas));
        if (bloqueo) break;
      }
      await colaQuitar(hechas);
      if (bloqueo) {
        useCola.setState({ bloqueo });
        break;
      }
      if (resp.pendientes > 0) {
        reintentarEn(3000);
        break;
      }
    }
  } finally {
    corriendo = false;
    useCola.setState({ enviando: false });
    await contar();
    if (otraVez && !useCola.getState().bloqueo) void sincronizar();
  }
}

/**
 * Al abrir una tula había otra abierta en el servidor:
 *  - "cerrar": se cierra esa y se abre la nueva (lo leído queda en la nueva).
 *  - "seguir": no se abre la nueva; lo leído se pasa a la tula que ya estaba abierta.
 */
export async function resolverConflicto(decision: "cerrar" | "seguir", tulaAbiertaId?: number): Promise<void> {
  const b = useCola.getState().bloqueo;
  if (!b) return;
  if (decision === "cerrar") {
    await colaReemplazar<Op>(b.seq, {
      ...b.op, op_id: nuevoId(), datos: { ...(b.op.datos ?? {}), cerrar_anterior: true },
    });
  } else {
    const local = b.op.tula_local_id;
    const todas = await colaTodas<Op>();
    await colaQuitar([b.seq]);
    for (const e of todas) {
      if (e.seq !== b.seq && local && e.valor.tula_local_id === local && tulaAbiertaId) {
        await colaReemplazar<Op>(e.seq, { ...e.valor, tula_local_id: undefined, tula_id: tulaAbiertaId });
      }
    }
  }
  useCola.setState({ bloqueo: null });
  void sincronizar();
}

/**
 * El servidor rechazó el código de la tula (422): se abre como "tula sin etiqueta" y lo
 * leído después sigue en ella, en vez de perderse.
 */
export async function abrirSinEtiqueta(): Promise<void> {
  const b = useCola.getState().bloqueo;
  if (!b || b.op.tipo !== "abrir_tula") return;
  await colaReemplazar<Op>(b.seq, { ...b.op, op_id: nuevoId(), datos: { ...(b.op.datos ?? {}), codigo: null } });
  useCola.setState({ bloqueo: null });
  void sincronizar();
}

// Al volver la señal o volver a la pantalla, se manda enseguida lo pendiente
if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    intentosFallidos = 0;
    useCola.setState({ sinSenal: false });
    void sincronizar();
  });
  window.addEventListener("offline", () => useCola.setState({ sinSenal: true }));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void sincronizar();
  });
  void sincronizar();
}
