import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "@/api/client";
import { cerrarSesion } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";
import { marcarActividad, ultimaActividad } from "@/utils/actividad";

/**
 * Cierre de sesión por inactividad (el servidor dice cuántos minutos; hoy 2 horas).
 *  - Cuenta como actividad: teclado (incluida la pistola lectora), toques, clics, rueda y
 *    lo que la persona envía al servidor (escaneos, guardar). Las consultas automáticas
 *    de cada pantalla NO cuentan.
 *  - Un minuto antes avisa; al cumplirse cierra la sesión también en el servidor.
 *  - Si la persona trabaja sin pedirle nada al servidor (llenando un formulario largo),
 *    se le avisa al servidor cada 2 minutos para que no la dé por inactiva.
 */
const EVENTOS = ["pointerdown", "keydown", "touchstart", "wheel", "mousemove"] as const;
const AVISO_MS = 60_000;
const LATIDO_MS = 2 * 60_000;

export function Inactividad() {
  const sesion = useAuthStore((s) => s.sesion);
  const minutos = useAuthStore((s) => s.inactividadMinutos);
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [quedan, setQuedan] = useState<number | null>(null);
  const ultimoLatido = useRef(Date.now());

  const activa = sesion && pathname !== "/login";

  useEffect(() => {
    if (!activa) return;
    marcarActividad();
    ultimoLatido.current = Date.now();
    for (const e of EVENTOS) window.addEventListener(e, marcarActividad, { passive: true, capture: true });

    const limite = minutos * 60_000;
    const t = setInterval(() => {
      const ahora = Date.now();
      const quieto = ahora - ultimaActividad();
      if (quieto >= limite) {
        clearInterval(t);
        setQuedan(null);
        cerrarSesion("inactividad");
        navigate("/login?motivo=inactividad", { replace: true });
        return;
      }
      setQuedan(quieto >= limite - AVISO_MS ? Math.ceil((limite - quieto) / 1000) : null);
      // Hubo actividad desde el último aviso al servidor y ya pasó un rato
      if (ultimaActividad() > ultimoLatido.current && ahora - ultimoLatido.current >= LATIDO_MS) {
        ultimoLatido.current = ahora;
        void api.post("/auth/actividad").catch(() => {});
      }
    }, 1_000);

    return () => {
      clearInterval(t);
      for (const e of EVENTOS) window.removeEventListener(e, marcarActividad, { capture: true });
    };
  }, [activa, minutos, navigate]);

  if (!activa || quedan === null) return null;
  return (
    <div role="alertdialog" aria-live="assertive"
         className="fixed inset-x-3 top-3 z-50 mx-auto max-w-md rounded-lg bg-amber-50 border border-amber-300 shadow-lg px-4 py-3 text-sm text-amber-900 flex items-center gap-3">
      <span className="flex-1">
        Por inactividad, la sesión se cerrará en <strong>{quedan} s</strong>.
      </span>
      <button type="button" onClick={() => { marcarActividad(); setQuedan(null); }}
              className="rounded-md bg-amber-600 text-white font-medium px-3 py-1.5">
        Seguir trabajando
      </button>
    </div>
  );
}
