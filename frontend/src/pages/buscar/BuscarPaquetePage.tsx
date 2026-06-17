import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { buscarApi, type BuscarModo, type PaqueteItem } from "@/api/buscar";

const MODOS: { value: BuscarModo; label: string; placeholder: string }[] = [
  { value: "serial",   label: "Número de Guía / Serial", placeholder: "Ej: 9003860413" },
  { value: "nombre",   label: "Nombre del Destinatario",  placeholder: "Ej: amanda valbuena  /  valbuena leon" },
  { value: "telefono", label: "Teléfono",                 placeholder: "Ej: 3001234567" },
];

function FuenteBadge({ fuente }: { fuente: string }) {
  const isHisto = fuente === "Histórico";
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        isHisto ? "bg-blue-50 text-blue-700" : "bg-indigo-50 text-indigo-700"
      }`}
    >
      {isHisto ? "📁 Histórico" : "🗄️ ERP"}
    </span>
  );
}

function DetailCard({ item }: { item: PaqueteItem }) {
  return (
    <div className="mt-6 border border-gray-200 rounded-xl p-5 bg-gray-50">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Detalle</h3>
      <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
        <div><span className="text-gray-500">Serial:</span>{" "}<span className="font-mono font-medium">{item.clave}</span></div>
        <div><span className="text-gray-500">Fuente:</span>{" "}<FuenteBadge fuente={item.fuente} /></div>
        {item.nombre    && <div><span className="text-gray-500">Nombre:</span> {item.nombre}</div>}
        {item.cliente   && <div><span className="text-gray-500">Cliente:</span> {item.cliente}</div>}
        {item.direccion && <div className="col-span-2"><span className="text-gray-500">Dirección:</span> {item.direccion}</div>}
        {item.ciudad    && <div><span className="text-gray-500">Ciudad:</span> {item.ciudad}</div>}
        {item.fecha     && <div><span className="text-gray-500">Fecha:</span> {item.fecha}</div>}
        {item.cod_men   && <div><span className="text-gray-500">Mensajero:</span> {item.cod_men}</div>}
        {item.estado    && <div><span className="text-gray-500">Estado:</span> {item.estado}</div>}
        {item.planilla  && <div><span className="text-gray-500">Planilla:</span> <span className="font-mono">{item.planilla}</span></div>}
        {item.tipo_gestion && <div><span className="text-gray-500">Tipo Gestión:</span> {item.tipo_gestion}</div>}
      </div>
    </div>
  );
}

export function BuscarPaquetePage() {
  const [modo, setModo] = useState<BuscarModo>("serial");
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");

  const { data, isFetching, isError } = useQuery({
    queryKey: ["buscar", q, modo],
    queryFn: () => buscarApi.buscarPaquete(q, modo).then((r) => r.data),
    enabled: q.length >= 2,
    staleTime: 15_000,
  });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (trimmed.length >= 2) setQ(trimmed);
  }

  function handleModoChange(m: BuscarModo) {
    setModo(m);
    setQ("");
    setInput("");
  }

  const placeholder = MODOS.find((m) => m.value === modo)?.placeholder ?? "";

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Buscar Paquete</h1>
      <p className="text-sm text-gray-500 mb-6">
        Busca simultáneamente en el histórico (bases_web) y en el ERP.
      </p>

      {/* Modo selector */}
      <div className="flex gap-1 mb-4 bg-gray-100 p-1 rounded-lg w-fit">
        {MODOS.map((m) => (
          <button
            key={m.value}
            onClick={() => handleModoChange(m.value)}
            className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
              modo === m.value
                ? "bg-white shadow text-gray-900 font-medium"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {modo === "telefono" && (
        <div className="mb-4 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
          La búsqueda por teléfono solo aplica a la base iMile activa, que no está conectada al ERP.
          Usa el Streamlit para buscar por teléfono.
        </div>
      )}

      {/* Search form */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <div className="relative flex-1 max-w-lg">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            disabled={modo === "telefono"}
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary outline-none disabled:bg-gray-100 disabled:text-gray-400"
          />
        </div>
        <button
          type="submit"
          disabled={input.trim().length < 2 || modo === "telefono"}
          className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg disabled:opacity-50 hover:bg-primary/90 transition-colors"
        >
          Buscar
        </button>
      </form>

      {/* Status */}
      {isFetching && <p className="text-sm text-gray-500 mb-4">Buscando...</p>}
      {isError && (
        <p className="text-sm text-red-600 mb-4">Error al buscar. Intenta de nuevo.</p>
      )}
      {data && !isFetching && (
        <p className="text-sm text-gray-600 mb-4">
          <span className="font-medium">{data.total}</span> resultado(s) —{" "}
          Histórico: <span className="font-medium">{data.historico}</span> · ERP:{" "}
          <span className="font-medium">{data.erp}</span>
        </p>
      )}

      {/* Results table */}
      {data && data.items.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Serial</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Nombre</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Dirección</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Ciudad</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Fecha</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Mensajero</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Estado</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Fuente</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.items.map((item: PaqueteItem, idx: number) => (
                  <tr key={`${item.clave}-${idx}`} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-800">{item.clave}</td>
                    <td className="px-4 py-3 text-gray-700">{item.nombre ?? item.cliente ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{item.direccion ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-700">{item.ciudad ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{item.fecha ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-600">{item.cod_men ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-700">{item.estado ?? "—"}</td>
                    <td className="px-4 py-3"><FuenteBadge fuente={item.fuente} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data && data.items.length === 0 && !isFetching && (
        <p className="text-sm text-gray-500">No se encontraron resultados.</p>
      )}

      {data && data.items.length === 1 && <DetailCard item={data.items[0]} />}
    </div>
  );
}
