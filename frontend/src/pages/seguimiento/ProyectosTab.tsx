import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Pencil, Plus, Shuffle, Trash2 } from "lucide-react";
import {
  seguimientoApi,
  type CategoriaProyecto,
  type DistribuirResponse,
  type EstadoProyecto,
  type Proyecto,
  type ProyectoInput,
  type Tarea,
} from "@/api/seguimiento";
import {
  CATEGORIA,
  ErrorBox,
  Modal,
  PRIORIDAD,
  QK,
  TareaFormModal,
  btnPrimario,
  btnSecundario,
  errorMsg,
  fmtFecha,
  inputCls,
  useInvalidar,
  useProyectosLista,
  useResponsables,
} from "./comunes";

const ESTADO_PROYECTO: Record<EstadoProyecto, { label: string; clases: string }> = {
  planeado: { label: "Planeado", clases: "bg-gray-100 text-gray-700" },
  en_curso: { label: "En curso", clases: "bg-blue-100 text-blue-800" },
  pausado: { label: "Pausado", clases: "bg-amber-100 text-amber-800" },
  completado: { label: "Completado", clases: "bg-green-100 text-green-800" },
  cancelado: { label: "Cancelado", clases: "bg-red-100 text-red-700" },
};

function Avance({ pct }: { pct: number }) {
  return (
    <div className="h-2 overflow-hidden rounded bg-gray-200">
      <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ProyectosTab() {
  const [sel, setSel] = useState<number | null>(null);
  const [form, setForm] = useState<Proyecto | "nuevo" | null>(null);
  const [categoria, setCategoria] = useState<CategoriaProyecto | "">("");
  const { data = [], isLoading } = useProyectosLista();
  const lista = categoria ? data.filter((p) => p.categoria === categoria) : data;

  if (sel !== null) return <ProyectoDetalleView id={sel} onVolver={() => setSel(null)} onEditar={setForm} form={form} setForm={setForm} />;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={categoria} onChange={(e) => setCategoria(e.target.value as CategoriaProyecto | "")} className={`${inputCls} w-60`}>
          <option value="">Todas las categorías</option>
          {Object.entries(CATEGORIA).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button onClick={() => setForm("nuevo")} className={`${btnPrimario} ml-auto`}>
          <Plus size={16} /> Nuevo proyecto
        </button>
      </div>
      {isLoading && <p className="text-sm text-gray-400">Cargando…</p>}
      {!isLoading && lista.length === 0 && (
        <p className="rounded-xl border border-gray-200 bg-white p-6 text-center text-gray-500">
          No hay proyectos. Crea uno (p. ej. "Seguridad de la información") y reparte sus tareas por semanas.
        </p>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {lista.map((p) => (
          <button
            key={p.id}
            onClick={() => setSel(p.id)}
            className="rounded-xl border border-gray-200 bg-white p-4 text-left hover:border-primary"
            style={p.color ? { borderLeft: `4px solid ${p.color}` } : undefined}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="font-semibold text-gray-900">{p.nombre}</div>
                <div className="text-xs text-gray-500">{CATEGORIA[p.categoria]}</div>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-xs ${ESTADO_PROYECTO[p.estado].clases}`}>{ESTADO_PROYECTO[p.estado].label}</span>
            </div>
            <div className="mt-3">
              <Avance pct={p.avance} />
            </div>
            <div className="mt-1.5 flex justify-between text-xs text-gray-500">
              <span>
                {p.completadas}/{p.total_tareas} tareas · {p.avance}%
                {p.demoradas > 0 && <span className="text-red-600"> · {p.demoradas} demoradas</span>}
              </span>
              <span>
                {fmtFecha(p.fecha_inicio)} → {fmtFecha(p.fecha_fin, true)}
              </span>
            </div>
          </button>
        ))}
      </div>
      {form && <ProyectoFormModal proyecto={form === "nuevo" ? null : form} onClose={() => setForm(null)} onCreado={setSel} />}
    </div>
  );
}

function ProyectoFormModal({
  proyecto,
  onClose,
  onCreado,
}: {
  proyecto: Proyecto | null;
  onClose: () => void;
  onCreado?: (id: number) => void;
}) {
  const invalidar = useInvalidar();
  const { data: responsables = [] } = useResponsables();
  const [f, setF] = useState({
    nombre: proyecto?.nombre ?? "",
    descripcion: proyecto?.descripcion ?? "",
    categoria: proyecto?.categoria ?? ("seguridad_informacion" as CategoriaProyecto),
    estado: proyecto?.estado ?? ("planeado" as EstadoProyecto),
    responsable_id: proyecto?.responsable_id ?? "",
    fecha_inicio: proyecto?.fecha_inicio ?? "",
    fecha_fin: proyecto?.fecha_fin ?? "",
    color: proyecto?.color ?? "#1d550e",
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.value });

  const guardar = useMutation({
    mutationFn: () => {
      const body: ProyectoInput = {
        ...f,
        descripcion: f.descripcion || null,
        responsable_id: f.responsable_id === "" ? null : Number(f.responsable_id),
      };
      return proyecto ? seguimientoApi.actualizarProyecto(proyecto.id, body) : seguimientoApi.crearProyecto(body);
    },
    onSuccess: (r) => {
      invalidar();
      onClose();
      if (!proyecto) onCreado?.(r.data.id);
    },
  });

  return (
    <Modal titulo={proyecto ? "Editar proyecto" : "Nuevo proyecto"} onClose={onClose}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="sm:col-span-2 text-sm">
          Nombre
          <input value={f.nombre} onChange={set("nombre")} className={inputCls} autoFocus />
        </label>
        <label className="sm:col-span-2 text-sm">
          Descripción / objetivo
          <textarea value={f.descripcion} onChange={set("descripcion")} rows={2} className={inputCls} />
        </label>
        <label className="text-sm">
          Categoría
          <select value={f.categoria} onChange={set("categoria")} className={inputCls}>
            {Object.entries(CATEGORIA).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Estado
          <select value={f.estado} onChange={set("estado")} className={inputCls}>
            {Object.entries(ESTADO_PROYECTO).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Inicio
          <input type="date" value={f.fecha_inicio} onChange={set("fecha_inicio")} className={inputCls} />
        </label>
        <label className="text-sm">
          Fin
          <input type="date" value={f.fecha_fin} onChange={set("fecha_fin")} className={inputCls} />
        </label>
        <label className="text-sm">
          Responsable
          <select value={f.responsable_id} onChange={set("responsable_id")} className={inputCls}>
            <option value="">{proyecto ? "Sin responsable" : "Yo"}</option>
            {responsables.map((r) => (
              <option key={r.id} value={r.id}>{r.nombre}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Color
          <input type="color" value={f.color} onChange={set("color")} className="block h-9 w-16 rounded border border-gray-300" />
        </label>
      </div>
      <div className="mt-4 flex items-center justify-end gap-2">
        <ErrorBox msg={guardar.isError ? errorMsg(guardar.error, "No se pudo guardar") : ""} />
        <button onClick={onClose} className={btnSecundario}>Cancelar</button>
        <button
          onClick={() => guardar.mutate()}
          disabled={!f.nombre.trim() || !f.fecha_inicio || !f.fecha_fin || guardar.isPending}
          className={btnPrimario}
        >
          {guardar.isPending ? "Guardando…" : "Guardar"}
        </button>
      </div>
    </Modal>
  );
}

function ProyectoDetalleView({
  id,
  onVolver,
  onEditar,
  form,
  setForm,
}: {
  id: number;
  onVolver: () => void;
  onEditar: (p: Proyecto) => void;
  form: Proyecto | "nuevo" | null;
  setForm: (f: Proyecto | "nuevo" | null) => void;
}) {
  const invalidar = useInvalidar();
  const [editarTarea, setEditarTarea] = useState<Tarea | null>(null);
  const [nuevaTarea, setNuevaTarea] = useState(false);
  const [distribuir, setDistribuir] = useState(false);
  const { data: p, isLoading } = useQuery({
    queryKey: [QK, "proyecto", id],
    queryFn: () => seguimientoApi.proyecto(id).then((r) => r.data),
  });
  const mover = useMutation({
    mutationFn: ({ tid, fecha }: { tid: number; fecha: string }) => seguimientoApi.actualizarTarea(tid, { fecha_programada: fecha }),
    onSuccess: invalidar,
  });
  const borrar = useMutation({
    mutationFn: () => seguimientoApi.eliminarProyecto(id),
    onSuccess: () => {
      invalidar();
      onVolver();
    },
  });

  if (isLoading || !p) return <p className="text-sm text-gray-400">Cargando…</p>;
  const maxSemana = Math.max(1, ...p.semanas.map((s) => s.total));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={onVolver} className={btnSecundario}>
          <ArrowLeft size={16} /> Proyectos
        </button>
        <div className="ml-auto flex gap-2">
          <button onClick={() => setNuevaTarea(true)} className={btnSecundario}>
            <Plus size={16} /> Tarea
          </button>
          <button onClick={() => setDistribuir(true)} className={btnPrimario}>
            <Shuffle size={16} /> Distribuir tareas por semanas
          </button>
          <button onClick={() => onEditar(p)} className={btnSecundario} title="Editar proyecto">
            <Pencil size={16} />
          </button>
          <button
            onClick={() => confirm(`¿Eliminar el proyecto "${p.nombre}" con todas sus tareas?`) && borrar.mutate()}
            className={btnSecundario}
            title="Eliminar proyecto"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4" style={p.color ? { borderLeft: `4px solid ${p.color}` } : undefined}>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{p.nombre}</h2>
            <div className="text-sm text-gray-500">
              {CATEGORIA[p.categoria]} · {fmtFecha(p.fecha_inicio, true)} → {fmtFecha(p.fecha_fin, true)}
              {p.responsable_nombre && ` · ${p.responsable_nombre}`}
            </div>
            {p.descripcion && <p className="mt-1 text-sm text-gray-700">{p.descripcion}</p>}
          </div>
          <span className={`rounded px-1.5 py-0.5 text-xs ${ESTADO_PROYECTO[p.estado].clases}`}>{ESTADO_PROYECTO[p.estado].label}</span>
        </div>
        <div className="mt-3">
          <Avance pct={p.avance} />
          <div className="mt-1 text-xs text-gray-500">
            {p.completadas}/{p.total_tareas} tareas · {p.avance}%
            {p.demoradas > 0 && <span className="text-red-600"> · {p.demoradas} demoradas</span>}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold text-gray-900">Plan semana a semana</h3>
        <div className="flex items-end gap-1 overflow-x-auto pb-1">
          {p.semanas.map((s) => (
            <div key={`${s.anio}-${s.semana}`} className="flex w-9 flex-shrink-0 flex-col items-center" title={`Semana ${s.semana} (${fmtFecha(s.lunes, true)}): ${s.completadas}/${s.total}`}>
              <div className="flex h-20 w-6 flex-col-reverse overflow-hidden rounded bg-gray-100">
                <div className="bg-primary" style={{ height: `${(s.completadas / maxSemana) * 100}%` }} />
                <div className="bg-red-300" style={{ height: `${(s.demoradas / maxSemana) * 100}%` }} />
                <div className="bg-blue-200" style={{ height: `${((s.total - s.completadas - s.demoradas) / maxSemana) * 100}%` }} />
              </div>
              <span className="mt-0.5 text-[10px] text-gray-500">S{s.semana}</span>
              <span className="text-[10px] text-gray-700">{s.total || ""}</span>
            </div>
          ))}
        </div>
        <div className="mt-1 flex gap-3 text-[11px] text-gray-500">
          <span><span className="mr-1 inline-block h-2 w-2 bg-primary" />hechas</span>
          <span><span className="mr-1 inline-block h-2 w-2 bg-red-300" />demoradas</span>
          <span><span className="mr-1 inline-block h-2 w-2 bg-blue-200" />por hacer</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2">Semana</th>
              <th className="px-3 py-2">Fecha</th>
              <th className="px-3 py-2">Tarea</th>
              <th className="px-3 py-2">Responsable</th>
              <th className="px-3 py-2">Horas</th>
              <th className="px-3 py-2">Prioridad</th>
              <th className="px-3 py-2">Estado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {p.tareas.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-gray-400">
                  Sin tareas. Usa "Distribuir tareas por semanas" para cargar el plan.
                </td>
              </tr>
            )}
            {p.tareas.map((t) => (
              <tr key={t.id} className={t.demorada ? "bg-red-50" : ""}>
                <td className="px-3 py-1.5 font-medium text-gray-700">S{t.semana_iso}</td>
                <td className="px-3 py-1.5">
                  <input
                    type="date"
                    value={t.fecha_programada}
                    onChange={(e) => e.target.value && mover.mutate({ tid: t.id, fecha: e.target.value })}
                    className="rounded border border-gray-200 px-1 py-0.5 text-xs"
                  />
                </td>
                <td className="px-3 py-1.5">
                  <button onClick={() => setEditarTarea(t)} className={`text-left hover:text-primary ${t.estado === "completada" ? "text-gray-400 line-through" : "text-gray-900"}`}>
                    {t.titulo}
                  </button>
                </td>
                <td className="px-3 py-1.5 text-gray-600">{t.responsable_nombre ?? "—"}</td>
                <td className="px-3 py-1.5 text-gray-600">{t.esfuerzo_horas ? Number(t.esfuerzo_horas) : "—"}</td>
                <td className="px-3 py-1.5">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${PRIORIDAD[t.prioridad].clases}`}>{PRIORIDAD[t.prioridad].label}</span>
                </td>
                <td className="px-3 py-1.5 text-gray-600">
                  {t.demorada ? <span className="text-red-600">demorada ({t.dias_atraso} d)</span> : t.estado.replace("_", " ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editarTarea && <TareaFormModal tarea={editarTarea} onClose={() => setEditarTarea(null)} />}
      {nuevaTarea && <TareaFormModal tarea={null} fechaInicial={p.fecha_inicio} proyectoInicial={p.id} onClose={() => setNuevaTarea(false)} />}
      {distribuir && <DistribuirModal proyecto={p} onClose={() => setDistribuir(false)} />}
      {form && form !== "nuevo" && <ProyectoFormModal proyecto={form} onClose={() => setForm(null)} />}
    </div>
  );
}

/** "Título | horas | prioridad" por línea → propuesta automática → ajuste manual → guardar. */
function DistribuirModal({ proyecto, onClose }: { proyecto: Proyecto; onClose: () => void }) {
  const invalidar = useInvalidar();
  const [texto, setTexto] = useState("");
  const [desde, setDesde] = useState(proyecto.fecha_inicio);
  const [hasta, setHasta] = useState(proyecto.fecha_fin);
  const [secuencial, setSecuencial] = useState(false);
  const [propuesta, setPropuesta] = useState<DistribuirResponse | null>(null);

  const tareas = texto
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [titulo, horas, prio] = l.split("|").map((x) => x.trim());
      const p = (prio ?? "").toLowerCase();
      return {
        titulo,
        esfuerzo_horas: horas && !isNaN(Number(horas)) ? Number(horas) : null,
        prioridad: (["baja", "media", "alta", "critica"].includes(p) ? p : "media") as "baja" | "media" | "alta" | "critica",
      };
    })
    .filter((t) => t.titulo);

  const previsualizar = useMutation({
    mutationFn: () =>
      seguimientoApi.distribuir(proyecto.id, { tareas, fecha_inicio: desde, fecha_fin: hasta, secuencial, aplicar: false }),
    onSuccess: (r) => setPropuesta(r.data),
  });
  const aplicar = useMutation({
    mutationFn: () =>
      seguimientoApi.distribuir(proyecto.id, {
        tareas: propuesta!.propuesta.map((t) => ({ ...t, esfuerzo_horas: t.esfuerzo_horas ? Number(t.esfuerzo_horas) : null })),
        fecha_inicio: desde,
        fecha_fin: hasta,
        secuencial,
        aplicar: true,
      }),
    onSuccess: () => {
      invalidar();
      onClose();
    },
  });

  function cambiarFecha(i: number, fecha: string) {
    if (!propuesta || !fecha) return;
    const lista = propuesta.propuesta.map((t, j) => (j === i ? { ...t, fecha_programada: fecha } : t));
    setPropuesta({ ...propuesta, propuesta: lista });
  }

  const error = previsualizar.isError
    ? errorMsg(previsualizar.error, "No se pudo calcular")
    : aplicar.isError
      ? errorMsg(aplicar.error, "No se pudo guardar")
      : "";

  return (
    <Modal titulo={`Distribuir tareas · ${proyecto.nombre}`} onClose={onClose}>
      {!propuesta ? (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            Una tarea por línea: <code className="rounded bg-gray-100 px-1">Título | horas | prioridad</code> (horas y
            prioridad opcionales). El sistema propone una semana para cada una y luego puedes ajustarla.
          </p>
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={10}
            placeholder={"Inventario de activos de información | 8 | alta\nPolítica de contraseñas | 4\nCopias de seguridad: prueba de restauración | 6 | critica\nCapacitación al personal | 3"}
            className={`${inputCls} font-mono`}
          />
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              Desde
              <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} className={inputCls} />
            </label>
            <label className="text-sm">
              Hasta
              <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} className={inputCls} />
            </label>
          </div>
          <label className="flex items-start gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={secuencial} onChange={(e) => setSecuencial(e.target.checked)} className="mt-0.5 accent-primary" />
            <span>
              <b>Respetar el orden</b> (las primeras tareas en las primeras semanas). Si no, se balancea la carga de horas entre semanas.
            </span>
          </label>
          <div className="flex items-center justify-end gap-2">
            <ErrorBox msg={error} />
            <button onClick={onClose} className={btnSecundario}>Cancelar</button>
            <button onClick={() => previsualizar.mutate()} disabled={!tareas.length || previsualizar.isPending} className={btnPrimario}>
              {previsualizar.isPending ? "Calculando…" : `Proponer reparto (${tareas.length})`}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-1">
            {Object.entries(propuesta.carga_por_semana).map(([sem, carga]) => (
              <span key={sem} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                {sem.split("-")[1]}: {carga}
              </span>
            ))}
          </div>
          <div className="max-h-80 overflow-y-auto rounded border border-gray-200">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-gray-50 text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-2 py-1.5">Sem.</th>
                  <th className="px-2 py-1.5">Fecha</th>
                  <th className="px-2 py-1.5">Tarea</th>
                  <th className="px-2 py-1.5">Horas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {propuesta.propuesta.map((t, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1 text-gray-600">S{t.semana_iso}</td>
                    <td className="px-2 py-1">
                      <input type="date" value={t.fecha_programada} onChange={(e) => cambiarFecha(i, e.target.value)} className="rounded border border-gray-200 px-1 py-0.5 text-xs" />
                    </td>
                    <td className="px-2 py-1">{t.titulo}</td>
                    <td className="px-2 py-1 text-gray-600">{t.esfuerzo_horas ? Number(t.esfuerzo_horas) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-end gap-2">
            <ErrorBox msg={error} />
            <button onClick={() => setPropuesta(null)} className={btnSecundario}>Volver</button>
            <button onClick={() => aplicar.mutate()} disabled={aplicar.isPending} className={btnPrimario}>
              {aplicar.isPending ? "Guardando…" : `Guardar ${propuesta.propuesta.length} tareas`}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
