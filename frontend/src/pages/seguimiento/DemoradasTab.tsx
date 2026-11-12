import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarClock, Check } from "lucide-react";
import { seguimientoApi, type FiltroTareas, type Tarea } from "@/api/seguimiento";
import { PRIORIDAD, QK, TareaFormModal, fmtFecha, useInvalidar } from "./comunes";

/** Tareas abiertas cuya fecha límite (o programada) ya pasó, de la más atrasada a la menos. */
export function DemoradasTab({ filtro }: { filtro: FiltroTareas }) {
  const [editar, setEditar] = useState<Tarea | null>(null);
  const invalidar = useInvalidar();
  const { data, isLoading } = useQuery({
    queryKey: [QK, "demoradas", filtro],
    queryFn: () => seguimientoApi.demoradas(filtro).then((r) => r.data),
  });
  const { data: res } = useQuery({ queryKey: [QK, "resumen"], queryFn: () => seguimientoApi.resumen().then((r) => r.data) });
  const completar = useMutation({ mutationFn: (id: number) => seguimientoApi.completar(id), onSuccess: invalidar });
  const aHoy = useMutation({
    mutationFn: (t: Tarea) =>
      seguimientoApi.actualizarTarea(t.id, {
        fecha_programada: res!.hoy,
        ...(t.fecha_limite && t.fecha_limite < res!.hoy ? { fecha_limite: res!.hoy } : {}),
      }),
    onSuccess: invalidar,
  });

  if (isLoading) return <p className="text-sm text-gray-400">Cargando…</p>;
  if (!data?.length) return <p className="rounded-xl border border-gray-200 bg-white p-6 text-center text-gray-500">No hay tareas demoradas 🎉</p>;

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
          <tr>
            <th className="px-3 py-2">Atraso</th>
            <th className="px-3 py-2">Tarea</th>
            <th className="px-3 py-2">Proyecto</th>
            <th className="px-3 py-2">Responsable</th>
            <th className="px-3 py-2">Programada</th>
            <th className="px-3 py-2">Límite</th>
            <th className="px-3 py-2">Prioridad</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.map((t) => (
            <tr key={t.id} className="hover:bg-gray-50">
              <td className="px-3 py-2 font-semibold text-red-600">{t.dias_atraso} d</td>
              <td className="px-3 py-2">
                <button onClick={() => setEditar(t)} className="text-left text-gray-900 hover:text-primary">
                  {t.titulo}
                </button>
              </td>
              <td className="px-3 py-2 text-gray-600">{t.proyecto_nombre ?? "—"}</td>
              <td className="px-3 py-2 text-gray-600">{t.responsable_nombre ?? "—"}</td>
              <td className="px-3 py-2 text-gray-600">{fmtFecha(t.fecha_programada)}</td>
              <td className="px-3 py-2 text-gray-600">{t.fecha_limite ? fmtFecha(t.fecha_limite) : "—"}</td>
              <td className="px-3 py-2">
                <span className={`rounded px-1.5 py-0.5 text-xs ${PRIORIDAD[t.prioridad].clases}`}>{PRIORIDAD[t.prioridad].label}</span>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right">
                <button
                  onClick={() => aHoy.mutate(t)}
                  disabled={!res}
                  className="mr-2 text-gray-500 hover:text-primary"
                  title="Reprogramar para hoy"
                >
                  <CalendarClock size={16} />
                </button>
                <button onClick={() => completar.mutate(t.id)} className="text-gray-500 hover:text-green-600" title="Completar">
                  <Check size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {editar && <TareaFormModal tarea={editar} onClose={() => setEditar(null)} />}
    </div>
  );
}
