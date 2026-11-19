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
  setTokens: (token: string, refreshToken: string) => void;
  setUser: (role: string, nombreCompleto: string, pageKeys: string[]) => void;
  setClave: (debeCambiarClave: boolean, diasParaVencer: number | null) => void;
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
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      setUser: (role, nombreCompleto, pageKeys) => set({ role, nombreCompleto, pageKeys }),
      setClave: (debeCambiarClave, diasParaVencer) => set({ debeCambiarClave, diasParaVencer }),
      logout: () =>
        set({ token: null, refreshToken: null, role: null, nombreCompleto: null, pageKeys: [],
              debeCambiarClave: false, diasParaVencer: null }),
    }),
    { name: "servilla-auth" }
  )
);
