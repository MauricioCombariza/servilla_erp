import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { AlertTriangle, Camera, CameraOff, PackageOpen, RotateCw } from "lucide-react";
import {
  tulasApi,
  type DestinoPaquete,
  type ImileEstado,
  type Tula,
  type TulaAbiertaConflicto,
  type TulaDetalle,
} from "@/api/tulas";

const SCANNER_ELEMENT_ID = "tulas-qr-reader";
const SCAN_FORMATS = [
  Html5QrcodeSupportedFormats.QR_CODE,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.CODE_39,
  Html5QrcodeSupportedFormats.CODE_93,
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.ITF,
];
const ANTIRREBOTE_MS = 2000; // la cámara lee el mismo código varias veces por segundo

/** Lo que se está leyendo: el código de una tula, o los paquetes de la tula abierta. */
type Modo = "tula" | "paquetes";

type Lectura = {
  serial: string;
  envio: "enviando" | "listo" | "falla";
  zona: string | null;
  aviso: string | null;
  imile: ImileEstado;
  imileMensaje: string | null;
  error?: string;
};

type Conflicto = { codigo: string | null; abierta: Tula };

function leerDetalle(e: unknown): unknown {
  return (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
}

function vibrar(patron: number | number[]) {
  if (navigator.vibrate) navigator.vibrate(patron);
}

/**
 * Pasos 2.2, 2.4, 2.5, 2.6 y 2.8 en una sola pantalla para celular: se lee la tula y ahí
 * mismo sus paquetes. Cada paquete se cuenta, se muestra su destino y se ingresa en iMile.
 * Sirve con el lector Bluetooth (escribe en el campo y manda Enter) o con la cámara.
 */
export function EscaneoTulasPage() {
  const [tula, setTula] = useState<Tula | null>(null);
  const [modo, setModo] = useState<Modo>("tula");
  const [codigo, setCodigo] = useState("");
  const [totalEsperado, setTotalEsperado] = useState("");
  const [lecturas, setLecturas] = useState<Lectura[]>([]);
  const [ultimo, setUltimo] = useState<{ destino: DestinoPaquete; ya: boolean } | null>(null);
  const [conflicto, setConflicto] = useState<Conflicto | null>(null);
  const [confirmarCierre, setConfirmarCierre] = useState(false);
  const [cerrada, setCerrada] = useState<TulaDetalle | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Paso 2.3: lo que dijo iMile del total al abrir la tula (queda visible mientras esté abierta)
  const [imileTotal, setImileTotal] = useState<string | null>(null);
  const [abriendo, setAbriendo] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [camara, setCamara] = useState(false);
  const campoRef = useRef<HTMLInputElement>(null);
  const ultimaLecturaRef = useRef({ codigo: "", at: 0 });

  // Al entrar (o recargar) se retoma la tula abierta con lo que ya se había leído
  const abiertaQuery = useQuery({
    queryKey: ["tula-abierta"],
    queryFn: async () => {
      const abierta = (await tulasApi.abierta()).data;
      return abierta ? (await tulasApi.detalle(abierta.id)).data : null;
    },
    refetchOnWindowFocus: false,
  });

  // Sin la base de despacho de hoy, todo saldría "No está en la tabla" y sin zona
  const baseQuery = useQuery({
    queryKey: ["tulas-base-del-dia"],
    queryFn: () => tulasApi.baseDelDia().then((r) => r.data),
  });
  const sinBase = baseQuery.data?.paquetes_hoy === 0;

  useEffect(() => {
    const d = abiertaQuery.data;
    if (!d) return;
    setTula(d);
    setModo("paquetes");
    setLecturas(
      [...d.seriales].reverse().map((s) => ({
        serial: s.serial,
        envio: "listo",
        zona: s.zona,
        aviso: s.en_tabla ? (s.zona ? null : "Fuera de zona") : "No está en la tabla",
        imile: s.imile_estado,
        imileMensaje: s.imile_mensaje,
      })),
    );
  }, [abiertaQuery.data]);

  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), 4000);
    return () => clearTimeout(t);
  }, [aviso]);

  function enfocar() {
    setTimeout(() => campoRef.current?.focus(), 0);
  }

  // ---------- Tula ----------

  async function abrirTula(cod: string | null, cerrarAnterior = false) {
    setOcupado(true);
    setAbriendo(true);
    try {
      const total = totalEsperado.trim() === "" ? null : Number(totalEsperado);
      const nueva = (
        await tulasApi.abrir({ codigo: cod, total_esperado: total, cerrar_anterior: cerrarAnterior })
      ).data;
      setTula(nueva);
      setImileTotal(nueva.imile_total);
      setModo("paquetes");
      setLecturas([]);
      setUltimo(null);
      setConflicto(null);
      setCerrada(null);
      setTotalEsperado("");
      vibrar(80);
    } catch (e) {
      const detalle = leerDetalle(e);
      if (detalle && typeof detalle === "object" && "tula_abierta" in detalle) {
        setConflicto({ codigo: cod, abierta: (detalle as TulaAbiertaConflicto).tula_abierta });
      } else {
        setAviso(typeof detalle === "string" ? detalle : "No se pudo abrir la tula");
        vibrar([50, 50, 50]);
      }
    } finally {
      setOcupado(false);
      setAbriendo(false);
      enfocar();
    }
  }

  async function guardarTotal(total: number) {
    if (!tula) return;
    try {
      setTula((await tulasApi.fijarTotal(tula.id, total)).data);
      setImileTotal(null);
    } catch {
      setAviso("No se pudo guardar el total");
    } finally {
      enfocar();
    }
  }

  async function cerrarTula() {
    if (!tula) return;
    setOcupado(true);
    try {
      const detalle = (await tulasApi.cerrar(tula.id)).data;
      setCerrada(detalle);
      setTula(null);
      setImileTotal(null);
      setModo("tula");
      setLecturas([]);
      setUltimo(null);
    } catch {
      setAviso("No se pudo cerrar la tula");
    } finally {
      setOcupado(false);
      setConfirmarCierre(false);
      enfocar();
    }
  }

  // ---------- Paquetes ----------

  function actualizarLectura(serial: string, cambios: Partial<Lectura>) {
    setLecturas((ls) => ls.map((l) => (l.serial === serial ? { ...l, ...cambios } : l)));
  }

  async function leerPaquete(serial: string) {
    if (!tula) return;
    const tulaId = tula.id;
    // Si ya estaba en la lista sube arriba; si no, entra como "enviando"
    setLecturas((ls) => {
      const previa = ls.find((l) => l.serial === serial);
      const fila: Lectura = previa
        ? { ...previa, envio: "enviando", error: undefined }
        : { serial, envio: "enviando", zona: null, aviso: null, imile: null, imileMensaje: null };
      return [fila, ...ls.filter((l) => l.serial !== serial)];
    });
    try {
      const r = (await tulasApi.escanear(tulaId, serial)).data;
      // Las respuestas pueden llegar en desorden (iMile atiende de a uno): manda la de más leídos
      setTula((t) => (t && t.id === r.tula.id && t.leidos > r.tula.leidos ? t : r.tula));
      setUltimo({ destino: r.destino, ya: r.ya_escaneado });
      actualizarLectura(serial, {
        envio: "listo",
        zona: r.destino.zona,
        aviso: r.destino.aviso,
        imile: r.imile.estado,
        imileMensaje: r.imile.mensaje,
      });
      vibrar(r.ya_escaneado ? [40, 60, 40] : 80);
    } catch (e) {
      const detalle = leerDetalle(e);
      const mensaje = typeof detalle === "string" ? detalle : "No se pudo registrar";
      actualizarLectura(serial, { envio: "falla", error: mensaje });
      vibrar([50, 50, 50]);
    }
  }

  async function reintentarImile(serial: string) {
    if (!tula) return;
    actualizarLectura(serial, { imile: null, imileMensaje: "Reintentando…" });
    try {
      const r = (await tulasApi.reintentarImile(tula.id, serial)).data;
      actualizarLectura(serial, { imile: r.imile_estado, imileMensaje: r.imile_mensaje });
    } catch {
      actualizarLectura(serial, { imile: "error", imileMensaje: "No se pudo reintentar" });
    }
  }

  // ---------- Entrada: lector Bluetooth, teclado o cámara ----------

  function recibirCodigo(raw: string) {
    const cod = raw.trim();
    if (!cod || ocupado || conflicto) return;
    const ahora = Date.now();
    if (ultimaLecturaRef.current.codigo === cod && ahora - ultimaLecturaRef.current.at < ANTIRREBOTE_MS) return;
    ultimaLecturaRef.current = { codigo: cod, at: ahora };

    if (modo === "tula") void abrirTula(cod);
    else void leerPaquete(cod);
  }

  // La cámara llama siempre a la versión más reciente (con el modo y la tula actuales)
  const recibirRef = useRef(recibirCodigo);
  recibirRef.current = recibirCodigo;

  useEffect(() => {
    if (!camara) return;
    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, { formatsToSupport: SCAN_FORMATS, verbose: false });
    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 150 } },
        (texto) => recibirRef.current(texto),
        () => {},
      )
      .catch(() => {
        setAviso("No se pudo abrir la cámara");
        setCamara(false);
      });
    return () => {
      scanner.stop().then(() => scanner.clear()).catch(() => {});
    };
  }, [camara]);

  function enviarCampo(e: React.FormEvent) {
    e.preventDefault();
    recibirCodigo(codigo);
    setCodigo("");
  }

  const enviando = lecturas.filter((l) => l.envio === "enviando").length;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <Contador tula={tula} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 truncate">
            {tula ? (tula.sin_etiqueta ? "Tula sin etiqueta" : `Tula ${tula.codigo}`) : "Escaneo de tulas"}
          </p>
          <p className="text-xs text-gray-500">
            {tula
              ? `${tula.leidos} leído${tula.leidos === 1 ? "" : "s"}${tula.total_esperado != null ? ` de ${tula.total_esperado}` : ""}${enviando ? ` · ${enviando} enviando a iMile` : ""}`
              : "Lee el código de la tula para empezar"}
          </p>
        </div>
        {tula && modo === "paquetes" && (
          <button
            type="button"
            onClick={() => { setModo("tula"); enfocar(); }}
            className="shrink-0 text-sm text-primary font-medium hover:underline"
          >
            Nueva tula
          </button>
        )}
      </header>

      <div className="p-4 flex flex-col gap-3 flex-1 w-full max-w-md mx-auto">
        {sinBase && (
          <div role="alert" className="rounded-lg px-4 py-3 bg-amber-100 text-amber-900 flex items-start gap-2 text-sm">
            <AlertTriangle size={18} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">No se ha subido la base de despacho de hoy</p>
              <p>
                Súbela antes de escanear: sin ella los paquetes salen "No está en la tabla" y sin zona.
              </p>
              <Link to="/subir-despacho" className="inline-block mt-1 font-medium underline">
                Subir base de despacho
              </Link>
            </div>
          </div>
        )}

        {/* Qué se va a leer ahora */}
        <div
          className={`rounded-lg px-4 py-2 text-sm font-medium text-center ${
            modo === "tula" ? "bg-amber-100 text-amber-900" : "bg-primary/10 text-primary"
          }`}
        >
          {modo === "tula" ? "Lee el código de la TULA" : "Lee los PAQUETES de la tula"}
        </div>

        {modo === "tula" && (
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <label className="block text-sm text-gray-700" htmlFor="total">
              Paquetes que trae <span className="text-gray-400">(vacío: se consulta en iMile)</span>
            </label>
            <input
              id="total"
              type="number"
              inputMode="numeric"
              min={0}
              value={totalEsperado}
              onChange={(e) => setTotalEsperado(e.target.value)}
              placeholder="Ej. 25"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-base outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              type="button"
              disabled={ocupado}
              onClick={() => abrirTula(null)}
              className="w-full border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-40"
            >
              Tula sin etiqueta
            </button>
            {tula && (
              <button
                type="button"
                onClick={() => { setModo("paquetes"); enfocar(); }}
                className="w-full text-sm text-gray-500 hover:underline"
              >
                Volver a la tula abierta
              </button>
            )}
          </div>
        )}

        <form onSubmit={enviarCampo} className="flex gap-2">
          <input
            ref={campoRef}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            autoFocus
            autoComplete="off"
            placeholder={modo === "tula" ? "Código de la tula" : "Serial del paquete"}
            className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-3 text-base font-mono outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            type="submit"
            disabled={!codigo.trim() || ocupado}
            className="shrink-0 bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg text-sm disabled:opacity-40"
          >
            {modo === "tula" ? "Abrir" : "Leer"}
          </button>
          <button
            type="button"
            onClick={() => setCamara((c) => !c)}
            aria-label={camara ? "Apagar cámara" : "Usar cámara"}
            className="shrink-0 border border-gray-300 rounded-lg px-3 text-gray-700 hover:bg-gray-50"
          >
            {camara ? <CameraOff size={20} /> : <Camera size={20} />}
          </button>
        </form>

        {camara && <div id={SCANNER_ELEMENT_ID} className="w-full rounded-xl overflow-hidden bg-black" />}

        {abriendo && (
          <div className="rounded-lg px-4 py-2.5 text-sm text-center bg-gray-100 text-gray-700">
            Abriendo la tula y consultando en iMile cuántos paquetes trae…
          </div>
        )}

        {tula && modo === "paquetes" && imileTotal && (
          <div
            className={`rounded-lg px-4 py-2.5 text-sm ${
              tula.total_esperado != null ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"
            }`}
          >
            {imileTotal}
          </div>
        )}

        {tula && modo === "paquetes" && !tula.sin_etiqueta && tula.total_esperado == null && (
          <TotalAMano onGuardar={guardarTotal} />
        )}

        {aviso && (
          <div role="alert" className="rounded-lg px-4 py-2.5 text-sm font-medium text-center bg-red-100 text-red-800">
            {aviso}
          </div>
        )}

        {conflicto && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
            <p className="font-medium text-amber-900">
              Tienes abierta la {conflicto.abierta.sin_etiqueta ? "tula sin etiqueta" : `tula ${conflicto.abierta.codigo}`}{" "}
              con {conflicto.abierta.leidos} paquete{conflicto.abierta.leidos === 1 ? "" : "s"}.
            </p>
            <p className="text-amber-800 mt-1">¿La cierro y abro la {conflicto.codigo ? `tula ${conflicto.codigo}` : "tula sin etiqueta"}?</p>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                disabled={ocupado}
                onClick={() => abrirTula(conflicto.codigo, true)}
                className="flex-1 bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-lg disabled:opacity-40"
              >
                Sí, cerrar y abrir
              </button>
              <button
                type="button"
                onClick={() => { setConflicto(null); enfocar(); }}
                className="flex-1 border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg bg-white"
              >
                No
              </button>
            </div>
          </div>
        )}

        {cerrada && <ResumenCierre tula={cerrada} />}

        {modo === "paquetes" && ultimo && <Destino destino={ultimo.destino} ya={ultimo.ya} />}

        {tula && lecturas.length > 0 && (
          <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
            {lecturas.map((l) => (
              <FilaLectura
                key={l.serial}
                lectura={l}
                onReenviar={() => leerPaquete(l.serial)}
                onReintentarImile={() => reintentarImile(l.serial)}
              />
            ))}
          </ul>
        )}

        {tula && modo === "paquetes" && (
          confirmarCierre ? (
            <div className="rounded-xl border border-gray-300 bg-white p-4 text-sm">
              <p className="font-medium text-gray-900">
                ¿Cerrar la tula con {tula.leidos} paquete{tula.leidos === 1 ? "" : "s"}?
              </p>
              <div className="flex gap-2 mt-3">
                <button
                  type="button"
                  disabled={ocupado || enviando > 0}
                  onClick={cerrarTula}
                  className="flex-1 bg-gray-800 hover:bg-gray-900 text-white font-medium py-2.5 rounded-lg disabled:opacity-40"
                >
                  {enviando > 0 ? "Esperando a iMile…" : "Sí, cerrar"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmarCierre(false)}
                  className="flex-1 border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg"
                >
                  No
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmarCierre(true)}
              className="w-full border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg text-sm hover:bg-gray-50 bg-white"
            >
              Cerrar tula
            </button>
          )
        )}
      </div>
    </div>
  );
}

