import { useEffect, useRef } from "react";
import api from "@/api/client";
import type { ImileEstado } from "@/api/tulas";

export type CambioSerial = {
  tula_id: number;
  serial: string;
  imile_estado: ImileEstado;
  imile_mensaje: string | null;
};

const CADA_MS = 4000;

/**
 * Mientras `activo` y la pantalla esté visible, pregunta al servidor qué paquetes del
 * usuario cambiaron de estado en iMile (los ingresa en segundo plano el servicio Go).
 * Sin señal simplemente no llega nada y se vuelve a intentar.
 */
export function useCambiosImile(activo: boolean, alCambiar: (cambios: CambioSerial[]) => void) {
  const cursor = useRef<string | null>(null);
  const fn = useRef(alCambiar);
  fn.current = alCambiar;

  useEffect(() => {
    if (!activo) return;
    let vivo = true;
    let t: ReturnType<typeof setTimeout>;
    const pedir = async () => {
      if (document.visibilityState === "visible") {
        try {
          const r = await api.get<{ cursor: string; seriales: CambioSerial[] }>("/flujo/cambios", {
            params: cursor.current ? { desde: cursor.current } : {},
            timeout: 10_000,
          });
          cursor.current = r.data.cursor;
          if (vivo && r.data.seriales.length > 0) fn.current(r.data.seriales);
        } catch {
          // sin señal: en la próxima vuelta
        }
      }
      if (vivo) t = setTimeout(pedir, CADA_MS);
    };
    void pedir();
    return () => {
      vivo = false;
      clearTimeout(t);
    };
  }, [activo]);
}
