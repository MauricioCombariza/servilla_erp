import axios from "axios";
import { useAuthStore } from "@/store/authStore";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const { refreshToken, logout, setTokens } = useAuthStore.getState();
      if (refreshToken && !error.config._retry) {
        error.config._retry = true;
        try {
          const res = await axios.post("/api/auth/refresh", { refresh_token: refreshToken });
          setTokens(res.data.access_token, res.data.refresh_token);
          error.config.headers.Authorization = `Bearer ${res.data.access_token}`;
          return api(error.config);
        } catch {
          logout();
        }
      } else {
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(error);
  }
);

export default api;
