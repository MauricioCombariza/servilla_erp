import api from "./client";

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface Geocerca {
  id: number;
  nombre: string;
  poligono: GeoJSONPolygon;
  area_m2: number;
  activo: boolean;
  creado_por: string | null;
  fecha_creacion: string;
  fecha_actualizacion: string;
}

export interface GeocercaCreate {
  nombre: string;
  poligono: GeoJSONPolygon;
}

export interface GeocercaUpdate {
  nombre?: string;
  activo?: boolean;
}

export const geocercasApi = {
  listar: (activo?: boolean) =>
    api.get<Geocerca[]>("/geocercas/", { params: activo === undefined ? undefined : { activo } }),

  crear: (body: GeocercaCreate) => api.post<Geocerca>("/geocercas/", body),

  actualizar: (id: number, body: GeocercaUpdate) => api.patch<Geocerca>(`/geocercas/${id}`, body),

  eliminar: (id: number) => api.delete<Geocerca>(`/geocercas/${id}`),
};
