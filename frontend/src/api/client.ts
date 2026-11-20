import axios from "axios";
import { useAuthStore } from "@/store/authStore";
import { marcarActividad } from "@/utils/actividad";

const api = axios.create({ baseURL: "/api" });

/** Segundos que le quedan al token (0 si no se puede leer). */
function segundosRestantes(token: string): number {
  try {
    const cuerpo = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const { exp } = JSON.parse(atob(cuerpo)) as { exp?: number };
    return exp ? exp - Date.now() / 1000 : 0;
  } catch {
    return 0;
  }
}

class SesionTerminada extends Error {}

let renovando: Promise<string> | null = null;

/**
 * Pide un token de acceso nuevo con el refresh (una sola petición aunque la pidan varias
 * a la vez). Si el servidor dice que la sesión terminó (inactividad, cerrada por un
 * administrador, cambio de clave), cierra la sesión del navegador.
 */
function renovar(): Promise<string> {
  if (renovando) return renovando;
  renovando = (async () => {
    const { refreshToken, logout, setTokens, setUser, setClave, role, nombreCompleto } = useAuthStore.getState();
    if (!refreshToken) throw new SesionTerminada();
    try {
      const res = await axios.post("/api/auth/refresh", { refresh_token: refreshToken });
      setTokens(res.data.access_token, res.data.refresh_token);
      setUser(res.data.role ?? role, res.data.nombre_completo ?? nombreCompleto, res.data.page_keys ?? []);
      setClave(res.data.debe_cambiar_clave ?? false, res.data.dias_para_vencer ?? null);
      // La clave venció: el token nuevo solo sirve para cambiarla. Lo pendiente del
      // celular (cola offline) se queda guardado y se envía después del cambio.
      if (res.data.debe_cambiar_clave && window.location.pathname !== "/cambiar-clave") {
        window.location.assign("/cambiar-clave");
      }
      return res.data.access_token as string;
    } catch (e) {
      // Solo si el servidor rechaza el refresh: un corte de red no debe cerrar la sesión
      // (lo que se escaneó sin señal sigue en la cola del celular)
      const estado = (e as { response?: { status?: number } })?.response?.status;
      if (estado === 401 || estado === 403) {
        logout();
        throw new SesionTerminada();
      }
      throw e;
    }
  })().finally(() => {
    renovando = null;
  });
  return renovando;
}

api.interceptors.request.use(async (config) => {
  // Las lecturas automáticas (GET cada X segundos) no cuentan como actividad; lo que la
  // persona manda (escaneos, guardar) sí. El teclado y los toques los cuenta <Inactividad/>.
  // (El aviso de actividad, /auth/actividad, no se cuenta a sí mismo.)
  if ((config.method ?? "get").toLowerCase() !== "get" && !config.url?.endsWith("/auth/actividad")) {
    marcarActividad();
  }
  let token = useAuthStore.getState().token;
  // El token de acceso dura pocos minutos: se renueva antes de que venza, así una carga
  // de archivo no choca con un 401 a mitad de camino.
  if (token && segundosRestantes(token) < 30 && useAuthStore.getState().refreshToken) {
    try {
      token = await renovar();
    } catch {
      // sin red: se manda con el token que hay; si el servidor lo rechaza, abajo se maneja
    }
  }
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status !== 401) return Promise.reject(error);
    const { refreshToken, logout } = useAuthStore.getState();
    if (!refreshToken || error.config?._retry) {
      logout();
      return Promise.reject(error);
    }
    error.config._retry = true;
    let token: string;
    try {
      token = await renovar();
    } catch {
      return Promise.reject(error);
    }
    if (useAuthStore.getState().debeCambiarClave) return Promise.reject(error);
    // Un archivo ya enviado no se reenvía solo: la persona lo vuelve a subir
    if (error.config?.data instanceof FormData) return Promise.reject(error);
    error.config.headers.Authorization = `Bearer ${token}`;
    return api(error.config);
  }
);

export default api;
