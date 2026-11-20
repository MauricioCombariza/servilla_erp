import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Check, X } from "lucide-react";
import { authApi, cerrarSesion, guardarSesion } from "@/api/auth";
import { useAuthStore } from "@/store/authStore";

// Mismas reglas que el backend (app/auth/claves.py); el backend tiene la última palabra
const MIN_LARGO = 12;

function reglas(clave: string) {
  return [
    { ok: clave.length >= MIN_LARGO, texto: `Al menos ${MIN_LARGO} caracteres (lleva ${clave.length})`, falta: `tener al menos ${MIN_LARGO} caracteres (lleva ${clave.length})` },
    { ok: /\p{L}/u.test(clave), texto: "Letras", falta: "tener letras" },
    { ok: /\d/.test(clave), texto: "Números", falta: "tener números" },
  ];
}

/** Cambio de clave: obligatorio cuando venció (cada 45 días) o es temporal; voluntario si no. */
export function CambiarClavePage() {
  const sesion = useAuthStore((s) => s.sesion);
  const debe = useAuthStore((s) => s.debeCambiarClave);
  const dias = useAuthStore((s) => s.diasParaVencer);
  const navigate = useNavigate();
  const [actual, setActual] = useState("");
  const [nueva, setNueva] = useState("");
  const [repite, setRepite] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  if (!sesion) return <Navigate to="/login" replace />;

  const lista = reglas(nueva);
  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    // El botón nunca se queda muerto: si algo falta, se dice qué
    if (!actual) return setError("Escribe tu contraseña actual (la que usabas para entrar).");
    const faltan = lista.filter((r) => !r.ok).map((r) => r.falta);
    if (faltan.length) return setError(`La contraseña nueva debe ${faltan.join(" y ")}.`);
    if (nueva !== repite) return setError("La contraseña nueva y la repetición no coinciden.");
    setEnviando(true);
    setError("");
    try {
      const r = await authApi.cambiarClave(actual, nueva);
      guardarSesion(r.data);
      navigate("/", { replace: true });
    } catch (err: unknown) {
      const detalle = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setError(typeof detalle === "string" ? detalle : "No se pudo cambiar la contraseña");
    } finally {
      setEnviando(false);
    }
  }

  const campo = "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none";

  return (
    <div className="min-h-screen flex items-center justify-center bg-brand-bg p-4">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 border-t-4 border-t-brand-gold p-8 w-full max-w-sm">
        <h1 className="text-lg font-semibold text-gray-900 mb-1">Cambiar contraseña</h1>
        <p className="text-sm text-gray-500 mb-6">
          {debe
            ? "Tu contraseña venció o es temporal. Escribe la que usabas y luego una nueva de al menos 12 letras y números (por ejemplo, dos palabras y un número)."
            : dias !== null
              ? `Tu contraseña vence en ${Math.max(dias, 0)} días.`
              : "Pon una contraseña nueva."}
        </p>

        <form onSubmit={enviar} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Contraseña actual (la que usabas)</label>
            <input type="password" autoComplete="current-password" autoFocus value={actual}
              onChange={(e) => setActual(e.target.value)} className={campo} />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Contraseña nueva</label>
            <input type="password" autoComplete="new-password" value={nueva}
              onChange={(e) => setNueva(e.target.value)} className={campo} />
            <ul className="mt-2 space-y-0.5">
              {lista.map((r) => (
                <li key={r.texto} className={`flex items-center gap-1.5 text-xs ${r.ok ? "text-green-700" : "text-gray-500"}`}>
                  {r.ok ? <Check size={12} /> : <X size={12} />} {r.texto}
                </li>
              ))}
              <li className="text-xs text-gray-500 pl-[18px]">Distinta de las últimas 5 y sin tu usuario</li>
            </ul>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Repite la contraseña nueva</label>
            <input type="password" autoComplete="new-password" value={repite}
              onChange={(e) => setRepite(e.target.value)} className={campo} />
            {repite && repite !== nueva && <p className="text-xs text-red-600 mt-1">No coinciden</p>}
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          <button type="submit" disabled={enviando}
            className="w-full bg-primary hover:bg-primary-hover text-white font-medium py-2 rounded-lg text-sm transition-colors disabled:opacity-60">
            {enviando ? "Guardando..." : "Cambiar contraseña"}
          </button>
          <button type="button"
            onClick={() => { if (debe) { cerrarSesion(); navigate("/login"); } else { navigate(-1); } }}
            className="w-full text-sm text-gray-500 hover:text-gray-700">
            {debe ? "Cerrar sesión" : "Cancelar"}
          </button>
        </form>
      </div>
    </div>
  );
}
