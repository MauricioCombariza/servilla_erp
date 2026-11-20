import axios from "axios";
import api from "@/api/client";
import { useAuthStore } from "@/store/authStore";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  role: string;
  nombre_completo: string;
  page_keys: string[];
  debe_cambiar_clave: boolean;
  dias_para_vencer: number | null;
  inactividad_minutos?: number;
}

export const authApi = {
  login: (username: string, password: string) =>
    axios.post<LoginResponse>("/api/auth/login", { username, password }),
  cambiarClave: (clave_actual: string, clave_nueva: string) =>
    api.post<LoginResponse>("/auth/cambiar-clave", { clave_actual, clave_nueva }),
};

/** Guarda en el store la sesión que devuelven login, refresh y cambiar-clave. */
export function guardarSesion(d: LoginResponse) {
  const s = useAuthStore.getState();
  s.setTokens(d.access_token, d.refresh_token);
  s.setUser(d.role, d.nombre_completo, d.page_keys ?? []);
  s.setClave(d.debe_cambiar_clave ?? false, d.dias_para_vencer ?? null);
  if (d.inactividad_minutos) s.setInactividad(d.inactividad_minutos);
}

/**
 * Cierra la sesión en el servidor (los tokens dejan de servir) y en el navegador.
 * Si no hay red, igual se cierra aquí; el servidor la cierra sola por inactividad.
 */
export function cerrarSesion(motivo: "salida" | "inactividad" = "salida") {
  const s = useAuthStore.getState();
  if (s.refreshToken) {
    void axios.post("/api/auth/logout", { refresh_token: s.refreshToken, motivo }).catch(() => {});
  }
  s.logout();
}
