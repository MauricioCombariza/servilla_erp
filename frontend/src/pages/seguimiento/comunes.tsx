import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Pencil, Repeat, Trash2, X } from "lucide-react";
import {
  seguimientoApi,
  type CategoriaProyecto,
  type Prioridad,
  type Tarea,
  type TareaInput,
} from "@/api/seguimiento";

export const QK = "seguimiento";

export const PRIORIDAD: Record<Prioridad, { label: string; clases: string }> = {
  critica: { label: "Crítica", clases: "bg-red-100 text-red-800" },
  alta: { label: "Alta", clases: "bg-orange-100 text-orange-800" },
  media: { label: "Media", clases: "bg-blue-100 text-blue-800" },
  baja: { label: "Baja", clases: "bg-gray-100 text-gray-600" },
};

export const CATEGORIA: Record<CategoriaProyecto, string> = {
  seguridad_informacion: "Seguridad de la información",
  nuevo_proyecto: "Nuevo proyecto",
  operativo: "Operativo",
  otro: "Otro",
};

export const DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

export function errorMsg(e: unknown, def = "Error"): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg ?? "").join("; ");
  return def;
}

/** "2026-11-12" → "jue 12 nov" (sin desfase de zona horaria). */
export function fmtFecha(iso: string, conAnio = false): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("es-CO", {
    weekday: "short",
    day: "numeric",
    month: "short",
    ...(conAnio ? { year: "numeric" } : {}),
  });
}

export function sumarDias(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  const f = new Date(Date.UTC(y, m - 1, d + n));
  return f.toISOString().slice(0, 10);
}

export function useInvalidar() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: [QK] });
}

