import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { Download, X } from "lucide-react";
import { escaneosCarrytApi, type EscaneoCarryt } from "@/api/escaneosCarryt";
import { personalApi } from "@/api/personal";
import { useAuthStore } from "@/store/authStore";
import { usePersonalLookup } from "@/hooks/usePersonalLookup";

const SCANNER_ELEMENT_ID = "carryt-qr-reader";
const SCAN_FORMATS = [
  Html5QrcodeSupportedFormats.QR_CODE,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.CODE_39,
  Html5QrcodeSupportedFormats.CODE_93,
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.EAN_8,
  Html5QrcodeSupportedFormats.ITF,
  Html5QrcodeSupportedFormats.UPC_A,
  Html5QrcodeSupportedFormats.UPC_E,
  Html5QrcodeSupportedFormats.CODABAR,
];

type Mensajero = { codigo: string; nombre_completo: string };
type Feedback = { type: "success" | "error"; message: string } | null;

const PUEDE_VER_REPORTES = ["administrador", "logistica", "mensajero"];
const PUEDE_REASIGNAR = ["administrador", "operaciones", "mensajero"];

function inicioDeMes(): string {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export function EscaneoCarrytPage() {
  const lookup = usePersonalLookup();
  const [mensajero, setMensajero] = useState<Mensajero | null>(null);
  const [manualSerial, setManualSerial] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const lastScanRef = useRef<{ serial: string; at: number }>({ serial: "", at: 0 });
  const qc = useQueryClient();
  const role = useAuthStore((s) => s.role);
  const [descargandoReporte, setDescargandoReporte] = useState<"dia" | "unicas" | "rango" | null>(
    null
  );
  const [errorReporte, setErrorReporte] = useState("");
  const [rangoDesde, setRangoDesde] = useState(inicioDeMes());
  const [rangoHasta, setRangoHasta] = useState(() => new Date().toISOString().slice(0, 10));
  const [showReasignar, setShowReasignar] = useState(false);

  const escaneosQuery = useQuery({
    queryKey: ["escaneos-carryt", mensajero?.codigo],
    queryFn: () => escaneosCarrytApi.listarDelDia(mensajero!.codigo).then((r) => r.data),
    enabled: !!mensajero,
  });

  const registrarMutation = useMutation({
    mutationFn: (serial: string) =>
      escaneosCarrytApi.registrar({
        serial,
        cod_men: mensajero!.codigo,
        nombre_mensajero: mensajero!.nombre_completo,
      }),
    onSuccess: (res) => {
      setFeedback({ type: "success", message: `Serial ${res.data.serial} registrado` });
      qc.setQueryData<EscaneoCarryt[]>(["escaneos-carryt", mensajero?.codigo], (old) => [
        res.data,
        ...(old ?? []),
      ]);
      if (navigator.vibrate) navigator.vibrate(80);
    },
    onError: (err: any, serial: string) => {
      const detail = err?.response?.data?.detail ?? "No se pudo registrar el serial";
      setFeedback({ type: "error", message: `${serial}: ${detail}` });
      if (navigator.vibrate) navigator.vibrate([50, 50, 50]);
    },
  });

  function handleSerial(rawSerial: string) {
    const serial = rawSerial.trim();
    if (!serial || !mensajero) return;

    const now = Date.now();
    if (lastScanRef.current.serial === serial && now - lastScanRef.current.at < 2000) return;
    lastScanRef.current = { serial, at: now };

    registrarMutation.mutate(serial);
  }

  useEffect(() => {
    if (!feedback) return;
    const t = setTimeout(() => setFeedback(null), 2500);
    return () => clearTimeout(t);
  }, [feedback]);

  useEffect(() => {
    if (!mensajero) return;

    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, {
      formatsToSupport: SCAN_FORMATS,
      verbose: false,
    });

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 150 } },
        (decodedText) => handleSerial(decodedText),
        () => {}
      )
      .catch(() => {
        setFeedback({ type: "error", message: "No se pudo acceder a la cámara" });
      });

    return () => {
      scanner
        .stop()
        .then(() => scanner.clear())
        .catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mensajero]);

  function cambiarMensajero() {
    setMensajero(null);
    lookup.reset();
    setFeedback(null);
  }

  function submitManual(e: React.FormEvent) {
    e.preventDefault();
    handleSerial(manualSerial);
    setManualSerial("");
  }

  async function handleDescargarReporte(tipo: "dia" | "unicas" | "rango") {
    setDescargandoReporte(tipo);
    setErrorReporte("");
    try {
      const hoy = new Date().toISOString().slice(0, 10);
      let r;
      let nombreArchivo;
      if (tipo === "dia") {
        r = await escaneosCarrytApi.descargarExcelDia();
        nombreArchivo = `carryt_${hoy}.xlsx`;
      } else if (tipo === "unicas") {
        r = await escaneosCarrytApi.descargarExcelRutasUnicas();
        nombreArchivo = `rutas_unicas_${hoy}.xlsx`;
      } else {
        r = await escaneosCarrytApi.descargarExcelRango(rangoDesde, rangoHasta);
        nombreArchivo = `carryt_${rangoDesde}_a_${rangoHasta}.xlsx`;
      }
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = nombreArchivo;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErrorReporte(msg ?? "Error al generar el archivo");
    } finally {
      setDescargandoReporte(null);
    }
  }

  const escaneos = escaneosQuery.data ?? [];

  if (!mensajero) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 p-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 w-full max-w-sm">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Escaneo Carryt</h1>
          <p className="text-sm text-gray-500 mb-6">Ingresa el código del mensajero</p>

          <input
            value={lookup.codigo}
            onChange={(e) => lookup.setCodigo(e.target.value.replace(/\D/g, "").slice(0, 4))}
            inputMode="numeric"
            maxLength={4}
            autoFocus
            placeholder="0000"
            className="w-full border border-gray-300 rounded-lg px-4 py-3 text-2xl tracking-widest text-center font-mono focus:ring-2 focus:ring-primary focus:border-primary outline-none"
          />

          <div className="h-6 mt-2 text-center text-sm">
            {lookup.info && <span className="text-green-600">✓ {lookup.info.nombre_completo}</span>}
            {lookup.error && <span className="text-red-600">❌ No encontrado</span>}
          </div>

          <button
            type="button"
            disabled={!lookup.info}
            onClick={() =>
              lookup.info &&
              setMensajero({ codigo: lookup.codigo, nombre_completo: lookup.info.nombre_completo })
            }
            className="w-full bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-lg text-base transition-colors disabled:opacity-40 disabled:cursor-not-allowed mt-2"
          >
            Confirmar
          </button>

          {role && PUEDE_VER_REPORTES.includes(role) && (
            <div className="mt-6 pt-5 border-t border-gray-100">
              <p className="text-xs font-medium text-gray-500 mb-2">Reportes de hoy</p>
              {errorReporte && <p className="text-xs text-red-600 mb-2">{errorReporte}</p>}
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => handleDescargarReporte("dia")}
                  disabled={descargandoReporte !== null}
                  className="inline-flex items-center justify-center gap-1.5 bg-gray-800 hover:bg-gray-900 text-white font-medium py-2.5 rounded-lg text-sm transition-colors disabled:opacity-40"
                >
                  <Download size={14} />
                  {descargandoReporte === "dia" ? "Generando..." : "Excel del día"}
                </button>
                <button
                  type="button"
                  onClick={() => handleDescargarReporte("unicas")}
                  disabled={descargandoReporte !== null}
                  className="inline-flex items-center justify-center gap-1.5 bg-gray-800 hover:bg-gray-900 text-white font-medium py-2.5 rounded-lg text-sm transition-colors disabled:opacity-40"
                >
                  <Download size={14} />
                  {descargandoReporte === "unicas" ? "Generando..." : "Rutas únicas"}
                </button>
              </div>

              <p className="text-xs font-medium text-gray-500 mt-4 mb-2">Envíos por rango de fechas</p>
              <div className="flex items-center gap-2 mb-2">
                <input
                  type="date"
                  value={rangoDesde}
                  onChange={(e) => setRangoDesde(e.target.value)}
                  className="flex-1 border border-gray-300 rounded-lg px-2 py-2 text-xs"
                />
                <span className="text-gray-400">—</span>
                <input
                  type="date"
                  value={rangoHasta}
                  onChange={(e) => setRangoHasta(e.target.value)}
                  className="flex-1 border border-gray-300 rounded-lg px-2 py-2 text-xs"
                />
              </div>
              <button
                type="button"
                onClick={() => handleDescargarReporte("rango")}
                disabled={descargandoReporte !== null || !rangoDesde || !rangoHasta}
                className="w-full inline-flex items-center justify-center gap-1.5 bg-gray-800 hover:bg-gray-900 text-white font-medium py-2.5 rounded-lg text-sm transition-colors disabled:opacity-40"
              >
                <Download size={14} />
                {descargandoReporte === "rango" ? "Generando..." : "Descargar rango"}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 p-4 flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-gray-900">{mensajero.nombre_completo}</p>
          <p className="text-xs text-gray-500">Código {mensajero.codigo} · Carryt</p>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {role && PUEDE_REASIGNAR.includes(role) && (
            <button
              type="button"
              onClick={() => setShowReasignar(true)}
              className="text-sm text-primary hover:underline"
            >
              Reasignar paquete
            </button>
          )}
          <button onClick={cambiarMensajero} className="text-sm text-primary hover:underline">
            Cambiar mensajero
          </button>
        </div>
      </header>

      <div className="p-4 flex flex-col gap-4 flex-1 overflow-hidden">
        <div className="text-center">
          <span className="inline-block bg-primary/10 text-primary font-semibold px-4 py-1.5 rounded-full text-sm">
            {escaneos.length} paquete{escaneos.length === 1 ? "" : "s"} escaneado{escaneos.length === 1 ? "" : "s"} hoy
          </span>
        </div>

        <div id={SCANNER_ELEMENT_ID} className="w-full rounded-xl overflow-hidden bg-black" />

        {feedback && (
          <div
            className={`rounded-lg px-4 py-2.5 text-sm font-medium text-center ${
              feedback.type === "success" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
            }`}
          >
            {feedback.message}
          </div>
        )}

        <form onSubmit={submitManual} className="flex gap-2">
          <input
            value={manualSerial}
            onChange={(e) => setManualSerial(e.target.value)}
            placeholder="Ingresar serial manualmente"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2.5 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none"
          />
          <button
            type="submit"
            disabled={!manualSerial.trim()}
            className="bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg text-sm disabled:opacity-40"
          >
            Agregar
          </button>
        </form>

        <div className="flex-1 overflow-y-auto bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
          {escaneos.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-6">Aún no hay paquetes escaneados</p>
          )}
          {escaneos.map((e) => (
            <div key={e.id} className="px-4 py-2.5 flex items-center justify-between text-sm">
              <span className="font-mono text-gray-800">{e.serial}</span>
              <span className="text-gray-400 text-xs">
                {e.fecha_creacion
                  ? new Date(e.fecha_creacion).toLocaleTimeString("es-CO", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : ""}
              </span>
            </div>
          ))}
        </div>
      </div>

      {showReasignar && (
        <ReasignarModal
          onClose={() => setShowReasignar(false)}
          currentCodMen={mensajero.codigo}
          qc={qc}
        />
      )}
    </div>
  );
}

