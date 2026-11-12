import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { seguimientoApi, type FiltroTareas } from "@/api/seguimiento";
import { QK, btnSecundario, fmtFecha } from "./comunes";

/** Las 52/53 semanas ISO del año con su avance; click en una abre la vista semanal. */
export function AnioTab({
  anioInicial,
  filtro,
  onSemana,
}: {
  anioInicial: number;
  filtro: FiltroTareas;
  onSemana: (anio: number, semana: number) => void;
}) {
  const [anio, setAnio] = useState(anioInicial);
  const { data, isLoading } = useQuery({
    queryKey: [QK, "anio", anio, filtro],
    queryFn: () => seguimientoApi.semanas(anio, filtro).then((r) => r.data),
  });

  const totales = data?.semanas.reduce(
    (acc, s) => ({ total: acc.total + s.total, hechas: acc.hechas + s.completadas, demoradas: acc.demoradas + s.demoradas }),
    { total: 0, hechas: 0, demoradas: 0 },
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button onClick={() => setAnio(anio - 1)} className={btnSecundario}>
          <ChevronLeft size={16} />
        </button>
        <span className="w-16 text-center font-semibold text-gray-900">{anio}</span>
        <button onClick={() => setAnio(anio + 1)} className={btnSecundario}>
          <ChevronRight size={16} />
        </button>
        {totales && (
          <span className="text-sm text-gray-500">
            {data!.semanas.length} semanas · {totales.hechas}/{totales.total} tareas hechas
            {totales.demoradas > 0 && <span className="text-red-600"> · {totales.demoradas} demoradas</span>}
          </span>
        )}
      </div>
      {isLoading && <p className="text-sm text-gray-400">Cargando…</p>}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
        {data?.semanas.map((s) => {
          const pct = s.total ? Math.round((s.completadas * 100) / s.total) : 0;
          return (
            <button
              key={s.semana}
              onClick={() => onSemana(s.anio, s.semana)}
              className={`rounded-lg border p-2 text-left text-xs hover:border-primary ${
                s.es_actual ? "border-primary ring-1 ring-primary" : "border-gray-200"
              } ${s.demoradas ? "bg-red-50" : "bg-white"}`}
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-gray-900">S{s.semana}</span>
                <span className="text-gray-500">{fmtFecha(s.lunes).replace(/^\S+\s/, "")}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded bg-gray-200">
                <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <div className="mt-1 text-gray-600">
                {s.total ? `${s.completadas}/${s.total}` : "—"}
                {s.demoradas > 0 && <span className="ml-1 text-red-600">· {s.demoradas} dem.</span>}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
