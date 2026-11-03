import { Html5Qrcode, type Html5QrcodeCameraScanConfig, type Html5QrcodeSupportedFormats } from "html5-qrcode";
// iPhone (Safari) y otros navegadores no traen BarcodeDetector: este polyfill lo agrega con
// zxing-cpp en WebAssembly. Si el navegador ya lo trae (Chrome Android) no lo reemplaza.
import { prepareZXingModule } from "barcode-detector/polyfill";
import zxingWasmUrl from "zxing-wasm/reader/zxing_reader.wasm?url";

// El .wasm se sirve desde nuestro dominio (por defecto lo bajaría de jsDelivr).
const ZXING_OVERRIDES = {
  locateFile: (ruta: string, prefijo: string) => (ruta.endsWith(".wasm") ? zxingWasmUrl : prefijo + ruta),
};
prepareZXingModule({ overrides: ZXING_OVERRIDES });

/**
 * Configuración común de la cámara para leer QR y códigos de barras de los paquetes.
 *
 * - Decodifica con BarcodeDetector: el nativo en Chrome Android y el polyfill (zxing-cpp/WASM)
 *   en iPhone. El decodificador en JavaScript de html5-qrcode casi no leía las etiquetas.
 * - El recuadro es cuadrado y proporcional al video: un QR completo cabe adentro
 *   (el de 250×150 de antes lo cortaba).
 * - Pide resolución HD y enfoque continuo; por defecto la cámara abría en baja resolución.
 */
export function crearEscaner(elementId: string, formatos: Html5QrcodeSupportedFormats[]): Html5Qrcode {
  // Se empieza a bajar el WASM ya, mientras la cámara arranca
  void prepareZXingModule({ overrides: ZXING_OVERRIDES, fireImmediately: true }).catch(() => {});
  return new Html5Qrcode(elementId, {
    formatsToSupport: formatos,
    verbose: false,
    experimentalFeatures: { useBarCodeDetectorIfSupported: true },
  });
}

export const CAMARA_TRASERA: MediaTrackConstraints = { facingMode: "environment" };

export const CONFIG_ESCANER: Html5QrcodeCameraScanConfig = {
  fps: 15,
  qrbox: (ancho, alto) => {
    const lado = Math.max(150, Math.floor(Math.min(ancho, alto) * 0.8));
    return { width: lado, height: lado };
  },
  // En html5-qrcode 2.3.8 estas restricciones reemplazan al primer argumento de start(),
  // por eso la cámara trasera va también aquí.
  videoConstraints: {
    facingMode: "environment",
    width: { ideal: 1280 },
    height: { ideal: 720 },
    advanced: [{ focusMode: "continuous" } as MediaTrackConstraintSet],
  },
};
