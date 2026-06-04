import axios from "axios";

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  role: string;
  nombre_completo: string;
}

export const authApi = {
  login: (username: string, password: string) =>
    axios.post<LoginResponse>("/api/auth/login", { username, password }),
};