/** Total escrito a mano con la tula ya abierta (cuando iMile no lo tenía). */
function TotalAMano({ onGuardar }: { onGuardar: (total: number) => void }) {
  const [valor, setValor] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valor.trim() !== "") onGuardar(Number(valor));
      }}
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2"
    >
      <label htmlFor="total-a-mano" className="text-sm text-gray-700 flex-1">
        ¿Cuántos paquetes trae?
      </label>
      <input
        id="total-a-mano"
        type="number"
        inputMode="numeric"
        min={0}
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        className="w-20 border border-gray-300 rounded-lg px-2 py-1.5 text-base outline-none focus:ring-2 focus:ring-primary"
      />
      <button
        type="submit"
        disabled={valor.trim() === ""}
        className="bg-gray-800 text-white text-sm font-medium px-3 py-1.5 rounded-lg disabled:opacity-40"
      >
        Guardar
      </button>
    </form>
  );
}

/** Paso 2.4: arriba a la izquierda. Con total esperado baja (faltan / sobran); sin él sube. */
function Contador({ tula }: { tula: Tula | null }) {
  if (!tula) {
    return (
      <div className="shrink-0 w-16 h-16 rounded-xl bg-gray-100 flex items-center justify-center text-gray-400">
        <PackageOpen size={28} />
      </div>
    );
  }
  const conTotal = tula.total_esperado != null;
  const sobran = conTotal && tula.contador < 0;
  const completa = conTotal && tula.contador === 0;
  const color = sobran ? "bg-red-100 text-red-700" : completa ? "bg-green-100 text-green-700" : "bg-primary/10 text-primary";
  return (
    <div className={`shrink-0 w-16 h-16 rounded-xl flex flex-col items-center justify-center ${color}`}>
      <span className="text-2xl font-bold leading-none">{Math.abs(tula.contador)}</span>
      <span className="text-[10px] uppercase mt-1">{!conTotal ? "leídos" : sobran ? "sobran" : "faltan"}</span>
    </div>
  );
}

