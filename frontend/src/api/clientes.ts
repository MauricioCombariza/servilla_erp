import api from "./client";
import type { Cliente, ClienteWithPrecios, PrecioCliente } from "@/types/domain";

export const clientesApi = {
  list: (activo?: boolean) =>
    api.get<Cliente[]>("/clientes/", { params: activo !== undefined ? { activo } : {} }),

  get: (id: number) => api.get<ClienteWithPrecios>(`/clientes/${id}`),

  create: (data: Omit<Cliente, "id" | "activo" | "fecha_creacion" | "fecha_modificacion">) =>
    api.post<Cliente>("/clientes/", data),

  update: (id: number, data: Partial<Cliente>) =>
    api.put<Cliente>(`/clientes/${id}`, data),

  delete: (id: number) => api.delete(`/clientes/${id}`),

  listPrecios: (clienteId: number, soloActivos = true) =>
    api.get<PrecioCliente[]>(`/clientes/${clienteId}/precios`, {
      params: { solo_activos: soloActivos },
    }),

  createPrecio: (clienteId: number, data: Omit<PrecioCliente, "id" | "cliente_id" | "activo">) =>
    api.post<PrecioCliente>(`/clientes/${clienteId}/precios`, data),

  updatePrecio: (clienteId: number, precioId: number, data: Partial<PrecioCliente>) =>
    api.put<PrecioCliente>(`/clientes/${clienteId}/precios/${precioId}`, data),

  deletePrecio: (clienteId: number, precioId: number) =>
    api.delete(`/clientes/${clienteId}/precios/${precioId}`),
};
