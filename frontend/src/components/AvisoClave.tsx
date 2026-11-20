import { Link, useLocation } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

// Igual a CLAVE_AVISO_DIAS del backend (app/config.py)
const AVISO_DIAS = 7;

/** Aviso en todas las pantallas cuando a la clave le quedan pocos días (vence cada 45). */
export function AvisoClave() {
  const sesion = useAuthStore((s) => s.sesion);
  const debe = useAuthStore((s) => s.debeCambiarClave);
  const dias = useAuthStore((s) => s.diasParaVencer);
  const { pathname } = useLocation();

  if (!sesion || debe || dias === null || dias > AVISO_DIAS || pathname === "/cambiar-clave") return null;
  return (
    <div role="status" className="fixed top-3 inset-x-3 z-50 mx-auto max-w-md rounded-lg bg-amber-50 border border-amber-300 text-amber-900 shadow px-4 py-2.5 flex items-center gap-3 text-sm">
      <KeyRound size={16} className="flex-shrink-0" />
      <span className="flex-1">
        Tu contraseña vence {dias <= 0 ? "hoy" : `en ${dias} ${dias === 1 ? "día" : "días"}`}.
      </span>
      <Link to="/cambiar-clave" className="font-medium underline">Cambiarla</Link>
    </div>
  );
}