/** Paso 2.6: el destino del último paquete, grande para leerlo de un vistazo. */
function Destino({ destino, ya }: { destino: DestinoPaquete; ya: boolean }) {
  const enZona = destino.en_tabla && destino.zona;
  const fondo = !destino.en_tabla ? "border-red-300 bg-red-50" : enZona ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50";
  return (
    <div className={`rounded-xl border-2 p-4 ${fondo}`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-4xl font-bold font-mono text-gray-900">{destino.ultimos_4}</span>
        <span className={`text-2xl font-bold ${enZona ? "text-green-800" : "text-amber-800"}`}>
          {destino.zona ?? destino.localidad ?? "—"}
        </span>
      </div>
      {destino.aviso && (
        <p className={`mt-1 font-semibold ${destino.en_tabla ? "text-amber-800" : "text-red-700"}`}>{destino.aviso}</p>
      )}
      {(destino.direccion_estandarizada || destino.direccion) && (
        <p className="mt-1 text-sm text-gray-700 break-words">{destino.direccion_estandarizada || destino.direccion}</p>
      )}
      {destino.zona && destino.localidad && <p className="text-xs text-gray-500">{destino.localidad}</p>}
      {ya && <p className="mt-2 text-sm font-medium text-amber-800">Ya estaba leído en esta tula: no se cuenta otra vez</p>}
    </div>
  );
}

const ETIQUETA_IMILE: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "iMile ✓", clase: "text-green-700" },
  repetido: { texto: "iMile: ya ingresado", clase: "text-amber-700" },
  bloqueado: { texto: "iMile: bloqueado", clase: "text-red-700" },
  error: { texto: "iMile: error", clase: "text-red-700" },
  sin_confirmar: { texto: "iMile: sin confirmar", clase: "text-amber-700" },
  omitido: { texto: "iMile apagado", clase: "text-gray-400" },
};