export function useResponsables() {
  return useQuery({
    queryKey: [QK, "responsables"],
    queryFn: () => seguimientoApi.responsables().then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

export function useProyectosLista() {
  return useQuery({
    queryKey: [QK, "proyectos"],
    queryFn: () => seguimientoApi.proyectos().then((r) => r.data),
  });
}

export const inputCls = "w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm";
export const btnPrimario =
  "flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50";
export const btnSecundario =
  "flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50";

export function ErrorBox({ msg }: { msg: string }) {
  if (!msg) return null;
  return (
    <div className="flex items-center gap-1.5 text-sm text-red-600">
      <AlertCircle size={16} /> {msg}
    </div>
  );
}

/** Fila de tarea con check para completar, badges y acciones. */
export function TareaItem({
  tarea,
  onEditar,
  compacta = false,
}: {
  tarea: Tarea;
  onEditar: (t: Tarea) => void;
  compacta?: boolean;
}) {
  const invalidar = useInvalidar();
  const toggle = useMutation({
    mutationFn: () =>
      tarea.estado === "completada" ? seguimientoApi.reabrir(tarea.id) : seguimientoApi.completar(tarea.id),
    onSuccess: invalidar,
  });
  const borrar = useMutation({ mutationFn: () => seguimientoApi.eliminarTarea(tarea.id), onSuccess: invalidar });
  const hecha = tarea.estado === "completada";

  return (
    <div
      className={`group flex items-start gap-2 rounded-lg border px-2 py-1.5 text-sm ${
        tarea.demorada ? "border-red-200 bg-red-50" : "border-gray-200 bg-white"
      }`}
    >
      <input
        type="checkbox"
        checked={hecha}
        disabled={toggle.isPending}
        onChange={() => toggle.mutate()}
        className="mt-0.5 h-4 w-4 accent-primary"
        title={hecha ? "Reabrir" : "Marcar como completada"}
      />
      <div className="min-w-0 flex-1">
        <div className={`break-words ${hecha ? "text-gray-400 line-through" : "text-gray-900"}`}>
          {tarea.recurrente_id && <Repeat size={12} className="mr-1 inline text-gray-400" />}
          {tarea.titulo}
        </div>
        {!compacta && (
          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-gray-500">
            <span className={`rounded px-1.5 py-0.5 ${PRIORIDAD[tarea.prioridad].clases}`}>
              {PRIORIDAD[tarea.prioridad].label}
            </span>
            {tarea.proyecto_nombre && <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-800">{tarea.proyecto_nombre}</span>}
            {tarea.responsable_nombre && <span>· {tarea.responsable_nombre}</span>}
            {tarea.fecha_limite && <span>· límite {fmtFecha(tarea.fecha_limite)}</span>}
            {tarea.demorada && <span className="font-medium text-red-700">· {tarea.dias_atraso} d de atraso</span>}
            {tarea.estado === "en_progreso" && <span className="text-amber-700">· en progreso</span>}
          </div>
        )}
      </div>
      <div className="flex gap-1 opacity-60 group-hover:opacity-100">
        <button onClick={() => onEditar(tarea)} className="text-gray-500 hover:text-primary" title="Editar">
          <Pencil size={14} />
        </button>
        <button
          onClick={() => confirm(`¿Eliminar "${tarea.titulo}"?`) && borrar.mutate()}
          className="text-gray-500 hover:text-red-600"
          title="Eliminar"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}

export function Modal({ titulo, onClose, children }: { titulo: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">{titulo}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Crear (tarea = null) o editar una tarea. */
export function TareaFormModal({
  tarea,
  fechaInicial,
  proyectoInicial,
  onClose,
}: {
  tarea: Tarea | null;
  fechaInicial?: string;
  proyectoInicial?: number;
  onClose: () => void;
}) {
  const invalidar = useInvalidar();
  const { data: responsables = [] } = useResponsables();
  const { data: proyectos = [] } = useProyectosLista();
  const [f, setF] = useState({
    titulo: tarea?.titulo ?? "",
    descripcion: tarea?.descripcion ?? "",
    fecha_programada: tarea?.fecha_programada ?? fechaInicial ?? "",
    fecha_limite: tarea?.fecha_limite ?? "",
    prioridad: (tarea?.prioridad ?? "media") as Prioridad,
    estado: tarea?.estado ?? "pendiente",
    proyecto_id: tarea?.proyecto_id ?? proyectoInicial ?? "",
    responsable_id: tarea?.responsable_id ?? "",
    esfuerzo_horas: tarea?.esfuerzo_horas ?? "",
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.value });

  const guardar = useMutation({
    mutationFn: () => {
      const body: TareaInput = {
        titulo: f.titulo.trim(),
        descripcion: f.descripcion || null,
        fecha_programada: f.fecha_programada,
        fecha_limite: f.fecha_limite || null,
        prioridad: f.prioridad,
        proyecto_id: f.proyecto_id === "" ? null : Number(f.proyecto_id),
        responsable_id: f.responsable_id === "" ? null : Number(f.responsable_id),
        esfuerzo_horas: f.esfuerzo_horas === "" ? null : Number(f.esfuerzo_horas),
      };
      return tarea
        ? seguimientoApi.actualizarTarea(tarea.id, { ...body, estado: f.estado })
        : seguimientoApi.crearTarea(body);
    },
    onSuccess: () => {
      invalidar();
      onClose();
    },
  });

  const valido = f.titulo.trim() && f.fecha_programada;

  return (
    <Modal titulo={tarea ? "Editar tarea" : "Nueva tarea"} onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm">
          Título
          <input value={f.titulo} onChange={set("titulo")} className={inputCls} autoFocus />
        </label>
        <label className="sm:col-span-2 text-sm">
          Descripción
          <textarea value={f.descripcion} onChange={set("descripcion")} rows={2} className={inputCls} />
        </label>
        <label className="text-sm">
          Fecha programada
          <input type="date" value={f.fecha_programada} onChange={set("fecha_programada")} className={inputCls} />
        </label>
        <label className="text-sm">
          Fecha límite (opcional)
          <input type="date" value={f.fecha_limite} onChange={set("fecha_limite")} className={inputCls} />
        </label>
        <label className="text-sm">
          Prioridad
          <select value={f.prioridad} onChange={set("prioridad")} className={inputCls}>
            {Object.entries(PRIORIDAD).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </label>
        {tarea && (
          <label className="text-sm">
            Estado
            <select value={f.estado} onChange={set("estado")} className={inputCls}>
              <option value="pendiente">Pendiente</option>
              <option value="en_progreso">En progreso</option>
              <option value="completada">Completada</option>
              <option value="cancelada">Cancelada</option>
            </select>
          </label>
        )}
        <label className="text-sm">
          Responsable
          <select value={f.responsable_id} onChange={set("responsable_id")} className={inputCls}>
            <option value="">{tarea ? "Sin responsable" : "Yo"}</option>
            {responsables.map((r) => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Proyecto
          <select value={f.proyecto_id} onChange={set("proyecto_id")} className={inputCls}>
            <option value="">Sin proyecto</option>
            {proyectos.map((p) => (
              <option key={p.id} value={p.id}>{p.nombre}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Esfuerzo (horas)
          <input type="number" min={0} step={0.5} value={f.esfuerzo_horas} onChange={set("esfuerzo_horas")} className={inputCls} />
        </label>
      </div>
      <div className="mt-4 flex items-center justify-end gap-2">
        <ErrorBox msg={guardar.isError ? errorMsg(guardar.error, "No se pudo guardar") : ""} />
        <button onClick={onClose} className={btnSecundario}>Cancelar</button>
        <button onClick={() => guardar.mutate()} disabled={!valido || guardar.isPending} className={btnPrimario}>
          {guardar.isPending ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </Modal>
  );
}
