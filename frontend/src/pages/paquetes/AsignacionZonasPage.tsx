import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, MapPinned, RotateCcw, Send } from "lucide-react";
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
    <div>
      <FlujoPaquetesNav className="mb-4 max-w-xl" />
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

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 max-w-2xl">
        <Cifra valor={`${asignadas}/${tablero.length}`} etiqueta="Zonas asignadas" />
        <Cifra valor={tablero.length - asignadas} etiqueta="Sin asignar" />
        <Cifra valor={paquetes} etiqueta="Paquetes leídos hoy" />
        <Cifra valor={paquetesAsignados} etiqueta="Paquetes asignados" />
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

      <TotalesPorMensajero
        totales={totales}
        cargando={totalesQuery.isLoading}
        actual={mensajero?.codigo ?? null}
        onElegir={(cod) => { setCodigo(cod); void cargarMensajero(cod); }}
      />

      {mensajero && (
        <SerialesDelMensajero
          mensajero={mensajero}
          seriales={serialesQuery.data ?? []}
          cargando={serialesQuery.isLoading}
          onCambio={refrescar}
          onMensajero={setMensajero}
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

/** Cuántos paquetes lleva cada mensajero hoy; tocar una fila lo carga para editarlo. */
function TotalesPorMensajero({ totales, cargando, actual, onElegir }: {
  totales: TotalMensajero[];
  cargando: boolean;
  actual: string | null;
  onElegir: (codigo: string) => void;
}) {
  return (
    <div className="mt-6 rounded-xl border border-gray-200 bg-white p-4">
      <h2 className="font-semibold text-gray-900">Paquetes por mensajero hoy</h2>
      {cargando ? (
        <p className="text-sm text-gray-500 mt-2">Cargando…</p>
      ) : totales.length === 0 ? (
        <p className="text-sm text-gray-500 mt-2">Todavía no hay mensajeros con zonas o paquetes asignados.</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
                <th className="py-1.5 pr-3 font-medium">Mensajero</th>
                <th className="py-1.5 pr-3 font-medium">Zonas</th>
                <th className="py-1.5 pr-3 font-medium text-right">Paquetes</th>
                <th className="py-1.5 font-medium text-right">Reasignados</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {totales.map((t) => (
                <tr
                  key={t.codigo}
                  onClick={() => onElegir(t.codigo)}
                  className={`cursor-pointer hover:bg-gray-50 ${actual && mismoCodigo(actual, t.codigo) ? "bg-primary/10" : ""}`}
                >
                  <td className="py-1.5 pr-3">
                    <span className="font-medium text-gray-900">{t.nombre}</span>
                    <span className="text-gray-500 font-mono text-xs"> · {t.codigo}</span>
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-gray-600">{t.zonas.join(", ") || "—"}</td>
                  <td className="py-1.5 pr-3 text-right font-bold text-gray-900">{t.paquetes}</td>
                  <td className="py-1.5 text-right text-gray-600">{t.reasignados || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
        <AsignarEnImile mensajero={mensajero} seriales={seriales} onCambio={onCambio} onMensajero={onMensajero} />
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
                  <EstadoImile serial={s} />
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

const ASIGNADO_EN_IMILE = new Set(["ok", "repetido"]);

const ETIQUETA_IMILE: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "iMile ✓", clase: "text-green-700" },
  repetido: { texto: "iMile ✓", clase: "text-green-700" },
  bloqueado: { texto: "iMile: bloqueado", clase: "text-red-700" },
  error: { texto: "iMile: error", clase: "text-red-700" },
  sin_confirmar: { texto: "iMile: sin confirmar", clase: "text-amber-700" },
};

function EstadoImile({ serial: s }: { serial: SerialDelMensajero }) {
  if (!s.imile_estado) {
    // Sin mandar; si se le pasó de otro mensajero ya mandado, dice con quién quedó en iMile
    return s.imile_mensaje ? <span className="text-xs text-amber-700" title={s.imile_mensaje}>iMile: con otro</span> : null;
  }
  const e = ETIQUETA_IMILE[s.imile_estado] ?? { texto: `iMile: ${s.imile_estado}`, clase: "text-red-700" };
  return <span className={`text-xs ${e.clase}`} title={s.imile_mensaje ?? undefined}>{e.texto}</span>;
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
  const pendientes = seriales.filter((s) => !ASIGNADO_EN_IMILE.has(s.imile_estado ?? "")).length;

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
          className="inline-flex items-center gap-1.5 bg-primary hover:bg-primary-hover text-white text-sm font-medium px-3 py-1.5 rounded-lg disabled:opacity-40"
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
          <form onSubmit={guardarNombre} className="flex flex-wrap items-center gap-2 mt-2">
            <label htmlFor="nombre-imile" className="text-xs text-red-900">Nombre exacto en iMile:</label>
            <input
              id="nombre-imile"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Como sale en iMile, ej. Mariela Pabon | D21026309101"
              className="min-w-0 flex-1 border border-gray-300 rounded-lg px-2 py-1 text-sm bg-white outline-none focus:ring-2 focus:ring-primary"
            />
            <button type="submit" className="bg-gray-800 text-white text-xs font-medium px-3 py-1.5 rounded-lg">
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
