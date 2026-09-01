import api from "./client";
import type { PaginaCatalogo, Rol, Usuario } from "@/types/domain";

export const paginasAdminApi = {
  list: () => api.get<PaginaCatalogo[]>("/admin/paginas"),
};

export const usuariosAdminApi = {
  list: () => api.get<Usuario[]>("/admin/usuarios"),

  create: (data: { username: string; password: string; nombre_completo: string; email?: string; rol: string }) =>
    api.post<Usuario>("/admin/usuarios", data),

  update: (id: number, data: Partial<Pick<Usuario, "username" | "nombre_completo" | "email" | "rol" | "activo">>) =>
    api.put<Usuario>(`/admin/usuarios/${id}`, data),

  resetPassword: (id: number, password: string) =>
    api.put(`/admin/usuarios/${id}/password`, { password }),
};

export const rolesAdminApi = {
  list: () => api.get<Rol[]>("/admin/roles"),

  create: (data: { nombre: string; descripcion?: string; paginas: string[] }) =>
    api.post<Rol>("/admin/roles", data),

  update: (nombre: string, data: { descripcion?: string; activo?: boolean; paginas?: string[] }) =>
    api.put<Rol>(`/admin/roles/${nombre}`, data),
};
