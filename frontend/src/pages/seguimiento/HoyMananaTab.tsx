import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { seguimientoApi, type FiltroTareas, type Tarea } from "@/api/seguimiento";
import { QK, TareaFormModal, TareaItem, fmtFecha, sumarDias } from "./comunes";

function Columna({
  titulo,
  tareas,
  cargando,
  onEditar,
  onNueva,
}: {
  titulo: string;
  tareas: Tarea[] | undefined;
  cargando: boolean;
  onEditar: (t: Tarea) => void;
  onNueva: () => void;
}) {
  const hechas = tareas?.filter((t) => t.estado === "completada").length ?? 0;
  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="font-semibold capitalize text-gray-900">{titulo}</h2>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {tareas && `${hechas}/${tareas.length} hechas`}
          <button onClick={onNueva} className="text-primary hover:text-primary-hover" title="Agregar">
            <Plus size={16} />
          </button>
        </div>
      </div>
      <div className="space-y-1.5">
        {cargando && <p className="text-sm text-gray-400">Cargando…</p>}
        {tareas?.length === 0 && <p className="text-sm text-gray-400">Sin tareas</p>}
        {tareas?.map((t) => <TareaItem key={t.id} tarea={t} onEditar={onEditar} />)}
      </div>
    </div>
  );
}

export function HoyMananaTab({ filtro }: { filtro: FiltroTareas }) {
  const [editar, setEditar] = useState<Tarea | null>(null);
  const [nuevaEn, setNuevaEn] = useState<string | null>(null);
  const hoyQ = useQuery({
    queryKey: [QK, "hoy", filtro],
    queryFn: () => seguimientoApi.hoy(filtro).then((r) => r.data),
  });
  const mananaQ = useQuery({
    queryKey: [QK, "manana", filtro],
    queryFn: () => seguimientoApi.manana(filtro).then((r) => r.data),
  });
  const resumen = useQuery({ queryKey: [QK, "resumen"], queryFn: () => seguimientoApi.resumen().then((r) => r.data) });
  const hoy = resumen.data?.hoy;
  const manana = hoy ? sumarDias(hoy, 1) : undefined;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Columna
        titulo={hoy ? `Hoy · ${fmtFecha(hoy)}` : "Hoy"}
        tareas={hoyQ.data}
        cargando={hoyQ.isLoading}
        onEditar={setEditar}
        onNueva={() => setNuevaEn(hoy ?? "")}
      />
      <Columna
        titulo={manana ? `Mañana · ${fmtFecha(manana)}` : "Mañana"}
        tareas={mananaQ.data}
        cargando={mananaQ.isLoading}
        onEditar={setEditar}
        onNueva={() => setNuevaEn(manana ?? "")}
      />
      {editar && <TareaFormModal tarea={editar} onClose={() => setEditar(null)} />}
      {nuevaEn !== null && <TareaFormModal tarea={null} fechaInicial={nuevaEn} onClose={() => setNuevaEn(null)} />}
    </div>
  );
}
