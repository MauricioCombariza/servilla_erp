import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ChevronDown, ChevronRight, Download } from "lucide-react";
import { pendientesEntregaApi, type TipoPersonalPendientes } from "@/api/pendientesEntrega";

const TABS: { value: TipoPersonalPendientes; label: string }[] = [
  { value: "courier_externo", label: "Courier Externo" },
  { value: "mensajero", label: "Mensajeros" },
];

export function PendientesEntregaPage() {
  const [tipo, setTipo] = useState<TipoPersonalPendientes>("courier_externo");
  const [expandidos, setExpandidos] = useState<Set<string>>(new Set());
  const [descargando, setDescargando] = useState<Record<string, boolean>>({});
  const [error, setError] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["pendientes-entrega", tipo],
    queryFn: () => pendientesEntregaApi.resumen(tipo).then((r) => r.data),
  });

  function cambiarTab(nuevoTipo: TipoPersonalPendientes) {
    setTipo(nuevoTipo);
    setExpandidos(new Set());
    setError("");
  }

  function toggleExpandido(codMen: string) {
    setExpandidos((prev) => {
      const next = new Set(prev);
      if (next.has(codMen)) next.delete(codMen);
      else next.add(codMen);
      return next;
    });
  }

  async function handleDescargar(codMen: string, nombre: string) {
    setDescargando((prev) => ({ ...prev, [codMen]: true }));
    setError("");
    try {
      const r = await pendientesEntregaApi.descargarExcel(codMen, tipo);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pendientes_${codMen}_${nombre.replace(/\s+/g, "_")}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al generar el archivo");
    } finally {
      setDescargando((prev) => ({ ...prev, [codMen]: false }));
    }
  }

  const personas = data?.personas ?? [];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Pendientes de Entrega</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {personas.length} con pendientes
          {data ? ` · desde ${data.corte_desde}` : ""}
        </p>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-4">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => cambiarTab(t.value)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tipo === t.value
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-900"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-500">Cargando...</p>
      ) : isError ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">
            Error al cargar los pendientes. Verifica la conexión a la base de datos.
          </p>
        </div>
      ) : personas.length === 0 ? (
        <p className="text-sm text-gray-500">No hay pendientes de entrega en este momento.</p>
      ) : (
        <div className="border border-gray-200 rounded-xl overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs">
                <th className="text-left px-3 py-2 font-medium w-8"></th>
                <th className="text-left px-3 py-2 font-medium">Nombre</th>
                <th className="text-left px-3 py-2 font-medium">Código</th>
                <th className="text-left px-3 py-2 font-medium">Email</th>
                <th className="text-right px-3 py-2 font-medium">Pendientes</th>
                <th className="text-right px-3 py-2 font-medium">Descargar</th>
              </tr>
            </thead>
            <tbody>
              {personas.map((p) => {
                const abierto = expandidos.has(p.cod_men);
                return (
                  <Fragment key={p.cod_men}>
                    <tr className="border-t border-gray-100">
                      <td className="px-3 py-2">
                        <button onClick={() => toggleExpandido(p.cod_men)} className="text-gray-400 hover:text-gray-700">
                          {abierto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-gray-900">{p.nombre}</td>
                      <td className="px-3 py-2 text-gray-600">{p.cod_men}</td>
                      <td className="px-3 py-2">
                        {p.tiene_email ? (
                          <span className="text-gray-600">{p.email}</span>
                        ) : (
                          <span className="text-amber-600">⚠️ Sin email</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900">{p.pendientes}</td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => handleDescargar(p.cod_men, p.nombre)}
                          disabled={descargando[p.cod_men]}
                          className="inline-flex items-center gap-1.5 bg-primary hover:bg-primary-hover text-white px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                        >
                          <Download size={14} />
                          {descargando[p.cod_men] ? "Generando..." : "Excel"}
                        </button>
                      </td>
                    </tr>
                    {abierto && (
                      <tr className="border-t border-gray-100 bg-gray-50">
                        <td></td>
                        <td colSpan={5} className="px-3 py-2">
                          <table className="min-w-[240px] text-xs">
                            <thead>
                              <tr className="text-gray-500">
                                <th className="text-left py-1 pr-4 font-medium">Mes</th>
                                <th className="text-right py-1 font-medium">Pendientes</th>
                              </tr>
                            </thead>
                            <tbody>
                              {p.desglose_mensual.map((d) => (
                                <tr key={d.mes} className="border-t border-gray-200">
                                  <td className="py-1 pr-4 text-gray-700">{d.mes}</td>
                                  <td className="py-1 text-right text-gray-900">{d.pendientes}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