// ── Modal de reasignación de mensajero ────────────────────────────────────────
interface ReasignarModalProps {
  onClose: () => void;
  currentCodMen: string;
  qc: QueryClient;
}

function ReasignarModal({ onClose, currentCodMen, qc }: ReasignarModalProps) {
  const [serialInput, setSerialInput] = useState("");
  const [found, setFound] = useState<EscaneoCarryt | null>(null);
  const [nuevoCodMen, setNuevoCodMen] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [exito, setExito] = useState("");

  const { data: personal = [] } = useQuery({
    queryKey: ["personal", true],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
  });

  async function buscar(e: React.FormEvent) {
    e.preventDefault();
    if (!serialInput.trim()) return;
    setBuscando(true);
    setError("");
    setExito("");
    setFound(null);
    try {
      const r = await escaneosCarrytApi.buscarPorSerial(serialInput.trim());
      setFound(r.data);
      setNuevoCodMen(r.data.cod_men);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "No se encontró el paquete");
    } finally {
      setBuscando(false);
    }
  }

  async function confirmar() {
    if (!found) return;
    const p = personal.find((p) => p.codigo === nuevoCodMen);
    if (!p) {
      setError("Selecciona un mensajero válido");
      return;
    }
    setGuardando(true);
    setError("");
    setExito("");
    try {
      const r = await escaneosCarrytApi.reasignar(found.id, {
        cod_men: p.codigo,
        nombre_mensajero: p.nombre_completo,
      });
      setFound(r.data);
      setExito(`Paquete ${r.data.serial} reasignado a ${r.data.nombre_mensajero}`);
      qc.invalidateQueries({ queryKey: ["escaneos-carryt", currentCodMen] });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "No se pudo reasignar el paquete");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-sm">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Reasignar paquete</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <form onSubmit={buscar} className="flex gap-2">
            <input
              value={serialInput}
              onChange={(e) => setSerialInput(e.target.value)}
              placeholder="Serial del paquete"
              autoFocus
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2.5 text-sm font-mono focus:ring-2 focus:ring-primary focus:border-primary outline-none"
            />
            <button
              type="submit"
              disabled={!serialInput.trim() || buscando}
              className="bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg text-sm disabled:opacity-40"
            >
              {buscando ? "..." : "Buscar"}
            </button>
          </form>

          {found && (
            <div className="space-y-3">
              <div className="bg-gray-50 rounded-lg px-3 py-2.5 text-sm space-y-1">
                <p className="font-mono text-gray-800">{found.serial}</p>
                <p className="text-xs text-gray-500">
                  Escaneado el {found.fecha} · actualmente en {found.nombre_mensajero} (
                  {found.cod_men})
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Nuevo mensajero
                </label>
                <select
                  value={nuevoCodMen}
                  onChange={(e) => setNuevoCodMen(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none"
                >
                  {personal.map((p) => (
                    <option key={p.id} value={p.codigo}>
                      {p.codigo} — {p.nombre_completo}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="button"
                onClick={confirmar}
                disabled={guardando || nuevoCodMen === found.cod_men}
                className="w-full bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-lg text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {guardando ? "Guardando..." : "Confirmar reasignación"}
              </button>
            </div>
          )}

          {error && (
            <div className="rounded-lg px-4 py-2.5 text-sm font-medium text-center bg-red-100 text-red-800">
              {error}
            </div>
          )}
          {exito && (
            <div className="rounded-lg px-4 py-2.5 text-sm font-medium text-center bg-green-100 text-green-800">
              {exito}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
