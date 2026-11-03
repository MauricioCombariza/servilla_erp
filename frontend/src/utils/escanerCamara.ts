import { Html5Qrcode, type Html5QrcodeCameraScanConfig, type Html5QrcodeSupportedFormats } from "html5-qrcode";

/**
 * Configuración común de la cámara para leer QR y códigos de barras de los paquetes.
 *
 * - Usa el BarcodeDetector nativo del navegador cuando existe (Chrome Android): es mucho más
 *   rápido y confiable que el decodificador en JavaScript (ZXing), que casi no leía las etiquetas.
 * - El recuadro es cuadrado y proporcional al video: un QR completo cabe adentro
 *   (el de 250×150 de antes lo cortaba).
 * - Pide resolución HD y enfoque continuo; por defecto la cámara abría en baja resolución.
 */
export function crearEscaner(elementId: string, formatos: Html5QrcodeSupportedFormats[]): Html5Qrcode {
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
