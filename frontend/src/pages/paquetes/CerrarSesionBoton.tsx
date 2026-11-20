import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { cerrarSesion as cerrarEnServidor } from "@/api/auth";

/** Cerrar sesión desde las pantallas del flujo de paquetes, que no tienen el menú lateral. */
export function CerrarSesionBoton({ className = "" }: { className?: string }) {
  const nombreCompleto = useAuthStore((s) => s.nombreCompleto);
  const navigate = useNavigate();

  function cerrarSesion() {
    // En el celular es fácil tocarlo sin querer en medio del escaneo
    if (!window.confirm(`¿Cerrar la sesión${nombreCompleto ? ` de ${nombreCompleto}` : ""}?`)) return;
    cerrarEnServidor();
    navigate("/login", { replace: true });
  }

  return (
    <button
      type="button"
      onClick={cerrarSesion}
      aria-label="Cerrar sesión"
      title="Cerrar sesión"
      className={`shrink-0 text-gray-600 hover:text-red-600 p-1 ${className}`}
    >
      <LogOut size={22} />
    </button>
  );
}
