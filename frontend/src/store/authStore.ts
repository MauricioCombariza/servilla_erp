import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  role: string | null;
  nombreCompleto: string | null;
  pageKeys: string[];
  // Clave vencida o temporal: solo se puede ir a /cambiar-clave (el token no sirve para más)
  debeCambiarClave: boolean;
  diasParaVencer: number | null;
  // Minutos sin actividad tras los que se cierra la sesión (lo dice el servidor al entrar)
  inactividadMinutos: number;
  setTokens: (token: string, refreshToken: string) => void;
  setUser: (role: string, nombreCompleto: string, pageKeys: string[]) => void;
  setClave: (debeCambiarClave: boolean, diasParaVencer: number | null) => void;
  setInactividad: (minutos: number) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      role: null,
      nombreCompleto: null,
      pageKeys: [],
      debeCambiarClave: false,
      diasParaVencer: null,
      inactividadMinutos: 120,
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      setUser: (role, nombreCompleto, pageKeys) => set({ role, nombreCompleto, pageKeys }),
      setClave: (debeCambiarClave, diasParaVencer) => set({ debeCambiarClave, diasParaVencer }),
      setInactividad: (inactividadMinutos) => set({ inactividadMinutos }),
      logout: () =>
        set({ token: null, refreshToken: null, role: null, nombreCompleto: null, pageKeys: [],
              debeCambiarClave: false, diasParaVencer: null }),
    }),
    { name: "servilla-auth" }
  )
);