function FilaLectura({ lectura: l, onReenviar, onReintentarImile }: {
  lectura: Lectura; onReenviar: () => void; onReintentarImile: () => void;
}) {
  const etiqueta = l.imile ? ETIQUETA_IMILE[l.imile] ?? { texto: `iMile: ${l.imile}`, clase: "text-red-700" } : null;
  const reintentable = l.imile === "error" || l.imile === "bloqueado" || l.imile === "sin_confirmar";
  return (
    <li className="px-4 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-gray-800">
          <span className="text-gray-400">{l.serial.slice(0, -4)}</span>
          <span className="font-bold">{l.serial.slice(-4)}</span>
        </span>
        <span className="shrink-0 font-medium text-gray-700">{l.zona ?? ""}</span>
      </div>
      <div className="flex items-center justify-between gap-2 mt-0.5 text-xs">
        <span className={l.aviso ? "text-amber-700" : "text-gray-400"}>
          {l.envio === "falla" ? <span className="text-red-700">{l.error}</span> : l.aviso ?? ""}
        </span>
        {l.envio === "enviando" && <span className="text-gray-500">Enviando a iMile…</span>}
        {l.envio === "falla" && (
          <button type="button" onClick={onReenviar} className="inline-flex items-center gap-1 text-primary font-medium">
            <RotateCw size={12} /> Reenviar
          </button>
        )}
        {l.envio === "listo" && etiqueta && (
          <span className="flex items-center gap-2">
            <span className={etiqueta.clase} title={l.imileMensaje ?? undefined}>{etiqueta.texto}</span>
            {reintentable && (
              <button type="button" onClick={onReintentarImile} className="inline-flex items-center gap-1 text-primary font-medium">
                <RotateCw size={12} /> Reintentar
              </button>
            )}
          </span>
        )}
        {l.envio === "listo" && !etiqueta && l.imileMensaje && <span className="text-gray-500">{l.imileMensaje}</span>}
      </div>
      {l.envio === "listo" && reintentable && l.imileMensaje && (
        <p className="text-xs text-red-700 mt-0.5 break-words">{l.imileMensaje}</p>
      )}
    </li>
  );
}

