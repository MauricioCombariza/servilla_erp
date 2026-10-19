import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Copy, Share2, X } from "lucide-react";
import { vistaZonasApi } from "@/api/vistaZonas";

/**
 * Paso 2.7: QR con el enlace del día para que los demás vean en su celular, sin iniciar
 * sesión, los paquetes de sus zonas. El enlace vence a la medianoche de Bogotá.
 */
export function CompartirVista({ onCerrar }: { onCerrar: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    let vigente = true;
    vistaZonasApi
      .enlace()
      .then(async ({ data }) => {
        // La URL sale de donde está abierta esta pantalla (en la prueba local, el túnel)
        const completa = window.location.origin + data.ruta;
        const imagen = await QRCode.toDataURL(completa, { width: 320, margin: 2 });
        if (!vigente) return;
        setUrl(completa);
        setQr(imagen);
      })
      .catch(() => vigente && setError("No se pudo generar el enlace. Intenta de nuevo."));
    return () => {
      vigente = false;
    };
  }, []);

  async function copiar() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      // Sin permiso de portapapeles (http): queda el enlace a la vista para copiarlo a mano
    }
  }

  function compartir() {
    if (url && navigator.share) navigator.share({ title: "Paquetes por zona", url }).catch(() => {});
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onCerrar}
    >
      <div
        role="dialog"
        aria-label="Compartir vista por zonas"
        className="bg-white rounded-xl w-full max-w-sm p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="font-semibold text-gray-900">Vista por zonas</p>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="text-gray-500 p-1">
            <X size={20} />
          </button>
        </div>

        {error && <p className="text-sm text-red-700">{error}</p>}
        {!error && !qr && <p className="text-sm text-gray-500 py-16 text-center">Generando QR…</p>}

        {qr && url && (
          <>
            <p className="text-sm text-gray-600">
              Que cada persona escanee este QR con su celular y elija sus zonas.
            </p>
            <img src={qr} alt="QR de la vista por zonas" className="w-full max-w-[280px] mx-auto" />
            <p className="text-xs text-gray-500 break-all select-all bg-gray-50 rounded p-2">{url}</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={copiar}
                className="flex-1 border border-gray-300 text-gray-700 font-medium py-2 rounded-lg text-sm flex items-center justify-center gap-1.5"
              >
                <Copy size={16} /> {copiado ? "Copiado" : "Copiar"}
              </button>
              {typeof navigator.share === "function" && (
                <button
                  type="button"
                  onClick={compartir}
                  className="flex-1 bg-primary text-white font-medium py-2 rounded-lg text-sm flex items-center justify-center gap-1.5"
                >
                  <Share2 size={16} /> Compartir
                </button>
              )}
            </div>
            <p className="text-xs text-gray-400 text-center">Vence hoy a la medianoche.</p>
          </>
        )}
      </div>
    </div>
  );
}
