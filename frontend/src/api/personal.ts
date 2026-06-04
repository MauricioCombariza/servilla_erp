import api from "./client";
import type { Ciudad, Personal, PersonalCiudad } from "@/types/domain";

export const personalApi = {
  list: (params?: { tipo?: string; activo?: boolean }) =>
    api.get<Personal[]>("/personal/", { params }),

  get: (id: number) => api.get<Personal & { ciudades: PersonalCiudad[] }>(`/personal/${id}`),

  create: (data: Omit<Personal, "id" | "activo" | "fecha_creacion" | "fecha_modificacion">) =>
    api.post<Personal>("/personal/", data),

  update: (id: number, data: Partial<Personal>) =>
    api.put<Personal>(`/personal/${id}`, data),

  delete: (id: number) => api.delete(`/personal/${id}`),

  listCiudades: () => api.get<Ciudad[]>("/personal/ciudades"),

  listCiudadesPersonal: (personalId: number) =>
    api.get<PersonalCiudad[]>(`/personal/${personalId}/ciudades`),

  createCiudad: (personalId: number, data: Omit<PersonalCiudad, "id" | "personal_id" | "activo">) =>
    api.post<PersonalCiudad>(`/personal/${personalId}/ciudades`, data),

  updateCiudad: (personalId: number, ciudadId: number, data: Partial<PersonalCiudad>) =>
    api.put<PersonalCiudad>(`/personal/${personalId}/ciudades/${ciudadId}`, data),

  deleteCiudad: (personalId: number, ciudadId: number) =>
    api.delete(`/personal/${personalId}/ciudades/${ciudadId}`),
};
