import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { laboresApi } from "@/api/labores";
import { escaneosCarrytApi, type EscaneoCarryt } from "@/api/escaneosCarryt";

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

function usePersonalLookup() {
  const [codigo, setCodigo] = useState("");
  const [info, setInfo] = useState<{ id: number; nombre_completo: string } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (codigo.length !== 4) {
      setInfo(null);
      setError(false);
      return;
    }
    let cancelled = false;
    laboresApi
      .lookupPersonalCodigo(codigo)
      .then((r) => {
        if (!cancelled) {
          setInfo(r.data);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInfo(null);
          setError(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [codigo]);

  return {
    codigo,
    setCodigo,
    info,
    error,
    reset: () => {
      setCodigo("");
      setInfo(null);
      setError(false);
    },
  };
}

type Mensajero = { codigo: string; nombre_completo: string };
type Feedback = { type: "success" | "error"; message: string } | null;

export function EscaneoCarrytPage() {
  const lookup = usePersonalLookup();
  const [mensajero, setMensajero] = useState<Mensajero | null>(null);
  const [manualSerial, setManualSerial] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const lastScanRef = useRef<{ serial: string; at: number }>({ serial: "", at: 0 });
  const qc = useQueryClient();

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
        <button onClick={cambiarMensajero} className="text-sm text-primary hover:underline flex-shrink-0">
          Cambiar mensajero
        </button>
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
    </div>
  );
}