/** Paso 2.8: lo que quedó al cerrar la tula. */
function ResumenCierre({ tula }: { tula: TulaDetalle }) {
  const conTotal = tula.total_esperado != null;
  const diferencia = tula.diferencia ?? 0;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <p className="font-semibold text-gray-900">
        {tula.sin_etiqueta ? "Tula sin etiqueta" : `Tula ${tula.codigo}`} cerrada
      </p>
      <dl className="grid grid-cols-3 gap-2 mt-3 text-center">
        <div className="rounded-lg bg-gray-50 p-2">
          <dd className="text-xl font-bold">{conTotal ? tula.total_esperado : "—"}</dd>
          <dt className="text-xs text-gray-500">Esperados</dt>
        </div>
        <div className="rounded-lg bg-gray-50 p-2">
          <dd className="text-xl font-bold">{tula.leidos}</dd>
          <dt className="text-xs text-gray-500">Leídos</dt>
        </div>
        <div className={`rounded-lg p-2 ${conTotal && diferencia !== 0 ? "bg-amber-50" : "bg-gray-50"}`}>
          <dd className="text-xl font-bold">{conTotal ? Math.abs(diferencia) : "—"}</dd>
          <dt className="text-xs text-gray-500">{!conTotal ? "Diferencia" : diferencia > 0 ? "Faltan" : diferencia < 0 ? "Sobran" : "Completa"}</dt>
        </div>
      </dl>
      {tula.faltantes && tula.faltantes.length > 0 && (
        <ListaSeriales titulo={`Faltaron (${tula.faltantes.length})`} seriales={tula.faltantes} clase="text-red-700" />
      )}
      {tula.no_esperados && tula.no_esperados.length > 0 && (
        <ListaSeriales
          titulo={`Leídos que no venían en esta tula según iMile (${tula.no_esperados.length})`}
          seriales={tula.no_esperados}
          clase="text-amber-700"
        />
      )}
      {tula.faltantes && tula.faltantes.length === 0 && (
        <p className="mt-3 text-sm text-green-700">Llegaron todos los paquetes que iMile dice que trae.</p>
      )}
    </div>
  );
}

function ListaSeriales({ titulo, seriales, clase }: { titulo: string; seriales: string[]; clase: string }) {
  return (
    <div className="mt-3">
      <p className={`text-sm font-medium ${clase}`}>{titulo}</p>
      <ul className="mt-1 grid grid-cols-2 gap-x-3 text-sm font-mono">
        {seriales.map((s) => (
          <li key={s} className="truncate">
            <span className="text-gray-400">{s.slice(0, -4)}</span>
            <span className="font-bold text-gray-900">{s.slice(-4)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
