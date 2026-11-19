import { useEffect, useRef } from "react";
import api from "@/api/client";
import type { ImileEstado } from "@/api/tulas";

export type CambioSerial = {
  tula_id: number;
  serial: string;
  imile_estado: ImileEstado;
  imile_mensaje: string | null;
};

/** La descarga de la tula en iMile terminó (o va en algo) y quizá ya se sabe su total. */
export type CambioTula = {
  tula_id: number;
  total_esperado: number | null;
  imile_descarga_estado: string | null;
  imile_total: string | null;
};

const CADA_MS = 4000;

/**
 * Mientras `activo` y la pantalla esté visible, pregunta al servidor qué paquetes del
 * usuario cambiaron de estado en iMile (los ingresa en segundo plano el servicio Go).
 * Sin señal simplemente no llega nada y se vuelve a intentar.
 */
export function useCambiosImile(
  activo: boolean,
  alCambiar: (cambios: CambioSerial[], tulas: CambioTula[]) => void,
) {
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
          const r = await api.get<{ cursor: string; seriales: CambioSerial[]; tulas?: CambioTula[] }>("/flujo/cambios", {
            params: cursor.current ? { desde: cursor.current } : {},
            timeout: 10_000,
          });
          cursor.current = r.data.cursor;
          const tulas = r.data.tulas ?? [];
          if (vivo && (r.data.seriales.length > 0 || tulas.length > 0)) fn.current(r.data.seriales, tulas);
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
