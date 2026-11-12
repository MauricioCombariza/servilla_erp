import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { seguimientoApi, type FiltroTareas, type Tarea } from "@/api/seguimiento";
import { DIAS, QK, TareaFormModal, TareaItem, btnSecundario, fmtFecha, sumarDias, useInvalidar } from "./comunes";

function semanasEnAnio(anio: number): number {
  // La semana ISO del 28 de diciembre es la última del año.
  const d = new Date(Date.UTC(anio, 11, 28));
  const dia = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dia);
  const inicio = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d.getTime() - inicio.getTime()) / 86400000 + 1) / 7);
}

export function moverSemana(anio: number, semana: number, delta: number): [number, number] {
  let s = semana + delta;
  let a = anio;
  if (s < 1) {
    a -= 1;
    s = semanasEnAnio(a);
  } else if (s > semanasEnAnio(a)) {
    a += 1;
    s = 1;
  }
  return [a, s];
}

/** Semana ISO con 7 columnas. Se puede arrastrar una tarea a otro día o mandarla a la
 *  semana siguiente. */
export function SemanaTab({
  anio,
  semana,
  filtro,
  onCambiar,
}: {
  anio: number;
  semana: number;
  filtro: FiltroTareas;
  onCambiar: (anio: number, semana: number) => void;
}) {
  const [editar, setEditar] = useState<Tarea | null>(null);
  const [nuevaEn, setNuevaEn] = useState<string | null>(null);
  const [arrastrando, setArrastrando] = useState<Tarea | null>(null);
  const invalidar = useInvalidar();
  const { data, isLoading } = useQuery({
    queryKey: [QK, "semana", anio, semana, filtro],
    queryFn: () => seguimientoApi.semana(anio, semana, filtro).then((r) => r.data),
  });
  const mover = useMutation({
    mutationFn: ({ id, fecha }: { id: number; fecha: string }) =>
      seguimientoApi.actualizarTarea(id, { fecha_programada: fecha }),
    onSuccess: invalidar,
  });

  const total = data?.dias.reduce((n, d) => n + d.tareas.length, 0) ?? 0;
  const hechas = data?.dias.reduce((n, d) => n + d.tareas.filter((t) => t.estado === "completada").length, 0) ?? 0;
  const pendientes = data?.dias.flatMap((d) => d.tareas.filter((t) => t.estado === "pendiente" || t.estado === "en_progreso")) ?? [];

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button onClick={() => onCambiar(...moverSemana(anio, semana, -1))} className={btnSecundario}>
          <ChevronLeft size={16} />
        </button>
        <div className="min-w-[14rem] text-center">
          <div className="font-semibold text-gray-900">
            Semana {semana} · {anio}
          </div>
          {data && (
            <div className="text-xs text-gray-500">
              {fmtFecha(data.lunes)} – {fmtFecha(data.domingo, true)} · {hechas}/{total} hechas
            </div>
          )}
        </div>
        <button onClick={() => onCambiar(...moverSemana(anio, semana, 1))} className={btnSecundario}>
          <ChevronRight size={16} />
        </button>
        {data && pendientes.length > 0 && (
          <button
            onClick={() => {
              if (!confirm(`¿Pasar las ${pendientes.length} tareas abiertas a la semana siguiente?`)) return;
              Promise.all(
                pendientes.map((t) =>
                  seguimientoApi.actualizarTarea(t.id, { fecha_programada: sumarDias(t.fecha_programada, 7) }),
                ),
              ).finally(invalidar);
            }}
            className={`${btnSecundario} ml-auto`}
          >
            Pasar abiertas a la próxima semana
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-gray-400">Cargando…</p>}
      {data && (
        <div className="grid grid-cols-1 gap-2 md:grid-cols-7">
          {data.dias.map((d, i) => (
            <div
              key={d.fecha}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (arrastrando && arrastrando.fecha_programada !== d.fecha) {
                  mover.mutate({ id: arrastrando.id, fecha: d.fecha });
                }
                setArrastrando(null);
              }}
              className={`min-h-[8rem] rounded-xl border p-2 ${i >= 5 ? "bg-gray-100" : "bg-gray-50"} border-gray-200`}
            >
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">
                  {DIAS[i]} {Number(d.fecha.slice(8))}
                </span>
                <button onClick={() => setNuevaEn(d.fecha)} className="text-gray-400 hover:text-primary" title="Agregar">
                  <Plus size={14} />
                </button>
              </div>
              <div className="space-y-1">
                {d.tareas.map((t) => (
                  <div key={t.id} draggable onDragStart={() => setArrastrando(t)}>
                    <TareaItem tarea={t} onEditar={setEditar} compacta />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-2 text-xs text-gray-400">Arrastra una tarea a otro día para reprogramarla.</p>

      {editar && <TareaFormModal tarea={editar} onClose={() => setEditar(null)} />}
      {nuevaEn !== null && <TareaFormModal tarea={null} fechaInicial={nuevaEn} onClose={() => setNuevaEn(null)} />}
    </div>
  );
}
