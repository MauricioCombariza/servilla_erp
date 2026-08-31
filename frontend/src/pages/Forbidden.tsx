import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";

export function Forbidden() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <ShieldAlert size={40} className="text-gray-400 mb-4" />
      <h1 className="text-lg font-semibold text-gray-900 mb-1">Sin permisos</h1>
      <p className="text-sm text-gray-500 mb-6">Tu rol no tiene acceso a esta página.</p>
      <Link to="/" className="text-sm text-primary hover:underline">
        Volver al inicio
      </Link>
    </div>
  );
}
