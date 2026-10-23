import { NavLink } from "react-router-dom";
import { MapPinned, PackageOpen, Upload } from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const PASOS = [
  { to: "/subir-despacho", label: "Subir base", icon: Upload, pageKey: "paquetes_despacho" },
  { to: "/escaneo-tulas", label: "Escaneo de tulas", icon: PackageOpen, pageKey: "escaneo_tulas" },
  { to: "/asignacion-zonas", label: "Asignación de zonas", icon: MapPinned, pageKey: "asignacion_zonas" },
];

/** Los tres pasos del día con los paquetes, para pasar de una pantalla a otra. */
export function FlujoPaquetesNav({ className = "" }: { className?: string }) {
  const { role, pageKeys } = useAuthStore();
  // Misma regla que el menú lateral: solo las pantallas a las que tiene acceso
  const pasos = PASOS.filter((p) => role === "administrador" || pageKeys.includes(p.pageKey));
  if (pasos.length < 2) return null;

  return (
    <nav aria-label="Flujo de paquetes" className={`grid gap-1.5 ${className}`} style={{ gridTemplateColumns: `repeat(${pasos.length}, minmax(0, 1fr))` }}>
      {pasos.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs sm:text-sm font-medium text-center transition-colors ${
              isActive
                ? "border-primary bg-primary text-white"
                : "border-gray-300 bg-white text-gray-700 hover:border-primary hover:text-primary"
            }`
          }
        >
          <Icon size={16} className="shrink-0" />
          <span className="leading-tight">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
