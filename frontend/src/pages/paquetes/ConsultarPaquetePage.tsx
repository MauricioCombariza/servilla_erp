import { useEffect, useRef, useState } from "react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";
import { Camera, CameraOff } from "lucide-react";
import { paquetesDespachoApi } from "@/api/paquetesDespacho";
import type { DestinoPaquete } from "@/api/tulas";
import { FlujoPaquetesNav } from "./FlujoPaquetesNav";

const SCANNER_ELEMENT_ID = "consultar-qr-reader";
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
 * Se lee el QR de un paquete y se muestra su sector (zona), dirección y localidad.
 * Solo consulta: no cuenta el paquete en ninguna tula ni lo ingresa en iMile.
 * Sirve con el lector Bluetooth (escribe en el campo y manda Enter) o con la cámara.
 */
export function ConsultarPaquetePage() {
  const [codigo, setCodigo] = useState("");
  const [destino, setDestino] = useState<DestinoPaquete | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [camara, setCamara] = useState(false);
  const campoRef = useRef<HTMLInputElement>(null);
  const ultimaLecturaRef = useRef({ codigo: "", at: 0 });

  async function consultar(raw: string) {
    const cod = raw.trim();
    if (!cod) return;
    const ahora = Date.now();
    if (ultimaLecturaRef.current.codigo === cod && ahora - ultimaLecturaRef.current.at < ANTIRREBOTE_MS) return;
    ultimaLecturaRef.current = { codigo: cod, at: ahora };

    setOcupado(true);
    setError(null);
    try {
      const r = (await paquetesDespachoApi.destino(cod)).data;
      setDestino(r);
      if (navigator.vibrate) navigator.vibrate(r.zona ? 80 : [80, 60, 80]);
    } catch {
      setDestino(null);
      setError("No se pudo consultar el paquete. Revisa la conexión e intenta otra vez.");
    } finally {
      setOcupado(false);
      setCodigo("");
      campoRef.current?.focus();
    }
  }

  // La cámara llama siempre a la versión más reciente
  const consultarRef = useRef(consultar);
  consultarRef.current = consultar;

  useEffect(() => {
    if (!camara) return;
    const scanner = new Html5Qrcode(SCANNER_ELEMENT_ID, { formatsToSupport: SCAN_FORMATS, verbose: false });
    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 150 } },
        (texto) => void consultarRef.current(texto),
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

  function enviarCampo(e: React.FormEvent) {
    e.preventDefault();
    void consultar(codigo);
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="mx-auto w-full max-w-md space-y-4">
        <FlujoPaquetesNav />
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 space-y-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Consultar paquete</h1>
            <p className="text-sm text-gray-500">Lee el QR del paquete para ver su sector, dirección y localidad.</p>
          </div>

          <form onSubmit={enviarCampo} className="flex gap-2">
            <input
              ref={campoRef}
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              autoFocus
              autoComplete="off"
              placeholder="Serial del paquete"
              className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-3 text-base font-mono outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              type="submit"
              disabled={!codigo.trim() || ocupado}
              className="shrink-0 bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg text-sm disabled:opacity-40"
            >
              Consultar
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
        </div>

        {error && (
          <div role="alert" className="rounded-lg px-4 py-3 bg-red-100 text-red-800 text-sm">
            {error}
          </div>
        )}

        {destino && <Resultado destino={destino} />}
      </div>
    </div>
  );
}

function Resultado({ destino }: { destino: DestinoPaquete }) {
  const enZona = destino.en_tabla && destino.zona;
  const fondo = !destino.en_tabla ? "border-red-300 bg-red-50" : enZona ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50";
  return (
    <div className={`rounded-xl border-2 p-4 space-y-3 ${fondo}`}>
      <p className="font-mono text-sm text-gray-500 break-all">
        {destino.serial.slice(0, -4)}
        <span className="text-gray-900 font-bold">{destino.ultimos_4}</span>
      </p>
      {destino.aviso && (
        <p className={`font-semibold ${destino.en_tabla ? "text-amber-800" : "text-red-700"}`}>{destino.aviso}</p>
      )}
      {destino.en_tabla && (
        <dl className="space-y-2">
          <Dato titulo="Sector" valor={destino.zona ?? "Fuera de zona"} grande />
          <Dato titulo="Dirección" valor={destino.direccion ?? "—"} detalle={destino.direccion_estandarizada} />
          <Dato titulo="Localidad" valor={destino.localidad ?? "Sin localidad"} />
        </dl>
      )}
    </div>
  );
}

function Dato({ titulo, valor, detalle, grande = false }: {
  titulo: string; valor: string; detalle?: string | null; grande?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-gray-500">{titulo}</dt>
      <dd className={grande ? "text-3xl font-bold text-gray-900" : "text-base text-gray-900 break-words"}>{valor}</dd>
      {detalle && detalle !== valor && <dd className="text-xs text-gray-500 font-mono">{detalle}</dd>}
    </div>
  );
}
