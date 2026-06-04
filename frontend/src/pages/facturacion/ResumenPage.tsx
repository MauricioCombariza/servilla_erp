import { useQuery } from "@tanstack/react-query";
import { facturacionApi } from "@/api/facturacion";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { TrendingUp, TrendingDown, AlertTriangle, Clock } from "lucide-react";

interface StatCardProps {
  title: string;
  value: number;
  sub?: string;
  subValue?: number;
  color?: string;
  icon: React.ReactNode;
}

function StatCard({ title, value, sub, subValue, color = "blue", icon }: StatCardProps) {
  const colorMap: Record<string, string> = {
    blue: "bg-blue-50 text-blue-700",
    green: "bg-green-50 text-green-700",
    red: "bg-red-50 text-red-700",
    orange: "bg-orange-50 text-orange-700",
  };
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-start justify-between mb-3">
        <p className="text-sm font-medium text-gray-600">{title}</p>
        <div className={`p-2 rounded-lg ${colorMap[color]}`}>{icon}</div>
      </div>
      <p className="text-2xl font-bold text-gray-900">
        <CurrencyCell value={value} />
      </p>
      {sub && subValue !== undefined && (
        <p className="text-xs text-gray-500 mt-1">
          {sub}: <span className="font-medium"><CurrencyCell value={subValue} /></span>
        </p>
      )}
    </div>
  );
}

export function ResumenPage() {
  const { data: resumen, isLoading } = useQuery({
    queryKey: ["facturacion-resumen"],
    queryFn: () => facturacionApi.resumen().then((r) => r.data),
    refetchInterval: 60_000,
  });

  const { data: cxc = [] } = useQuery({
    queryKey: ["cuentas-cobrar"],
    queryFn: () => facturacionApi.cuentasPorCobrar().then((r) => r.data),
  });

  const { data: cxp = [] } = useQuery({
    queryKey: ["cuentas-pagar"],
    queryFn: () => facturacionApi.cuentasPorPagar().then((r) => r.data),
  });

  if (isLoading || !resumen) return <div className="text-center py-16 text-gray-500">Cargando...</div>;

  const vencidas_cobrar = cxc.filter((c) => c.clasificacion === "VENCIDA");
  const vencidas_pagar = cxp.filter((c) => c.clasificacion === "VENCIDA");

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-6">Resumen Financiero</h1>

      {/* KPIs principales */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          title="Por cobrar (total)"
          value={resumen.total_por_cobrar}
          sub="Vence esta semana"
          subValue={resumen.vence_esta_semana_cobrar}
          color="blue"
          icon={<TrendingUp size={18} />}
        />
        <StatCard
          title="Vencido (cobrar)"
          value={resumen.total_vencido_cobrar}
          color="red"
          icon={<AlertTriangle size={18} />}
        />
        <StatCard
          title="Por pagar (total)"
          value={resumen.total_por_pagar}
          sub="Vence esta semana"
          subValue={resumen.vence_esta_semana_pagar}
          color="orange"
          icon={<TrendingDown size={18} />}
        />
        <StatCard
          title="Facturado este mes"
          value={resumen.facturas_emitidas_mes}
          sub="Recibido este mes"
          subValue={resumen.facturas_recibidas_mes}
          color="green"
          icon={<Clock size={18} />}
        />
      </div>

      {/* Tablas CxC / CxP */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cuentas por cobrar */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Cuentas por cobrar</h2>
            <span className="text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-full">
              {cxc.length} facturas
            </span>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {cxc.slice(0, 15).map((c) => (
              <div key={c.id} className="flex items-center justify-between px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 truncate">{c.acreedor_o_deudor}</p>
                  <p className="text-xs text-gray-500">{c.referencia} · vence {c.fecha_vencimiento}</p>
                </div>
                <div className="text-right ml-3 flex-shrink-0">
                  <p className="text-sm font-semibold text-gray-900">
                    <CurrencyCell value={c.monto} />
                  </p>
                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                    c.clasificacion === "VENCIDA" ? "bg-red-50 text-red-600"
                    : c.clasificacion === "POR VENCER" ? "bg-yellow-50 text-yellow-600"
                    : "bg-green-50 text-green-600"
                  }`}>
                    {c.clasificacion}
                  </span>
                </div>
              </div>
            ))}
            {cxc.length === 0 && (
              <p className="text-center py-8 text-gray-400 text-sm">Sin cuentas pendientes</p>
            )}
          </div>
        </div>

        {/* Cuentas por pagar */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Cuentas por pagar</h2>
            <span className="text-xs bg-orange-50 text-orange-700 px-2 py-1 rounded-full">
              {cxp.length} items
            </span>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {cxp.slice(0, 15).map((c) => (
              <div key={`${c.tipo}-${c.id}`} className="flex items-center justify-between px-5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 truncate">{c.acreedor_o_deudor}</p>
                  <p className="text-xs text-gray-500 capitalize">
                    {c.tipo.replace("_", " ")} · {c.referencia} · {c.fecha_vencimiento}
                  </p>
                </div>
                <div className="text-right ml-3 flex-shrink-0">
                  <p className="text-sm font-semibold text-gray-900">
                    <CurrencyCell value={c.monto} />
                  </p>
                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                    c.clasificacion === "VENCIDA" ? "bg-red-50 text-red-600"
                    : c.clasificacion === "POR VENCER" ? "bg-yellow-50 text-yellow-600"
                    : "bg-green-50 text-green-600"
                  }`}>
                    {c.clasificacion}
                  </span>
                </div>
              </div>
            ))}
            {cxp.length === 0 && (
              <p className="text-center py-8 text-gray-400 text-sm">Sin pagos pendientes</p>
            )}
          </div>
        </div>
      </div>

      {/* Alertas */}
      {(vencidas_cobrar.length > 0 || vencidas_pagar.length > 0) && (
        <div className="mt-6 bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={16} className="text-red-500" />
            <p className="text-sm font-medium text-red-800">Facturas vencidas</p>
          </div>
          <ul className="space-y-1 text-xs text-red-700">
            {vencidas_cobrar.map((c) => (
              <li key={c.id}>📤 {c.acreedor_o_deudor} — <strong>{c.referencia}</strong> — <CurrencyCell value={c.monto} /> ({Math.abs(c.dias)} días vencido)</li>
            ))}
            {vencidas_pagar.map((c) => (
              <li key={`${c.tipo}-${c.id}`}>📥 {c.acreedor_o_deudor} — <strong>{c.referencia}</strong> — <CurrencyCell value={c.monto} /></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
