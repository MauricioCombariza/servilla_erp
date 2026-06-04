import { useQuery } from "@tanstack/react-query";
import { facturacionApi } from "@/api/facturacion";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

const CLASIF_STYLE: Record<string, string> = {
  VENCIDA:    "bg-red-100 text-red-700",
  "POR VENCER": "bg-amber-100 text-amber-700",
  VIGENTE:    "bg-green-100 text-green-700",
};

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });

export function CuentasCobrarPage() {
  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: ["cuentas-cobrar"],
    queryFn: () => facturacionApi.cuentasPorCobrar().then((r) => r.data),
  });

  const totalPendiente = cuentas.reduce((s, c) => s + c.monto, 0);
  const totalVencido   = cuentas.filter((c) => c.clasificacion === "VENCIDA").reduce((s, c) => s + c.monto, 0);
  const estaSemana     = cuentas.filter((c) => c.clasificacion === "POR VENCER").reduce((s, c) => s + c.monto, 0);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Cuentas por Cobrar</h1>
        <p className="text-sm text-gray-500 mt-0.5">Facturas emitidas pendientes de cobro</p>
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

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : cuentas.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin cuentas pendientes</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Factura","Cliente","Vencimiento","Días","Monto","Estado","Clasificación"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cuentas.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.referencia}</td>
                  <td className="px-4 py-3 text-gray-900">{c.acreedor_o_deudor}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{c.fecha_vencimiento}</td>
                  <td className={`px-4 py-3 font-medium ${c.dias < 0 ? "text-red-600" : "text-gray-600"}`}>
                    {c.dias < 0 ? `${Math.abs(c.dias)}d vencida` : `${c.dias}d`}
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900"><CurrencyCell value={c.monto} /></td>
                  <td className="px-4 py-3">
                    <span className="bg-yellow-50 text-yellow-700 px-2 py-0.5 rounded text-xs">{c.estado}</span>
                  </td>
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
                <td colSpan={4} className="px-4 py-3 text-sm font-medium text-gray-700">Total</td>
                <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={totalPendiente} /></td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
