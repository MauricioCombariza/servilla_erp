import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { FileDown, RefreshCw } from "lucide-react";
import { devolucionesApi, type Devolucion } from "@/api/devoluciones";
import { extraerErrorBlob } from "@/utils/blobError";

const SCANNER_ELEMENT_ID = "devoluciones-qr-reader";
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

const ESCANEADOS_DIA_KEY = ["devoluciones-escaneados-dia"];

type Feedback = { type: "success" | "warning" | "error"; message: string } | null;

function horaCorta(iso: string) {
  return new Date(iso).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
}

function hoyISO() {
  return new Date().toISOString().slice(0, 10);
}

export function EscaneoDevolucionesPage() {
  const queryClient = useQueryClient();
  const {
    data: escaneados = [],
    isLoading: cargandoLista,
    refetch,
  } = useQuery({
    queryKey: ESCANEADOS_DIA_KEY,
    queryFn: () => devolucionesApi.escaneadosDia().then((r) => r.data),
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  });
  const [manualSerial, setManualSerial] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [descargando, setDescargando] = useState<"word" | "excel" | null>(null);
  const [errorDocumento, setErrorDocumento] = useState("");
  const lastScanRef = useRef<{ serial: string; at: number }>({ serial: "", at: 0 });

  const escanearMutation = useMutation({
    mutationFn: (serial: string) => devolucionesApi.escanearSerial(serial),
    onSuccess: (res) => {
      const d = res.data;
      if (d.ya_escaneado) {
        const hora = d.escaneado_previamente_en ? horaCorta(d.escaneado_previamente_en) : null;
        setFeedback({
          type: "warning",
          message: `${d.serial}: ya había sido escaneado antes${hora ? ` (a las ${hora})` : ""}`,
        });
        if (navigator.vibrate) navigator.vibrate([40, 40, 40]);
      } else {
        setFeedback({ type: "success", message: `Serial ${d.serial} marcado como devolución` });
        if (navigator.vibrate) navigator.vibrate(80);
      }
      queryClient.setQueryData<Devolucion[]>(ESCANEADOS_DIA_KEY, (prev = []) =>
        prev.some((x) => x.serial === d.serial)
          ? prev.map((x) => (x.serial === d.serial ? d : x))
          : [d, ...prev]
      );
    },
    onError: (err: unknown, serial: string) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setFeedback({ type: "error", message: `${serial}: ${detail ?? "No se pudo registrar el serial"}` });
      if (navigator.vibrate) navigator.vibrate([50, 50, 50]);
    },
  });

  function handleSerial(rawSerial: string) {
    const serial = rawSerial.trim();
    if (!serial) return;

    const now = Date.now();
    if (lastScanRef.current.serial === serial && now - lastScanRef.current.at < 2000) return;
    lastScanRef.current = { serial, at: now };

    escanearMutation.mutate(serial);
  }

  useEffect(() => {
    if (!feedback) return;
    const t = setTimeout(() => setFeedback(null), 2500);
    return () => clearTimeout(t);
  }, [feedback]);

  useEffect(() => {
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
  }, []);

  function submitManual(e: React.FormEvent) {
    e.preventDefault();
    handleSerial(manualSerial);
    setManualSerial("");
  }

  async function handleDescargarReporte(formato: "word" | "excel") {
    setDescargando(formato);
    setErrorDocumento("");
    try {
      const fecha = hoyISO();
      const r =
        formato === "word"
          ? await devolucionesApi.reporteDiaWord(fecha)
          : await devolucionesApi.reporteDiaExcel(fecha);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `acta_devolucion_${fecha}.${formato === "word" ? "docx" : "xlsx"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setErrorDocumento(await extraerErrorBlob(e));
    } finally {
      setDescargando(null);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 p-4">
        <p className="font-semibold text-gray-900">Escaneo Devoluciones</p>
        <p className="text-xs text-gray-500">Pistolea cada paquete devuelto</p>
      </header>

      <div className="p-4 flex flex-col gap-4 flex-1 overflow-hidden">
        <div className="text-center">
          <span className="inline-block bg-primary/10 text-primary font-semibold px-4 py-1.5 rounded-full text-sm">
            {escaneados.length} paquete{escaneados.length === 1 ? "" : "s"} escaneado{escaneados.length === 1 ? "" : "s"} hoy
          </span>
        </div>

        <div id={SCANNER_ELEMENT_ID} className="w-full rounded-xl overflow-hidden bg-black" />

        {feedback && (
          <div
            className={`rounded-lg px-4 py-2.5 text-sm font-medium text-center ${
              feedback.type === "success"
                ? "bg-green-100 text-green-800"
                : feedback.type === "warning"
                  ? "bg-amber-100 text-amber-800"
                  : "bg-red-100 text-red-800"
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
          {cargandoLista && (
            <p className="text-center text-sm text-gray-400 py-6">Cargando lo escaneado hoy…</p>
          )}
          {!cargandoLista && escaneados.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-6">Aún no hay paquetes escaneados hoy</p>
          )}
          {escaneados.map((d) => (
            <div key={d.serial} className="px-4 py-2.5 text-sm">
              <p className="font-mono text-gray-800">{d.serial}</p>
              <p className="text-gray-500 text-xs">{d.nombre ?? "Sin nombre"} · {d.localidad ?? "Sin localidad"}</p>
            </div>
          ))}
        </div>

        {errorDocumento && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-3">
            <p className="text-sm text-red-700">{errorDocumento}</p>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => handleDescargarReporte("word")}
            disabled={escaneados.length === 0 || descargando !== null}
            className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-xl text-sm transition-colors disabled:opacity-40"
          >
            <FileDown size={16} />
            {descargando === "word" ? "Generando..." : "Acta (Word)"}
          </button>
          <button
            type="button"
            onClick={() => handleDescargarReporte("excel")}
            disabled={escaneados.length === 0 || descargando !== null}
            className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-xl text-sm transition-colors disabled:opacity-40"
          >
            <FileDown size={16} />
            {descargando === "excel" ? "Generando..." : "Acta (Excel)"}
          </button>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center justify-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 text-center"
        >
          <RefreshCw size={12} />
          Actualizar lista
        </button>
      </div>
    </div>
  );
}
