import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { facturacionApi } from "@/api/facturacion";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

const CLASIF_STYLE: Record<string, string> = {
  VENCIDA:      "bg-red-100 text-red-700",
  "POR VENCER": "bg-amber-100 text-amber-700",
  VIGENTE:      "bg-green-100 text-green-700",
};

const TIPO_STYLE: Record<string, string> = {
  factura:     "bg-blue-50 text-blue-700",
  liquidacion: "bg-purple-50 text-purple-700",
  ciudades:    "bg-teal-50 text-teal-700",
  transporte:  "bg-indigo-50 text-indigo-700",
  gasto:       "bg-orange-50 text-orange-700",
  gasto_fijo:  "bg-rose-50 text-rose-700",
  nomina:      "bg-emerald-50 text-emerald-700",
};

const TIPO_LABEL: Record<string, string> = {
  factura:     "Factura",
  liquidacion: "Liquidación",
  ciudades:    "Ciudades",
  transporte:  "Transporte",
  gasto:       "Gasto",
  gasto_fijo:  "Gasto fijo",
  nomina:      "Nómina",
};

const tipoLabel = (t: string) => TIPO_LABEL[t] ?? t;

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });

export function CuentasPagarPage() {
  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: ["cuentas-pagar"],
    queryFn: () => facturacionApi.cuentasPorPagar().then((r) => r.data),
  });

  const [tipoFiltro, setTipoFiltro] = useState<string>("todos");

  // Tipos distintos presentes (para los chips de filtro), con su conteo.
  const tipos = useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of cuentas) counts.set(c.tipo, (counts.get(c.tipo) ?? 0) + 1);
    return [...counts.entries()].map(([tipo, count]) => ({ tipo, count }));
  }, [cuentas]);

  const filtradas = useMemo(
    () => (tipoFiltro === "todos" ? cuentas : cuentas.filter((c) => c.tipo === tipoFiltro)),
    [cuentas, tipoFiltro],
  );

  const totalPendiente = filtradas.reduce((s, c) => s + c.monto, 0);
  const totalVencido   = filtradas.filter((c) => c.clasificacion === "VENCIDA").reduce((s, c) => s + c.monto, 0);
  const estaSemana     = filtradas.filter((c) => c.clasificacion === "POR VENCER").reduce((s, c) => s + c.monto, 0);

  const chipBase = "px-3 py-1 rounded-full text-xs font-medium border transition-colors";
  const chipCls = (active: boolean) =>
    `${chipBase} ${active ? "bg-gray-900 text-white border-gray-900" : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"}`;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Cuentas por Pagar</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Todas las cuentas por pagar: facturas, liquidaciones, ciudades, transporte, gastos y nómina
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Total pendiente</p>
          <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(totalPendiente)}</p>
        </div>
        <div className="bg-white rounded-xl border border-red-200 p-4">
          <p className="text-xs text-red-500 uppercase tracking-wide">Vencido</p>
          <p className="text-xl font-semibold text-red-600 mt-1">${fmt.format(totalVencido)}</p>
        </div>
        <div className="bg-white rounded-xl border border-amber-200 p-4">
          <p className="text-xs text-amber-500 uppercase tracking-wide">Vence esta semana</p>
          <p className="text-xl font-semibold text-amber-600 mt-1">${fmt.format(estaSemana)}</p>
        </div>
      </div>

      {tipos.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          <button className={chipCls(tipoFiltro === "todos")} onClick={() => setTipoFiltro("todos")}>
            Todos ({cuentas.length})
          </button>
          {tipos.map(({ tipo, count }) => (
            <button key={tipo} className={chipCls(tipoFiltro === tipo)} onClick={() => setTipoFiltro(tipo)}>
              {tipoLabel(tipo)} ({count})
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : filtradas.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin cuentas pendientes</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Tipo","Referencia","Acreedor","Vencimiento","Días hasta vence","Monto","Clasificación"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtradas.map((c, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${TIPO_STYLE[c.tipo] ?? "bg-gray-100 text-gray-600"}`}>
                      {tipoLabel(c.tipo)}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.referencia}</td>
                  <td className="px-4 py-3 text-gray-900">{c.acreedor_o_deudor}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{c.fecha_vencimiento}</td>
                  <td className={`px-4 py-3 font-medium ${c.dias < 0 ? "text-red-600" : "text-gray-600"}`}>
                    {c.dias < 0 ? `${Math.abs(c.dias)}d vencida` : `en ${c.dias}d`}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900"><CurrencyCell value={c.monto} /></td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${CLASIF_STYLE[c.clasificacion] ?? ""}`}>
                      {c.clasificacion}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-50 border-t border-gray-200">
              <tr>
                <td colSpan={5} className="px-4 py-3 text-sm font-medium text-gray-700">Total</td>
                <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={totalPendiente} /></td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
