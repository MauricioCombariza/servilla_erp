import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  role: string | null;
  nombreCompleto: string | null;
  pageKeys: string[];
  setTokens: (token: string, refreshToken: string) => void;
  setUser: (role: string, nombreCompleto: string, pageKeys: string[]) => void;
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
      setTokens: (token, refreshToken) => set({ token, refreshToken }),
      setUser: (role, nombreCompleto, pageKeys) => set({ role, nombreCompleto, pageKeys }),
      logout: () =>
        set({ token: null, refreshToken: null, role: null, nombreCompleto: null, pageKeys: [] }),
    }),
    { name: "servilla-auth" }
  )
);
