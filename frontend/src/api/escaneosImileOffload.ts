import api from "./client";

export interface EscaneoImileOffload {
  id: number;
  fecha: string;
  cod_men: string;
  nombre_mensajero: string;
  serial: string;
  resultado: "ok" | "error" | "sesion_expirada";
  detalle: string | null;
  fecha_creacion: string | null;
}

export interface ImileStatus {
  sesion_configurada: boolean;
  conectado: boolean;
  detalle: string | null;
}

export const escaneosImileOffloadApi = {
  registrar: (data: { serial: string; cod_men: string; nombre_mensajero: string }) =>
    api.post<EscaneoImileOffload>("/escaneos-imile-offload/", data),

  listarDelDia: (cod_men: string) =>
    api.get<EscaneoImileOffload[]>("/escaneos-imile-offload/", { params: { cod_men } }),

  status: () => api.get<ImileStatus>("/escaneos-imile-offload/status"),
};
