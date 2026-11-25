import axios from "axios";
import api from "@/api/client";
import { useAuthStore } from "@/store/authStore";

export interface LoginResponse {
  access_token: string;
  role: string;
  nombre_completo: string;
  page_keys: string[];
  debe_cambiar_clave: boolean;
  dias_para_vencer: number | null;
  inactividad_minutos?: number;
  /** Solo al terminar de configurar el segundo factor (se muestran una vez) */
  codigos_respaldo?: string[] | null;
}

/** Clave correcta; falta el código del celular ("verificar") o configurarlo ("configurar"). */
export interface MfaPendiente {
  mfa_paso: "verificar" | "configurar";
  mfa_token: string;
  nombre_completo: string;
}

/** QR nuevo; su token solo sirve para confirmarlo con el primer código (mfa/reactivar). */
export interface MfaQrNuevo {
  mfa_token: string;
  secreto: string;
  uri: string;
}

export function esMfaPendiente(d: LoginResponse | MfaPendiente): d is MfaPendiente {
  return "mfa_paso" in d;
}

export const authApi = {
  login: (username: string, password: string) =>
    axios.post<LoginResponse | MfaPendiente>("/api/auth/login", { username, password }),
  mfaConfigurar: (mfa_token: string) =>
    axios.post<{ secreto: string; uri: string }>("/api/auth/mfa/configurar", { mfa_token }),
  mfaActivar: (mfa_token: string, codigo: string) =>
    axios.post<LoginResponse>("/api/auth/mfa/activar", { mfa_token, codigo }),
  mfaVerificar: (mfa_token: string, codigo: string) =>
    axios.post<LoginResponse>("/api/auth/mfa/verificar", { mfa_token, codigo }),
  /** Cambio de celular: con el código actual (o uno de respaldo) entrega un QR nuevo */
  mfaReconfigurar: (mfa_token: string, codigo: string) =>
    axios.post<MfaQrNuevo>("/api/auth/mfa/reconfigurar", { mfa_token, codigo }),
  mfaReactivar: (mfa_token: string, codigo: string) =>
    axios.post<LoginResponse>("/api/auth/mfa/reactivar", { mfa_token, codigo }),
  cambiarClave: (clave_actual: string, clave_nueva: string) =>
    api.post<LoginResponse>("/auth/cambiar-clave", { clave_actual, clave_nueva }),
};

/** Guarda en el store la sesión que devuelven login, refresh y cambiar-clave. */
export function guardarSesion(d: LoginResponse) {
  const s = useAuthStore.getState();
  s.setToken(d.access_token);
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
  // La cookie HttpOnly viaja sola; el servidor la borra
  void axios.post("/api/auth/logout", { motivo, refresh_token: s.legadoRefresh ?? undefined }).catch(() => {});
  s.logout();
}
