import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { seguimientoApi, type Frecuencia, type Prioridad, type Recurrente, type RecurrenteInput } from "@/api/seguimiento";
import {
  DIAS,
  ErrorBox,
  Modal,
  PRIORIDAD,
  QK,
  btnPrimario,
  btnSecundario,
  errorMsg,
  fmtFecha,
  inputCls,
  useInvalidar,
  useProyectosLista,
  useResponsables,
} from "./comunes";

function describir(r: Recurrente): string {
  if (r.frecuencia === "diaria") return r.dias_semana?.length ? `Diaria (${r.dias_semana.map((d) => DIAS[d - 1]).join(", ")})` : "Diaria";
  if (r.frecuencia === "semanal") return `Cada ${(r.dias_semana ?? []).map((d) => DIAS[d - 1]).join(", ")}`;
  return `Mensual, día ${r.dia_mes}`;
}

/** Plantillas que generan tareas automáticamente (diaria, semanal o mensual). */
export function RecurrentesTab() {
  const [form, setForm] = useState<Recurrente | "nueva" | null>(null);
  const invalidar = useInvalidar();
  const { data = [], isLoading } = useQuery({
    queryKey: [QK, "recurrentes"],
    queryFn: () => seguimientoApi.recurrentes().then((r) => r.data),
  });
  const { data: responsables = [] } = useResponsables();
  const { data: proyectos = [] } = useProyectosLista();
  const borrar = useMutation({ mutationFn: (id: number) => seguimientoApi.eliminarRecurrente(id), onSuccess: invalidar });
  const nombre = (id: number | null) => responsables.find((r) => r.id === id)?.nombre ?? "—";

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-sm text-gray-500">
          Cada plantilla crea sus tareas en el calendario (p. ej. revisar copias de seguridad cada lunes). Al editarla se
          rehacen solo las tareas futuras aún pendientes.
        </p>
        <button onClick={() => setForm("nueva")} className={`${btnPrimario} flex-shrink-0`}>
          <Plus size={16} /> Nueva recurrente
        </button>
      </div>
      {isLoading && <p className="text-sm text-gray-400">Cargando…</p>}
      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2">Tarea</th>
              <th className="px-3 py-2">Frecuencia</th>
              <th className="px-3 py-2">Responsable</th>
              <th className="px-3 py-2">Proyecto</th>
              <th className="px-3 py-2">Vigencia</th>
              <th className="px-3 py-2">Prioridad</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {!isLoading && data.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-gray-400">Sin tareas recurrentes</td>
              </tr>
            )}
            {data.map((r) => (
              <tr key={r.id} className={r.activa ? "" : "text-gray-400"}>
                <td className="px-3 py-2">
                  {r.titulo}
                  {!r.activa && <span className="ml-1 text-xs">(inactiva)</span>}
                </td>
                <td className="px-3 py-2">{describir(r)}{r.saltar_festivos && <span className="text-xs text-gray-400"> · sin festivos</span>}</td>
                <td className="px-3 py-2">{nombre(r.responsable_id)}</td>
                <td className="px-3 py-2">{proyectos.find((p) => p.id === r.proyecto_id)?.nombre ?? "—"}</td>
                <td className="px-3 py-2">
                  {fmtFecha(r.fecha_inicio, true)} → {r.fecha_fin ? fmtFecha(r.fecha_fin, true) : "sin fin"}
                </td>
                <td className="px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${PRIORIDAD[r.prioridad].clases}`}>{PRIORIDAD[r.prioridad].label}</span>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right">
                  <button onClick={() => setForm(r)} className="mr-2 text-gray-500 hover:text-primary" title="Editar">
                    <Pencil size={15} />
                  </button>
                  <button
                    onClick={() => confirm(`¿Eliminar "${r.titulo}"? Se borran sus tareas futuras pendientes.`) && borrar.mutate(r.id)}
                    className="text-gray-500 hover:text-red-600"
                    title="Eliminar"
                  >
                    <Trash2 size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {form && <RecurrenteFormModal rec={form === "nueva" ? null : form} onClose={() => setForm(null)} />}
    </div>
  );
}

function RecurrenteFormModal({ rec, onClose }: { rec: Recurrente | null; onClose: () => void }) {
  const invalidar = useInvalidar();
  const { data: responsables = [] } = useResponsables();
  const { data: proyectos = [] } = useProyectosLista();
  const { data: res } = useQuery({ queryKey: [QK, "resumen"], queryFn: () => seguimientoApi.resumen().then((r) => r.data) });
  const [f, setF] = useState({
    titulo: rec?.titulo ?? "",
    descripcion: rec?.descripcion ?? "",
    frecuencia: rec?.frecuencia ?? ("semanal" as Frecuencia),
    dias_semana: rec?.dias_semana ?? [1],
    dia_mes: rec?.dia_mes ?? 1,
    fecha_inicio: rec?.fecha_inicio ?? res?.hoy ?? "",
    fecha_fin: rec?.fecha_fin ?? "",
    prioridad: rec?.prioridad ?? ("media" as Prioridad),
    responsable_id: rec?.responsable_id ?? "",
    proyecto_id: rec?.proyecto_id ?? "",
    saltar_festivos: rec?.saltar_festivos ?? true,
    activa: rec?.activa ?? true,
  });

  const toggleDia = (d: number) =>
    setF({ ...f, dias_semana: f.dias_semana.includes(d) ? f.dias_semana.filter((x) => x !== d) : [...f.dias_semana, d].sort() });

  const guardar = useMutation({
    mutationFn: () => {
      const body: RecurrenteInput = {
        titulo: f.titulo.trim(),
        descripcion: f.descripcion || null,
        frecuencia: f.frecuencia,
        dias_semana: f.frecuencia === "mensual" ? null : f.frecuencia === "diaria" && f.dias_semana.length === 7 ? null : f.dias_semana,
        dia_mes: f.frecuencia === "mensual" ? Number(f.dia_mes) : null,
        fecha_inicio: f.fecha_inicio,
        fecha_fin: f.fecha_fin || null,
        prioridad: f.prioridad,
        responsable_id: f.responsable_id === "" ? null : Number(f.responsable_id),
        proyecto_id: f.proyecto_id === "" ? null : Number(f.proyecto_id),
        saltar_festivos: f.saltar_festivos,
        activa: f.activa,
      };
      return rec ? seguimientoApi.actualizarRecurrente(rec.id, body) : seguimientoApi.crearRecurrente(body);
    },
    onSuccess: () => {
      invalidar();
      onClose();
    },
  });

  const valido = f.titulo.trim() && f.fecha_inicio && (f.frecuencia === "mensual" || f.dias_semana.length > 0);

  return (
    <Modal titulo={rec ? "Editar tarea recurrente" : "Nueva tarea recurrente"} onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm">
          Título
          <input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} className={inputCls} autoFocus />
        </label>
        <label className="sm:col-span-2 text-sm">
          Descripción
          <textarea value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} rows={2} className={inputCls} />
        </label>
        <label className="text-sm">
          Frecuencia
          <select
            value={f.frecuencia}
            onChange={(e) => {
              const frecuencia = e.target.value as Frecuencia;
              setF({ ...f, frecuencia, dias_semana: frecuencia === "diaria" ? [1, 2, 3, 4, 5, 6, 7] : f.dias_semana.length ? f.dias_semana : [1] });
            }}
            className={inputCls}
          >
            <option value="diaria">Diaria</option>
            <option value="semanal">Semanal</option>
            <option value="mensual">Mensual</option>
          </select>
        </label>
        {f.frecuencia === "mensual" ? (
          <label className="text-sm">
            Día del mes
            <input type="number" min={1} max={31} value={f.dia_mes} onChange={(e) => setF({ ...f, dia_mes: Number(e.target.value) })} className={inputCls} />
          </label>
        ) : (
          <div className="text-sm">
            Días
            <div className="mt-1 flex flex-wrap gap-1">
              {DIAS.map((d, i) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDia(i + 1)}
                  className={`rounded px-2 py-1 text-xs ${f.dias_semana.includes(i + 1) ? "bg-primary text-white" : "bg-gray-100 text-gray-600"}`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
        )}
        <label className="text-sm">
          Desde
          <input type="date" value={f.fecha_inicio} onChange={(e) => setF({ ...f, fecha_inicio: e.target.value })} className={inputCls} />
        </label>
        <label className="text-sm">
          Hasta (opcional)
          <input type="date" value={f.fecha_fin} onChange={(e) => setF({ ...f, fecha_fin: e.target.value })} className={inputCls} />
        </label>
        <label className="text-sm">
          Responsable
          <select value={f.responsable_id} onChange={(e) => setF({ ...f, responsable_id: e.target.value })} className={inputCls}>
            <option value="">{rec ? "(sin cambio)" : "Yo"}</option>
            {responsables.map((r) => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Proyecto
          <select value={f.proyecto_id} onChange={(e) => setF({ ...f, proyecto_id: e.target.value })} className={inputCls}>
            <option value="">Sin proyecto</option>
            {proyectos.map((p) => (
              <option key={p.id} value={p.id}>{p.nombre}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Prioridad
          <select value={f.prioridad} onChange={(e) => setF({ ...f, prioridad: e.target.value as Prioridad })} className={inputCls}>
            {Object.entries(PRIORIDAD).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </label>
        <div className="flex flex-col justify-end gap-1 text-sm text-gray-700">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={f.saltar_festivos} onChange={(e) => setF({ ...f, saltar_festivos: e.target.checked })} className="accent-primary" />
            Saltar domingos y festivos
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={f.activa} onChange={(e) => setF({ ...f, activa: e.target.checked })} className="accent-primary" />
            Activa
          </label>
        </div>
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
