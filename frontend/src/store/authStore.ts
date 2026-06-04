import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  role: string | null;
  nombreCompleto: string | null;
  setTokens: (token: string, refreshToken: string) => void;
  setUser: (role: string, nombreCompleto: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      role: null,
      nombreCompleto: null,
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      setUser: (role, nombreCompleto) => set({ role, nombreCompleto }),
      logout: () => set({ token: null, refreshToken: null, role: null, nombreCompleto: null }),
    }),
    { name: "servilla-auth" }
  )
);
