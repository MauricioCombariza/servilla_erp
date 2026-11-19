/**
 * IndexedDB mínimo para el trabajo sin señal (sin dependencias).
 * - "kv": valores sueltos (base del día, estado de la pantalla, cursor de cambios).
 * - "cola": operaciones por mandar al servidor, en orden (clave autoincremental).
 * Si IndexedDB no está disponible (navegación privada en algunos celulares) todo sigue en
 * memoria: se puede trabajar, pero una recarga de la página pierde lo que no se envió.
 */
const NOMBRE = "servilla_flujo";
const VERSION = 1;

let abierta: Promise<IDBDatabase | null> | null = null;
const memoria = { kv: new Map<string, unknown>(), cola: new Map<number, unknown>(), seq: 0 };

function abrir(): Promise<IDBDatabase | null> {
  if (!abierta) {
    abierta = new Promise((resolve) => {
      try {
        const req = indexedDB.open(NOMBRE, VERSION);
        req.onupgradeneeded = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains("kv")) db.createObjectStore("kv");
          if (!db.objectStoreNames.contains("cola")) db.createObjectStore("cola", { autoIncrement: true });
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => resolve(null);
        req.onblocked = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }
  return abierta;
}

function esperar<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function almacen(nombre: "kv" | "cola", modo: IDBTransactionMode) {
  const db = await abrir();
  return db ? db.transaction(nombre, modo).objectStore(nombre) : null;
}

export async function kvLeer<T>(clave: string): Promise<T | undefined> {
  const s = await almacen("kv", "readonly");
  if (!s) return memoria.kv.get(clave) as T | undefined;
  return (await esperar(s.get(clave))) as T | undefined;
}

export async function kvGuardar(clave: string, valor: unknown): Promise<void> {
  const s = await almacen("kv", "readwrite");
  if (!s) {
    memoria.kv.set(clave, valor);
    return;
  }
  await esperar(s.put(valor, clave));
}

export async function kvBorrar(clave: string): Promise<void> {
  const s = await almacen("kv", "readwrite");
  if (!s) {
    memoria.kv.delete(clave);
    return;
  }
  await esperar(s.delete(clave));
}

export type EnCola<T> = { seq: number; valor: T };

export async function colaAgregar<T>(valor: T): Promise<number> {
  const s = await almacen("cola", "readwrite");
  if (!s) {
    memoria.seq += 1;
    memoria.cola.set(memoria.seq, valor);
    return memoria.seq;
  }
  return (await esperar(s.add(valor))) as number;
}

export async function colaTodas<T>(): Promise<EnCola<T>[]> {
  const s = await almacen("cola", "readonly");
  if (!s) return [...memoria.cola.entries()].map(([seq, valor]) => ({ seq, valor: valor as T }));
  const [claves, valores] = await Promise.all([esperar(s.getAllKeys()), esperar(s.getAll())]);
  return claves.map((k, i) => ({ seq: k as number, valor: valores[i] as T }));
}

export async function colaReemplazar<T>(seq: number, valor: T): Promise<void> {
  const s = await almacen("cola", "readwrite");
  if (!s) {
    memoria.cola.set(seq, valor);
    return;
  }
  await esperar(s.put(valor, seq));
}

export async function colaQuitar(seqs: number[]): Promise<void> {
  if (seqs.length === 0) return;
  const db = await abrir();
  if (!db) {
    seqs.forEach((s) => memoria.cola.delete(s));
    return;
  }
  const tx = db.transaction("cola", "readwrite");
  seqs.forEach((s) => tx.objectStore("cola").delete(s));
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
