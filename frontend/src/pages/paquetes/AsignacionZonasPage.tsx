import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { AlertTriangle, Camera, CameraOff, MapPinned, RotateCcw, Send } from "lucide-react";
import {
  asignacionZonasApi,
  type AsignacionSerial,
  type ChoqueZonas,
  type EnvioImile,
  type SerialDelMensajero,
  type TotalMensajero,
  type ZonasMensajero,
} from "@/api/asignacionZonas";
import { FlujoPaquetesNav } from "./FlujoPaquetesNav";

function leerError(e: unknown): { status?: number; detail?: unknown } {
  const r = (e as { response?: { status?: number; data?: { detail?: unknown } } })?.response;
  return { status: r?.status, detail: r?.data?.detail };
}

const mismoCodigo = (a: string, b: string) => a.trim().toUpperCase() === b.trim().toUpperCase();

const SCANNER_ELEMENT_ID = "asignacion-qr-reader";
const SCAN_FORMATS = [
  Html5QrcodeSupportedFormats.QR_CODE,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.CODE_39,
  Html5QrcodeSupportedFormats.CODE_93,
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.ITF,
];
const ANTIRREBOTE_MS = 2000; // la cámara lee el mismo código varias veces por segundo

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

  const totalesQuery = useQuery({
    queryKey: ["asignacion-totales"],
    queryFn: () => asignacionZonasApi.totales().then((r) => r.data),
    refetchInterval: 15000,
  });
  const totales = totalesQuery.data ?? [];

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
  const paquetesAsignados = totales.reduce((s, t) => s + t.paquetes, 0);
  const cambios =
    !!mensajero &&
    (elegidas.size !== mensajero.zonas.length || mensajero.zonas.some((z) => !elegidas.has(z)));

  function refrescar() {
    void qc.invalidateQueries({ queryKey: ["asignacion-tablero"] });
    void qc.invalidateQueries({ queryKey: ["asignacion-seriales"] });
    void qc.invalidateQueries({ queryKey: ["asignacion-totales"] });
  }

  function tomarMensajero(m: ZonasMensajero) {
    setMensajero(m);
    setElegidas(new Set(m.zonas));
    setChoques(null);
  }

  async function buscar(e: React.FormEvent) {
    e.preventDefault();
    await cargarMensajero(codigo.trim());
  }

  async function cargarMensajero(cod: string) {
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
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="sticky top-0 z-20 bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <MapPinned size={24} className="text-primary shrink-0" />
        <div className="min-w-0 flex-1">
          <h1 className="font-semibold text-gray-900 truncate">Asignación de Zonas</h1>
          <p className="text-xs text-gray-500 truncate">
            {mensajero ? (
              <>
                <span className="font-medium text-gray-900">{mensajero.nombre}</span> · {mensajero.codigo} ·{" "}
                {elegidas.size} zona{elegidas.size === 1 ? "" : "s"} marcada{elegidas.size === 1 ? "" : "s"}
              </>
            ) : (
              "Ingresa el código del mensajero"
            )}
          </p>
        </div>
      </header>

      <div className="bg-white border-b border-gray-200 px-4 py-1.5 text-sm text-gray-600 text-center">
        <span className="font-semibold text-gray-900">{asignadas}/{tablero.length}</span> zonas ·{" "}
        <span className="font-semibold text-gray-900">{tablero.length - asignadas}</span> sin asignar ·{" "}
        <span className="font-semibold text-gray-900">{paquetes}</span> leídos ·{" "}
        <span className="font-semibold text-gray-900">{paquetesAsignados}</span> asignados
      </div>

      <div className="bg-white border-b border-gray-200 px-4 py-2">
        <FlujoPaquetesNav className="max-w-md mx-auto" />
      </div>

      <div className="p-3 sm:p-4 w-full max-w-md mx-auto lg:max-w-6xl flex-1 grid gap-4 lg:grid-cols-2 lg:items-start">
        <div className="flex flex-col gap-3 min-w-0">
          <p className="hidden sm:block text-sm text-gray-500">
            Ingresa el código del mensajero, marca sus zonas de hoy y guarda. Cada zona va completa a un
            solo mensajero; los paquetes sueltos se le pasan pistoleando su serial.
          </p>

          <form onSubmit={buscar} className="flex gap-2">
            <input
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              placeholder="Código del mensajero"
              autoComplete="off"
              autoCapitalize="characters"
              className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-2.5 text-base font-mono bg-white outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              type="submit"
              disabled={!codigo.trim() || buscando}
              className="shrink-0 bg-gray-800 hover:bg-gray-900 text-white font-medium px-5 py-2.5 rounded-lg disabled:opacity-40"
            >
              {buscando ? "Buscando…" : "Buscar"}
            </button>
          </form>

          {error && (
            <div role="alert" className="rounded-lg px-4 py-2.5 text-sm bg-red-50 text-red-800 border border-red-200">
              {error}
            </div>
          )}
          {ok && <div className="rounded-lg px-4 py-2.5 text-sm bg-green-50 text-green-800 border border-green-200">{ok}</div>}

          {tableroQuery.isLoading ? (
            <p className="text-sm text-gray-500">Cargando zonas…</p>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-4 xl:grid-cols-5 gap-2">
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
                    className={`min-w-0 min-h-[56px] text-left rounded-lg border p-2 transition disabled:cursor-default ${clase}`}
                  >
                    <div className="flex items-baseline justify-between gap-1">
                      <span className="font-mono font-semibold text-base text-gray-900 truncate">{z.zona}</span>
                      <span className="text-xs text-gray-500 shrink-0">{z.paquetes_leidos} paq.</span>
                    </div>
                    <p className={`text-xs truncate mt-0.5 ${z.mensajero ? "text-gray-700" : "text-gray-400"}`}>
                      {z.mensajero ? z.mensajero.nombre : "Sin asignar"}
                    </p>
                  </button>
                );
              })}
            </div>
          )}

          {mensajero && (cambios || choques) && (
            <div className="sticky bottom-0 z-10 -mx-3 sm:mx-0 bg-white border-t sm:border sm:rounded-xl border-gray-200 px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-[0_-4px_12px_rgba(0,0,0,0.06)]">
              {choques && (
                <div className="mb-3 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
                  <p className="font-medium text-amber-900 flex items-center gap-2">
                    <AlertTriangle size={16} className="shrink-0" /> Estas zonas ya las tiene otro mensajero:
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
                      className="flex-1 bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2.5 rounded-lg disabled:opacity-40"
                    >
                      Sí, reasignar
                    </button>
                    <button
                      type="button"
                      onClick={() => setChoques(null)}
                      className="flex-1 border border-gray-300 bg-white text-gray-700 font-medium px-4 py-2.5 rounded-lg"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
              {!choques && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => { setElegidas(new Set(mensajero.zonas)); setChoques(null); }}
                    className="shrink-0 border border-gray-300 bg-white text-gray-700 font-medium px-3 py-2.5 rounded-lg text-sm"
                  >
                    Deshacer cambios
                  </button>
                  <button
                    type="button"
                    disabled={!cambios || guardando}
                    onClick={() => guardar(false)}
                    className="min-w-0 flex-1 truncate bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2.5 rounded-lg disabled:opacity-40"
                  >
                    {guardando ? "Guardando…" : `Guardar zonas de ${mensajero.nombre}`}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4 min-w-0">
          {mensajero && (
            <SerialesDelMensajero
              mensajero={mensajero}
              seriales={serialesQuery.data ?? []}
              cargando={serialesQuery.isLoading}
              onCambio={refrescar}
              onMensajero={setMensajero}
            />
          )}

          <TotalesPorMensajero
            totales={totales}
            cargando={totalesQuery.isLoading}
            actual={mensajero?.codigo ?? null}
            onElegir={(cod) => {
              setCodigo(cod);
              void cargarMensajero(cod);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        </div>
      </div>
    </div>
  );
}

/** Cuántos paquetes lleva cada mensajero hoy; tocar una fila lo carga para editarlo. */
function TotalesPorMensajero({ totales, cargando, actual, onElegir }: {
  totales: TotalMensajero[];
  cargando: boolean;
  actual: string | null;
  onElegir: (codigo: string) => void;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <h2 className="font-semibold text-gray-900">Paquetes por mensajero hoy</h2>
      {cargando ? (
        <p className="text-sm text-gray-500 mt-2">Cargando…</p>
      ) : totales.length === 0 ? (
        <p className="text-sm text-gray-500 mt-2">Todavía no hay mensajeros con zonas o paquetes asignados.</p>
      ) : (
        <ul className="mt-2 -mx-2 divide-y divide-gray-100 text-sm">
          {totales.map((t) => (
            <li key={t.codigo}>
              <button
                type="button"
                onClick={() => onElegir(t.codigo)}
                className={`w-full text-left px-2 py-2.5 rounded-lg hover:bg-gray-50 ${actual && mismoCodigo(actual, t.codigo) ? "bg-primary/10" : ""}`}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate">
                    <span className="font-medium text-gray-900">{t.nombre}</span>
                    <span className="text-gray-500 font-mono text-xs"> · {t.codigo}</span>
                  </span>
                  <span className="shrink-0 text-lg font-bold text-gray-900">{t.paquetes}</span>
                </div>
                <div className="flex justify-between gap-3 text-xs text-gray-500 mt-0.5">
                  <span className="min-w-0 font-mono break-words">{t.zonas.join(", ") || "Sin zonas"}</span>
                  {t.reasignados > 0 && <span className="shrink-0">{t.reasignados} reasignado{t.reasignados === 1 ? "" : "s"}</span>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Reasignación serial por serial y la lista final de paquetes del mensajero (la que usará el 3.3). */
function SerialesDelMensajero({ mensajero, seriales, cargando, onCambio, onMensajero }: {
  mensajero: ZonasMensajero;
  seriales: SerialDelMensajero[];
  cargando: boolean;
  onCambio: () => void;
  onMensajero: (m: ZonasMensajero) => void;
}) {
  const [serial, setSerial] = useState("");
  const [ultimo, setUltimo] = useState<AsignacionSerial | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [camara, setCamara] = useState(false);
  const campoRef = useRef<HTMLInputElement>(null);
  const ultimaLecturaRef = useRef<{ codigo: string; at: number }>({ codigo: "", at: 0 });

  async function asignar(raw: string) {
    const s = raw.trim();
    if (!s) return;
    const ahora = Date.now();
    if (ultimaLecturaRef.current.codigo === s && ahora - ultimaLecturaRef.current.at < ANTIRREBOTE_MS) return;
    ultimaLecturaRef.current = { codigo: s, at: ahora };
    setError(null);
    try {
      setUltimo((await asignacionZonasApi.asignarSerial(mensajero.codigo, s)).data);
      onCambio();
    } catch (err) {
      const { detail } = leerError(err);
      setUltimo(null);
      setError(typeof detail === "string" ? detail : "No se pudo asignar el serial");
    } finally {
      // Con la cámara abierta no se enfoca el campo: en el celular sacaría el teclado
      if (!camara) campoRef.current?.focus();
    }
  }

  // La cámara llama siempre a la versión más reciente (con el mensajero actual)
  const asignarRef = useRef(asignar);
  asignarRef.current = asignar;

  useEffect(() => {
    if (!camara) return;
    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, { formatsToSupport: SCAN_FORMATS, verbose: false });
    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 150 } },
        (texto) => void asignarRef.current(texto),
        () => {},
      )
      .catch(() => {
        setError("No se pudo abrir la cámara");
        setCamara(false);
      });
    return () => {
      scanner.stop().then(() => scanner.clear()).catch(() => {});
    };
  }, [camara]);

  function pistolear(e: React.FormEvent) {
    e.preventDefault();
    const s = serial;
    setSerial("");
    void asignar(s);
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
    <>
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
            autoCapitalize="characters"
            className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-2.5 text-base font-mono outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            type="submit"
            disabled={!serial.trim()}
            className="shrink-0 bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg disabled:opacity-40"
          >
            Asignar
          </button>
          <button
            type="button"
            onClick={() => setCamara((c) => !c)}
            aria-label={camara ? "Cerrar cámara" : "Leer con la cámara"}
            title={camara ? "Cerrar cámara" : "Leer con la cámara"}
            className={`shrink-0 rounded-lg border px-3 ${camara ? "border-primary bg-primary text-white" : "border-gray-300 text-gray-700"}`}
          >
            {camara ? <CameraOff size={20} /> : <Camera size={20} />}
          </button>
        </form>
        {camara && <div id={SCANNER_ELEMENT_ID} className="mt-3 w-full rounded-xl overflow-hidden bg-black" />}
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
        <AsignarEnImile mensajero={mensajero} seriales={seriales} onCambio={onCambio} onMensajero={onMensajero} />
        {cargando ? (
          <p className="text-sm text-gray-500 mt-2">Cargando…</p>
        ) : seriales.length === 0 ? (
          <p className="text-sm text-gray-500 mt-2">Todavía no tiene paquetes leídos en sus zonas.</p>
        ) : (
          <ul className="mt-2 lg:max-h-96 lg:overflow-y-auto divide-y divide-gray-100 text-sm">
            {seriales.map((s) => (
              <li key={s.serial} className="py-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0 font-mono break-all">
                    <span className="text-gray-400">{s.serial.slice(0, -4)}</span>
                    <span className="font-bold text-gray-900">{s.serial.slice(-4)}</span>
                  </span>
                  <span className="shrink-0 text-gray-600">{s.zona ?? "—"}</span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 mt-0.5">
                  <EstadoImile serial={s} />
                  {s.origen === "serial" && (
                    <button
                      type="button"
                      onClick={() => devolver(s.serial)}
                      className="ml-auto inline-flex items-center gap-1 text-xs text-primary font-medium py-1.5"
                      title="Deshacer: vuelve al mensajero de su zona"
                    >
                      <RotateCcw size={12} /> Devolver a su zona
                    </button>
                  )}
                </div>
                <MotivoImile serial={s} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

const ASIGNADO_EN_IMILE = new Set(["ok", "repetido"]);
// No se vuelven a mandar: lo ya asignado y las guías que iMile tiene cerradas
const SIN_REENVIO = new Set([...ASIGNADO_EN_IMILE, "cerrada"]);

const ETIQUETA_IMILE: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "iMile ✓", clase: "text-green-700" },
  repetido: { texto: "iMile ✓", clase: "text-green-700" },
  bloqueado: { texto: "iMile: bloqueado", clase: "text-red-700" },
  error: { texto: "iMile: error", clase: "text-red-700" },
  sin_confirmar: { texto: "iMile: sin confirmar", clase: "text-amber-700" },
  cerrada: { texto: "Cerrada en iMile", clase: "text-gray-600" },
};

function EstadoImile({ serial: s }: { serial: SerialDelMensajero }) {
  if (!s.imile_estado) {
    // Sin mandar; si se le pasó de otro mensajero ya mandado, dice con quién quedó en iMile
    return s.imile_mensaje ? <span className="text-xs text-amber-700" title={s.imile_mensaje}>iMile: con otro</span> : null;
  }
  const e = ETIQUETA_IMILE[s.imile_estado] ?? { texto: `iMile: ${s.imile_estado}`, clase: "text-red-700" };
  return <span className={`text-xs ${e.clase}`}>{e.texto}</span>;
}

/** Lo que respondió iMile, a la vista, cuando el paquete no quedó asignado. */
function MotivoImile({ serial: s }: { serial: SerialDelMensajero }) {
  if (!s.imile_mensaje || ASIGNADO_EN_IMILE.has(s.imile_estado ?? "")) return null;
  const clase = s.imile_estado === "cerrada" || !s.imile_estado ? "text-gray-500" : "text-red-700";
  return <p className={`text-xs mt-0.5 break-words ${clase}`}>{s.imile_mensaje}</p>;
}

/** Paso 3.3: pasa a iMile ("Asignar repartidor") los paquetes del mensajero, uno por uno. */
function AsignarEnImile({ mensajero, seriales, onCambio, onMensajero }: {
  mensajero: ZonasMensajero;
  seriales: SerialDelMensajero[];
  onCambio: () => void;
  onMensajero: (m: ZonasMensajero) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [nombre, setNombre] = useState(mensajero.nombre_imile ?? "");
  const pendientes = seriales.filter((s) => !SIN_REENVIO.has(s.imile_estado ?? "")).length;

  const envioQuery = useQuery({
    queryKey: ["asignacion-envio-imile", mensajero.codigo],
    queryFn: () => asignacionZonasApi.envioImile(mensajero.codigo).then((r) => r.data),
    refetchInterval: (q) => (q.state.data?.en_curso ? 2000 : false),
  });
  const envio: EnvioImile | null = envioQuery.data ?? null;

  // Mientras avanza, la lista muestra el estado de cada paquete
  const hechos = envio?.hechos ?? 0;
  const enCurso = !!envio?.en_curso;
  useEffect(() => {
    if (envio) onCambio();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hechos, enCurso]);

  useEffect(() => setNombre(mensajero.nombre_imile ?? ""), [mensajero.codigo, mensajero.nombre_imile]);

  async function enviar() {
    setError(null);
    try {
      await asignacionZonasApi.asignarEnImile(mensajero.codigo);
      await envioQuery.refetch();
    } catch (err) {
      const { detail } = leerError(err);
      setError(typeof detail === "string" ? detail : "No se pudo mandar a iMile");
    }
  }

  async function guardarNombre(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      onMensajero((await asignacionZonasApi.fijarNombreImile(mensajero.codigo, nombre.trim() || null)).data);
    } catch (err) {
      const { detail } = leerError(err);
      setError(typeof detail === "string" ? detail : "No se pudo guardar el nombre");
    }
  }

  return (
    <div className="mt-2 mb-1 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-gray-600">
          En iMile: <span className="font-medium text-gray-900">{mensajero.nombre_imile || mensajero.nombre}</span>
        </span>
        <button
          type="button"
          disabled={enCurso || pendientes === 0}
          onClick={enviar}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 bg-primary hover:bg-primary-hover text-white text-sm font-medium px-3 py-2.5 sm:py-1.5 rounded-lg disabled:opacity-40"
        >
          <Send size={14} />
          {enCurso ? "Asignando en iMile…" : pendientes === 0 ? "Todo asignado en iMile" : `Asignar en iMile (${pendientes})`}
        </button>
      </div>

      {envio && envio.total > 0 && (
        <p className="mt-2 text-gray-700">
          {envio.hechos} de {envio.total} mandados · <span className="text-green-700">{envio.asignados} asignados</span>
          {envio.fallidos > 0 && <span className="text-red-700"> · {envio.fallidos} con error</span>}
        </p>
      )}
      {error && <p role="alert" className="mt-2 text-red-700">{error}</p>}

      {envio?.error && (
        <div role="alert" className="mt-2 rounded-lg border border-red-200 bg-red-50 p-2.5 text-red-800">
          <p>{envio.error}</p>
          <form onSubmit={guardarNombre} className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-2 mt-2">
            <label htmlFor="nombre-imile" className="text-xs text-red-900">Nombre exacto en iMile:</label>
            <input
              id="nombre-imile"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Como sale en iMile, ej. Mariela Pabon | D21026309101"
              className="min-w-0 flex-1 border border-gray-300 rounded-lg px-2 py-2 sm:py-1 text-base sm:text-sm bg-white outline-none focus:ring-2 focus:ring-primary"
            />
            <button type="submit" className="bg-gray-800 text-white text-sm sm:text-xs font-medium px-3 py-2.5 sm:py-1.5 rounded-lg">
              Guardar
            </button>
          </form>
          <p className="mt-1 text-xs text-red-900/80">
            Cópialo del selector DA de iMile: con el código (| D…) se elige exactamente ese mensajero.
          </p>
        </div>
      )}
    </div>
  );
}
