import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "@/api/client";
import { useAuthStore } from "@/store/authStore";

/**
 * Mantiene la app al día sin pedir que la gente vuelva a iniciar sesión:
 *  - Permisos: los page_keys se guardan al iniciar sesión; si después se le da una página
 *    nueva al rol (o llega una página nueva con un despliegue), se vuelven a pedir al
 *    abrir, al volver a la app y cada 5 min.
 *  - Versión: cada compilación lleva su número (version.json). Si hay una más nueva se
 *    avisa, y al volver a la app (estaba en segundo plano) se recarga sola.
 */
const CADA_MS = 5 * 60_000;

type Me = { rol: string; nombre_completo: string; page_keys: string[] };

async function versionPublicada(): Promise<string | null> {
  try {
    const r = await fetch(`/version.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return null;
    return ((await r.json()) as { version?: string }).version ?? null;
  } catch {
    return null; // sin señal: se revisa en la próxima vuelta
  }
}

export function AlDia() {
  const token = useAuthStore((s) => s.token);
  const [hayNueva, setHayNueva] = useState(false);

  useEffect(() => {
    let vivo = true;

    async function revisar(alVolver: boolean) {
      const publicada = await versionPublicada();
      if (!vivo || !publicada || import.meta.env.DEV) return;
      if (publicada !== __APP_VERSION__) {
        // Volvió a la app desde segundo plano: buen momento para recargar sin interrumpir
        if (alVolver) {
          window.location.reload();
          return;
        }
        setHayNueva(true);
      }
      if (useAuthStore.getState().token) {
        try {
          const me = (await api.get<Me>("/auth/me")).data;
          if (vivo) useAuthStore.getState().setUser(me.rol, me.nombre_completo, me.page_keys);
        } catch {
          // sin señal o sesión vencida: el cliente ya maneja el 401
        }
      }
    }

    void revisar(false);
    const t = setInterval(() => void revisar(false), CADA_MS);
    const alCambiar = () => {
      if (document.visibilityState === "visible") void revisar(true);
    };
    document.addEventListener("visibilitychange", alCambiar);
    return () => {
      vivo = false;
      clearInterval(t);
      document.removeEventListener("visibilitychange", alCambiar);
    };
  }, [token]);

  if (!hayNueva) return null;
  return (
    <div role="status" className="fixed bottom-3 inset-x-3 z-50 mx-auto max-w-md rounded-lg bg-gray-900 text-white shadow-lg px-4 py-3 flex items-center gap-3 text-sm">
      <span className="flex-1">Hay una versión nueva del ERP.</span>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="inline-flex items-center gap-1.5 rounded-md bg-white text-gray-900 font-medium px-3 py-1.5"
      >
        <RefreshCw size={14} /> Actualizar
      </button>
    </div>
  );
}
