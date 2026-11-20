import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  // Token de acceso: SOLO en memoria (dura minutos). El de renovación va en una cookie
  // HttpOnly que el JavaScript no puede leer: un XSS no se lleva la sesión.
  token: string | null;
  // Hay una sesión abierta (la cookie existe): al recargar se pide un token nuevo
  sesion: boolean;
  // Refresh que guardaban en localStorage las sesiones de antes de la cookie: se manda
  // una vez para pasarlas a la cookie y se borra.
  legadoRefresh: string | null;
  role: string | null;
  nombreCompleto: string | null;
  pageKeys: string[];
  // Clave vencida o temporal: solo se puede ir a /cambiar-clave (el token no sirve para más)
  debeCambiarClave: boolean;
  diasParaVencer: number | null;
  // Minutos sin actividad tras los que se cierra la sesión (lo dice el servidor al entrar)
  inactividadMinutos: number;
  setToken: (token: string) => void;
  setUser: (role: string, nombreCompleto: string, pageKeys: string[]) => void;
  setClave: (debeCambiarClave: boolean, diasParaVencer: number | null) => void;
  setInactividad: (minutos: number) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      sesion: false,
      legadoRefresh: null,
      role: null,
      nombreCompleto: null,
      pageKeys: [],
      debeCambiarClave: false,
      diasParaVencer: null,
      inactividadMinutos: 120,
      setToken: (token) => set({ token, sesion: true, legadoRefresh: null }),
      setUser: (role, nombreCompleto, pageKeys) => set({ role, nombreCompleto, pageKeys }),
      setClave: (debeCambiarClave, diasParaVencer) => set({ debeCambiarClave, diasParaVencer }),
      setInactividad: (inactividadMinutos) => set({ inactividadMinutos }),
      logout: () =>
        set({ token: null, sesion: false, legadoRefresh: null, role: null, nombreCompleto: null,
              pageKeys: [], debeCambiarClave: false, diasParaVencer: null }),
    }),
    {
      name: "servilla-auth",
      version: 1,
      // Nada de tokens de acceso en localStorage
      partialize: ({ token: _token, ...resto }) => resto,
      // v0 guardaba token y refreshToken aquí
      migrate: (viejo, version) => {
        const v = (viejo ?? {}) as Record<string, unknown>;
        if (version < 1) {
          const { token: _t, refreshToken, ...resto } = v;
          return { ...resto, sesion: Boolean(refreshToken),
                   legadoRefresh: typeof refreshToken === "string" ? refreshToken : null } as unknown as AuthState;
        }
        return v as unknown as AuthState;
      },
    }
  )
);
