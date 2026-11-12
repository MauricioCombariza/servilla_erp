import api from "./client";

export type Prioridad = "baja" | "media" | "alta" | "critica";
export type EstadoTarea = "pendiente" | "en_progreso" | "completada" | "cancelada";
export type CategoriaProyecto = "seguridad_informacion" | "nuevo_proyecto" | "operativo" | "otro";
export type EstadoProyecto = "planeado" | "en_curso" | "pausado" | "completado" | "cancelado";
export type Frecuencia = "diaria" | "semanal" | "mensual";

export interface Tarea {
  id: number;
  titulo: string;
  descripcion: string | null;
  proyecto_id: number | null;
  proyecto_nombre: string | null;
  recurrente_id: number | null;
  responsable_id: number | null;
  responsable_nombre: string | null;
  creado_por: number | null;
  fecha_programada: string;
  fecha_limite: string | null;
  prioridad: Prioridad;
  estado: EstadoTarea;
  esfuerzo_horas: string | null;
  completada_en: string | null;
  anio_iso: number;
  semana_iso: number;
  demorada: boolean;
  dias_atraso: number;
}

export interface TareaInput {
  titulo: string;
  descripcion?: string | null;
  proyecto_id?: number | null;
  responsable_id?: number | null;
  fecha_programada: string;
  fecha_limite?: string | null;
  prioridad?: Prioridad;
  esfuerzo_horas?: number | null;
}

export type TareaCambios = Partial<TareaInput> & { estado?: EstadoTarea };

export interface SemanaDetalle {
  anio: number;
  semana: number;
  lunes: string;
  domingo: string;
  dias: { fecha: string; tareas: Tarea[] }[];
}

export interface SemanaResumen {
  anio: number;
  semana: number;
  lunes: string;
  domingo: string;
  total: number;
  completadas: number;
  pendientes: number;
  demoradas: number;
  es_actual: boolean;
}

export interface SemanasAnio {
  anio: number;
  semana_actual: number | null;
  semanas: SemanaResumen[];
}

export interface Proyecto {
  id: number;
  nombre: string;
  descripcion: string | null;
  categoria: CategoriaProyecto;
  responsable_id: number | null;
  responsable_nombre: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  estado: EstadoProyecto;
  color: string | null;
  total_tareas: number;
  completadas: number;
  demoradas: number;
  avance: number;
}

export interface ProyectoDetalle extends Proyecto {
  semanas: { anio: number; semana: number; lunes: string; total: number; completadas: number; demoradas: number }[];
  tareas: Tarea[];
}

export interface ProyectoInput {
  nombre: string;
  descripcion?: string | null;
  categoria: CategoriaProyecto;
  responsable_id?: number | null;
  fecha_inicio: string;
  fecha_fin: string;
  estado?: EstadoProyecto;
  color?: string | null;
}

export interface TareaDistribuir {
  titulo: string;
  descripcion?: string | null;
  esfuerzo_horas?: number | null;
  prioridad?: Prioridad;
  responsable_id?: number | null;
  fecha_programada?: string | null;
}

export interface DistribuirResponse {
  aplicado: boolean;
  semanas: number;
  propuesta: (Required<Omit<TareaDistribuir, "fecha_programada">> & {
    fecha_programada: string;
    anio_iso: number;
    semana_iso: number;
  })[];
  carga_por_semana: Record<string, number>;
}

export interface Recurrente {
  id: number;
  titulo: string;
  descripcion: string | null;
  proyecto_id: number | null;
  responsable_id: number | null;
  prioridad: Prioridad;
  frecuencia: Frecuencia;
  dias_semana: number[] | null;
  dia_mes: number | null;
  fecha_inicio: string;
  fecha_fin: string | null;
  saltar_festivos: boolean;
  activa: boolean;
  generado_hasta: string | null;
}

export type RecurrenteInput = Omit<Recurrente, "id" | "generado_hasta">;

export interface Responsable {
  id: number;
  nombre: string;
  username: string;
}

export interface Resumen {
  hoy: string;
  anio_iso: number;
  semana_iso: number;
  tareas_hoy: number;
  tareas_manana: number;
  semana_total: number;
  semana_completadas: number;
  demoradas: number;
  proyectos: { id: number; nombre: string; categoria: CategoriaProyecto; avance: number; demoradas: number }[];
}

export interface FiltroTareas {
  responsable_id?: number;
  proyecto_id?: number;
}

const B = "/seguimiento";

export const seguimientoApi = {
  resumen: () => api.get<Resumen>(`${B}/resumen`),
  responsables: () => api.get<Responsable[]>(`${B}/responsables`),

  hoy: (params?: FiltroTareas) => api.get<Tarea[]>(`${B}/tareas/hoy`, { params }),
  manana: (params?: FiltroTareas) => api.get<Tarea[]>(`${B}/tareas/manana`, { params }),
  demoradas: (params?: FiltroTareas) => api.get<Tarea[]>(`${B}/tareas/demoradas`, { params }),
  crearTarea: (body: TareaInput) => api.post<Tarea>(`${B}/tareas`, body),
  actualizarTarea: (id: number, body: TareaCambios) => api.patch<Tarea>(`${B}/tareas/${id}`, body),
  completar: (id: number) => api.post<Tarea>(`${B}/tareas/${id}/completar`),
  reabrir: (id: number) => api.post<Tarea>(`${B}/tareas/${id}/reabrir`),
  eliminarTarea: (id: number) => api.delete(`${B}/tareas/${id}`),

  semanas: (anio: number, params?: FiltroTareas) => api.get<SemanasAnio>(`${B}/semanas`, { params: { anio, ...params } }),
  semana: (anio: number, semana: number, params?: FiltroTareas) =>
    api.get<SemanaDetalle>(`${B}/semanas/${anio}/${semana}`, { params }),

  proyectos: (params?: { categoria?: CategoriaProyecto; estado?: EstadoProyecto }) =>
    api.get<Proyecto[]>(`${B}/proyectos`, { params }),
  proyecto: (id: number) => api.get<ProyectoDetalle>(`${B}/proyectos/${id}`),
  crearProyecto: (body: ProyectoInput) => api.post<ProyectoDetalle>(`${B}/proyectos`, body),
  actualizarProyecto: (id: number, body: Partial<ProyectoInput>) => api.patch<ProyectoDetalle>(`${B}/proyectos/${id}`, body),
  eliminarProyecto: (id: number) => api.delete(`${B}/proyectos/${id}`),
  distribuir: (
    id: number,
    body: { tareas: TareaDistribuir[]; fecha_inicio?: string; fecha_fin?: string; secuencial: boolean; aplicar: boolean },
  ) => api.post<DistribuirResponse>(`${B}/proyectos/${id}/distribuir`, body),

  recurrentes: () => api.get<Recurrente[]>(`${B}/recurrentes`),
  crearRecurrente: (body: RecurrenteInput) => api.post<Recurrente>(`${B}/recurrentes`, body),
  actualizarRecurrente: (id: number, body: RecurrenteInput) => api.put<Recurrente>(`${B}/recurrentes/${id}`, body),
  eliminarRecurrente: (id: number) => api.delete(`${B}/recurrentes/${id}`),
};
