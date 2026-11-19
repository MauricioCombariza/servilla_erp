import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { seguimientoApi, type FiltroTareas } from "@/api/seguimiento";
import { useAuthStore } from "@/store/authStore";
import { QK, TareaFormModal, btnPrimario, inputCls, useResponsables } from "./comunes";
import { HoyMananaTab } from "./HoyMananaTab";
import { SemanaTab } from "./SemanaTab";
import { AnioTab } from "./AnioTab";
import { DemoradasTab } from "./DemoradasTab";
import { ProyectosTab } from "./ProyectosTab";
import { RecurrentesTab } from "./RecurrentesTab";

type Tab = "hoy" | "semana" | "anio" | "demoradas" | "proyectos" | "recurrentes";

const TABS: { key: Tab; label: string }[] = [
  { key: "hoy", label: "Hoy y mañana" },
  { key: "semana", label: "Semana" },
  { key: "anio", label: "Año" },
  { key: "demoradas", label: "Demoradas" },
  { key: "proyectos", label: "Proyectos" },
  { key: "recurrentes", label: "Recurrentes" },
];

/** Seguimiento de tareas: hoy, mañana, semana a semana, el año completo, demoradas y
 *  proyectos (seguridad de la información, nuevos proyectos…) repartidos por semanas. */
export function SeguimientoPage() {
  const [tab, setTab] = useState<Tab>("hoy");
  const [semanaSel, setSemanaSel] = useState<{ anio: number; semana: number } | null>(null);
  const [responsableId, setResponsableId] = useState<string>("");
  const [nueva, setNueva] = useState(false);
  const esAdmin = useAuthStore((s) => s.role) === "administrador";
  const { data: responsables = [] } = useResponsables();

  const filtro: FiltroTareas = responsableId ? { responsable_id: Number(responsableId) } : {};
  const { data: res } = useQuery({
    queryKey: [QK, "resumen"],
    queryFn: () => seguimientoApi.resumen().then((r) => r.data),
  });

  const anio = semanaSel?.anio ?? res?.anio_iso;
  const semana = semanaSel?.semana ?? res?.semana_iso;

  const tarjetas = res
    ? [
        { label: "Hoy", valor: res.tareas_hoy, tab: "hoy" as Tab, clases: "text-gray-900" },
        { label: "Mañana", valor: res.tareas_manana, tab: "hoy" as Tab, clases: "text-gray-900" },
        {
          label: `Semana ${res.semana_iso}`,
          valor: `${res.semana_completadas}/${res.semana_total}`,
          tab: "semana" as Tab,
          clases: "text-gray-900",
        },
        { label: "Demoradas", valor: res.demoradas, tab: "demoradas" as Tab, clases: res.demoradas ? "text-red-600" : "text-gray-900" },
      ]
    : [];

  return (
    <div className="p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Tareas y Proyectos</h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Seguimiento diario, semanal y anual de tareas, demoradas y proyectos repartidos semana a semana.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {esAdmin && (
            <select value={responsableId} onChange={(e) => setResponsableId(e.target.value)} className={`${inputCls} w-52`}>
              <option value="">Todos los responsables</option>
              {responsables.map((r) => (
                <option key={r.id} value={r.id}>{r.nombre}</option>
              ))}
            </select>
          )}
          <button onClick={() => setNueva(true)} className={`${btnPrimario} flex-shrink-0`}>
            <Plus size={16} /> Nueva tarea
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {tarjetas.map((t) => (
          <button
            key={t.label}
            onClick={() => {
              setTab(t.tab);
              if (t.tab === "semana") setSemanaSel(null);
            }}
            className="rounded-xl border border-gray-200 bg-white p-3 text-left hover:border-primary"
          >
            <div className="text-xs text-gray-500">{t.label}</div>
            <div className={`text-2xl font-semibold ${t.clases}`}>{t.valor}</div>
          </button>
        ))}
      </div>

      <div className="mb-4 flex overflow-x-auto border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.key ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
            {t.key === "demoradas" && res?.demoradas ? (
              <span className="ml-1.5 rounded-full bg-red-100 px-1.5 text-xs text-red-700">{res.demoradas}</span>
            ) : null}
          </button>
        ))}
      </div>

      {tab === "hoy" && <HoyMananaTab filtro={filtro} />}
      {tab === "semana" && anio && semana && (
        <SemanaTab anio={anio} semana={semana} filtro={filtro} onCambiar={(a, s) => setSemanaSel({ anio: a, semana: s })} />
      )}
      {tab === "anio" && anio && (
        <AnioTab
          anioInicial={anio}
          filtro={filtro}
          onSemana={(a, s) => {
            setSemanaSel({ anio: a, semana: s });
            setTab("semana");
          }}
        />
      )}
      {tab === "demoradas" && <DemoradasTab filtro={filtro} />}
      {tab === "proyectos" && <ProyectosTab />}
      {tab === "recurrentes" && <RecurrentesTab />}

      {nueva && <TareaFormModal tarea={null} fechaInicial={res?.hoy} onClose={() => setNueva(false)} />}
    </div>
  );
}
