import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, MapPinned, RotateCcw } from "lucide-react";
import {
  asignacionZonasApi,
  type AsignacionSerial,
  type ChoqueZonas,
  type SerialDelMensajero,
  type ZonasMensajero,
} from "@/api/asignacionZonas";

function leerError(e: unknown): { status?: number; detail?: unknown } {
  const r = (e as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
  return { status: r?.status, detail: r?.data?.detail };
}

const mismoCodigo = (a: string, b: string) => a.trim().toUpperCase() === b.trim().toUpperCase();

/**
 * Pasos 3.1 y 3.2 (con sesión del ERP): se ingresa el código del mensajero, se le eligen
 * sus zonas del día sobre el tablero (cada zona va completa a un solo mensajero) y, si hace
 * falta, se le pistolean seriales sueltos que quedan suyos aunque su zona sea de otro.
 */
export function AsignacionZonasPage() {
  const qc = useQueryClient();
  const [codigo, setCodigo] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [mensajero, setMensajero] = useState<ZonasMensajero | null>(null);
  const [elegidas, setElegidas] = useState<Set<string>>(new Set());
  const [choques, setChoques] = useState<ChoqueZonas | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const tableroQuery = useQuery({
    queryKey: ["asignacion-tablero"],
    queryFn: () => asignacionZonasApi.tablero().then((r) => r.data),
    refetchInterval: 15000,
  });
  const tablero = useMemo(() => tableroQuery.data ?? [], [tableroQuery.data]);

  const serialesQuery = useQuery({
    queryKey: ["asignacion-seriales", mensajero?.codigo],
    queryFn: () => asignacionZonasApi.seriales(mensajero!.codigo).then((r) => r.data),
    enabled: !!mensajero,
  });

  useEffect(() => {
    if (!ok) return;
    const t = setTimeout(() => setOk(null), 4000);
    return () => clearTimeout(t);
  }, [ok]);

  const asignadas = tablero.filter((z) => z.mensajero).length;
  const paquetes = tablero.reduce((s, z) => s + z.paquetes_leidos, 0);
  const cambios =
    !!mensajero &&
    (elegidas.size !== mensajero.zonas.length || mensajero.zonas.some((z) => !elegidas.has(z)));

  function refrescar() {
    void qc.invalidateQueries({ queryKey: ["asignacion-tablero"] });
    void qc.invalidateQueries({ queryKey: ["asignacion-seriales"] });
  }

  function tomarMensajero(m: ZonasMensajero) {
    setMensajero(m);
    setElegidas(new Set(m.zonas));
    setChoques(null);
  }

  async function buscar(e: React.FormEvent) {
    e.preventDefault();
    const cod = codigo.trim();
    if (!cod) return;
    setBuscando(true);
    setError(null);
    try {
      tomarMensajero((await asignacionZonasApi.mensajero(cod)).data);
    } catch (err) {
      const { status, detail } = leerError(err);
      setMensajero(null);
      setError(status === 404 ? "Mensajero no encontrado" : typeof detail === "string" ? detail : "No se pudo buscar");
    } finally {
      setBuscando(false);
    }
  }

  function alternar(zona: string) {
    if (!mensajero) return;
    setChoques(null);
    setElegidas((s) => {
      const n = new Set(s);
      if (n.has(zona)) n.delete(zona);
      else n.add(zona);
      return n;
    });
  }

  async function guardar(reasignar = false) {
    if (!mensajero) return;
    setGuardando(true);
    setError(null);
    try {
      const r = (await asignacionZonasApi.asignar(mensajero.codigo, [...elegidas].sort(), reasignar)).data;
      tomarMensajero(r);
      setOk(`Zonas de ${r.nombre} guardadas (${r.zonas.length})`);
      refrescar();
    } catch (err) {
      const { status, detail } = leerError(err);
      if (status === 409 && detail && typeof detail === "object" && "choques" in detail) {
        setChoques(detail as ChoqueZonas);
      } else {
        const msg = detail && typeof detail === "object" && "mensaje" in detail ? (detail as { mensaje: string }).mensaje : null;
        setError(msg ?? (typeof detail === "string" ? detail : "No se pudieron guardar las zonas"));
      }
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <MapPinned size={20} className="text-primary" />
          Asignación de Zonas
        </h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Ingresa el código del mensajero, marca sus zonas de hoy y guarda. Cada zona va completa a un
          solo mensajero; los paquetes sueltos se le pasan pistoleando su serial.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4 max-w-xl">
        <Cifra valor={`${asignadas}/${tablero.length}`} etiqueta="Zonas asignadas" />
        <Cifra valor={tablero.length - asignadas} etiqueta="Sin asignar" />
        <Cifra valor={paquetes} etiqueta="Paquetes leídos hoy" />
      </div>

      <form onSubmit={buscar} className="flex flex-wrap items-center gap-2 mb-3">
        <input
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          placeholder="Código del mensajero"
          autoComplete="off"
          className="w-52 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-primary"
        />
        <button
          type="submit"
          disabled={!codigo.trim() || buscando}
          className="bg-gray-800 hover:bg-gray-900 text-white text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-40"
        >
          {buscando ? "Buscando…" : "Buscar"}
        </button>
        {mensajero && (
          <span className="text-sm">
            <span className="font-semibold text-gray-900">{mensajero.nombre}</span>
            <span className="text-gray-500"> · {mensajero.codigo} · {elegidas.size} zona{elegidas.size === 1 ? "" : "s"} marcada{elegidas.size === 1 ? "" : "s"}</span>
          </span>
        )}
      </form>

      {error && (
        <div role="alert" className="mb-3 rounded-lg px-4 py-2.5 text-sm bg-red-50 text-red-800 border border-red-200">
          {error}
        </div>
      )}
      {ok && <div className="mb-3 rounded-lg px-4 py-2.5 text-sm bg-green-50 text-green-800 border border-green-200">{ok}</div>}

      {choques && mensajero && (
        <div className="mb-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
          <p className="font-medium text-amber-900 flex items-center gap-2">
            <AlertTriangle size={16} /> Estas zonas ya las tiene otro mensajero:
          </p>
          <ul className="mt-1 text-amber-900">
            {choques.choques.map((c) => (
              <li key={c.zona}>
                <span className="font-mono font-semibold">{c.zona}</span> — {c.nombre} ({c.codigo})
              </li>
            ))}
          </ul>
          <p className="mt-2 text-amber-800">¿Se las paso completas a {mensajero.nombre}?</p>
          <div className="flex gap-2 mt-3">
            <button
              type="button"
              disabled={guardando}
              onClick={() => guardar(true)}
              className="bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2 rounded-lg disabled:opacity-40"
            >
              Sí, reasignar
            </button>
            <button
              type="button"
              onClick={() => setChoques(null)}
              className="border border-gray-300 bg-white text-gray-700 font-medium px-4 py-2 rounded-lg"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}

      {tableroQuery.isLoading ? (
        <p className="text-sm text-gray-500">Cargando zonas…</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
          {tablero.map((z) => {
            const marcada = elegidas.has(z.zona);
            const deOtro = !!mensajero && !!z.mensajero && !mismoCodigo(z.mensajero.codigo, mensajero.codigo);
            const clase = !mensajero
              ? z.mensajero ? "border-gray-200 bg-white" : "border-dashed border-gray-300 bg-gray-50"
              : marcada
                ? deOtro ? "border-amber-400 bg-amber-50 ring-2 ring-amber-300" : "border-primary bg-primary/10 ring-2 ring-primary/40"
                : deOtro ? "border-gray-200 bg-gray-100 text-gray-500" : "border-gray-200 bg-white hover:border-primary";
            return (
              <button
                key={z.zona}
                type="button"
                disabled={!mensajero}
                onClick={() => alternar(z.zona)}
                aria-pressed={mensajero ? marcada : undefined}
                className={`text-left rounded-lg border p-2.5 transition disabled:cursor-default ${clase}`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono font-semibold text-gray-900">{z.zona}</span>
                  <span className="text-xs text-gray-500">{z.paquetes_leidos} paq.</span>
                </div>
                <p className={`text-xs truncate mt-0.5 ${z.mensajero ? "text-gray-700" : "text-gray-400"}`}>
                  {z.mensajero ? z.mensajero.nombre : "Sin asignar"}
                </p>
              </button>
            );
          })}
        </div>
      )}

      {mensajero && (
        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            disabled={!cambios || guardando}
            onClick={() => guardar(false)}
            className="bg-primary hover:bg-primary-hover text-white text-sm font-medium px-4 py-2 rounded-lg disabled:opacity-40"
          >
            {guardando ? "Guardando…" : `Guardar zonas de ${mensajero.nombre}`}
          </button>
          {cambios && (
            <button
              type="button"
              onClick={() => { setElegidas(new Set(mensajero.zonas)); setChoques(null); }}
              className="text-sm text-gray-500 hover:underline"
            >
              Deshacer cambios
            </button>
          )}
        </div>
      )}

      {mensajero && (
        <SerialesDelMensajero
          mensajero={mensajero}
          seriales={serialesQuery.data ?? []}
          cargando={serialesQuery.isLoading}
          onCambio={refrescar}
        />
      )}
    </div>
  );
}

function Cifra({ valor, etiqueta }: { valor: number | string; etiqueta: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
      <p className="text-xl font-bold text-gray-900">{valor}</p>
      <p className="text-xs text-gray-500">{etiqueta}</p>
    </div>
  );
}

/** Reasignación serial por serial y la lista final de paquetes del mensajero (la que usará el 3.3). */
function SerialesDelMensajero({ mensajero, seriales, cargando, onCambio }: {
  mensajero: ZonasMensajero;
  seriales: SerialDelMensajero[];
  cargando: boolean;
  onCambio: () => void;
}) {
  const [serial, setSerial] = useState("");
  const [ultimo, setUltimo] = useState<AsignacionSerial | null>(null);
  const [error, setError] = useState<string | null>(null);
  const campoRef = useRef<HTMLInputElement>(null);

  async function pistolear(e: React.FormEvent) {
    e.preventDefault();
    const s = serial.trim();
    setSerial("");
    if (!s) return;
    setError(null);
    try {
      setUltimo((await asignacionZonasApi.asignarSerial(mensajero.codigo, s)).data);
      onCambio();
    } catch (err) {
      const { detail } = leerError(err);
      setUltimo(null);
      setError(typeof detail === "string" ? detail : "No se pudo asignar el serial");
    } finally {
      campoRef.current?.focus();
    }
  }

  async function devolver(s: string) {
    setError(null);
    try {
      await asignacionZonasApi.quitarSerial(mensajero.codigo, s);
      onCambio();
    } catch (err) {
      const { detail } = leerError(err);
      setError(typeof detail === "string" ? detail : "No se pudo devolver el serial");
    }
  }

  const reasignados = seriales.filter((s) => s.origen === "serial").length;

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="font-semibold text-gray-900">Pasar paquetes sueltos a {mensajero.nombre}</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Pistolea el serial: queda de {mensajero.nombre} aunque su zona sea de otro mensajero.
        </p>
        <form onSubmit={pistolear} className="flex gap-2 mt-3">
          <input
            ref={campoRef}
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="Serial del paquete"
            autoComplete="off"
            className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            type="submit"
            disabled={!serial.trim()}
            className="bg-gray-800 hover:bg-gray-900 text-white text-sm font-medium px-4 rounded-lg disabled:opacity-40"
          >
            Asignar
          </button>
        </form>
        {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
        {ultimo && (
          <p className={`mt-2 text-sm ${ultimo.ya_era_suyo ? "text-amber-800" : "text-green-800"}`}>
            <span className="font-mono font-semibold">{ultimo.ultimos_4}</span>
            {ultimo.zona ? ` (${ultimo.zona})` : ""}:{" "}
            {ultimo.ya_era_suyo
              ? "ya era suyo"
              : ultimo.mensajero_anterior
                ? `pasó de ${ultimo.mensajero_anterior.nombre} a ${mensajero.nombre}`
                : `quedó de ${mensajero.nombre}`}
          </p>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="font-semibold text-gray-900">
          Paquetes de {mensajero.nombre} hoy{" "}
          <span className="text-gray-500 font-normal">
            ({seriales.length}{reasignados ? ` · ${reasignados} reasignado${reasignados === 1 ? "" : "s"}` : ""})
          </span>
        </h2>
        {cargando ? (
          <p className="text-sm text-gray-500 mt-2">Cargando…</p>
        ) : seriales.length === 0 ? (
          <p className="text-sm text-gray-500 mt-2">Todavía no tiene paquetes leídos en sus zonas.</p>
        ) : (
          <ul className="mt-2 max-h-80 overflow-y-auto divide-y divide-gray-100 text-sm">
            {seriales.map((s) => (
              <li key={s.serial} className="py-1.5 flex items-center justify-between gap-2">
                <span className="font-mono">
                  <span className="text-gray-400">{s.serial.slice(0, -4)}</span>
                  <span className="font-bold text-gray-900">{s.serial.slice(-4)}</span>
                </span>
                <span className="flex items-center gap-3 shrink-0">
                  <span className="text-gray-600">{s.zona ?? "—"}</span>
                  {s.origen === "serial" && (
                    <button
                      type="button"
                      onClick={() => devolver(s.serial)}
                      className="inline-flex items-center gap-1 text-xs text-primary font-medium"
                      title="Deshacer: vuelve al mensajero de su zona"
                    >
                      <RotateCcw size={12} /> Devolver a su zona
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
