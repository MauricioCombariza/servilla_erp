import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { flujoApi } from "@/api/flujo";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { FlujoCaja60Dias, ResumenMensualFlujo } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();

const PERIODO_COLOR: Record<string, string> = {
  "VENCIDO": "bg-red-100 text-red-700",
  "ESTA SEMANA": "bg-amber-100 text-amber-700",
  "ESTE MES": "bg-blue-100 text-blue-700",
  "PROXIMO MES": "bg-gray-100 text-gray-600",
};

type Tab = "60dias" | "mensual";

export function FlujoCajaPage() {
  const [tab, setTab] = useState<Tab>("60dias");
  const [anio, setAnio] = useState(HOY.getFullYear());

  const { data: flujo60 = [], isLoading: load60 } = useQuery({
    queryKey: ["flujo-60dias"],
    queryFn: () => flujoApi.flujo60dias().then((r) => r.data),
    enabled: tab === "60dias",
  });

  const { data: mensual = [], isLoading: loadM } = useQuery({
    queryKey: ["flujo-mensual", anio],
    queryFn: () => flujoApi.resumenMensual(anio).then((r) => r.data),
    enabled: tab === "mensual",
  });

  const ingresos60 = flujo60.filter((f) => f.tipo === "ingreso").reduce((s, f) => s + f.monto, 0);
  const egresos60  = flujo60.filter((f) => f.tipo === "egreso").reduce((s, f) => s + f.monto, 0);

  const chartData = [...mensual]
    .reverse()
    .map((m) => ({
      name: `${MESES[m.mes - 1]} ${m.anio}`,
      Facturado: m.total_facturado,
      Cobrado: m.cobrado,
      Costos: m.costo_mensajero + m.gastos_admin + m.costo_nomina,
      "Flujo neto": m.flujo_neto,
    }));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Flujo de Caja</h1>
          <p className="text-sm text-gray-500 mt-0.5">Ingresos y egresos consolidados</p>
        </div>
        {tab === "mensual" && (
          <input
            type="number"
            value={anio}
            onChange={(e) => setAnio(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-24"
          />
        )}
      </div>

      <div className="flex border-b border-gray-200 mb-6">
        {(["60dias", "mensual"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "60dias" ? "Próximos 60 días" : "Resumen mensual"}
          </button>
        ))}
      </div>

      {tab === "60dias" && (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Por cobrar</p>
              <p className="text-xl font-semibold text-green-700 mt-1">${fmt.format(ingresos60)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Por pagar</p>
              <p className="text-xl font-semibold text-red-600 mt-1">${fmt.format(egresos60)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">Balance proyectado</p>
              <p className={`text-xl font-semibold mt-1 ${ingresos60 - egresos60 >= 0 ? "text-green-700" : "text-red-600"}`}>
                ${fmt.format(ingresos60 - egresos60)}
              </p>
            </div>
          </div>

          {load60 ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : flujo60.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin movimientos en los próximos 60 días</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Tipo", "Descripción", "Categoría", "Monto", "Período"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {flujo60.map((f, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{f.fecha}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          f.tipo === "ingreso" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}>
                          {f.tipo}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900 text-xs">{f.descripcion}</td>
                      <td className="px-4 py-3 text-gray-600 text-xs">{f.categoria}</td>
                      <td className={`px-4 py-3 font-medium ${f.tipo === "ingreso" ? "text-green-700" : "text-red-600"}`}>
                        <CurrencyCell value={f.monto} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${PERIODO_COLOR[f.periodo] ?? ""}`}>
                          {f.periodo}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "mensual" && (
        <>
          {loadM ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : mensual.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin datos para {anio}</div>
          ) : (
            <>
              {/* Chart */}
              <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Facturado vs Cobrado vs Costos</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={chartData} margin={{ top: 0, right: 16, left: 16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${fmt.format(v / 1_000_000)}M`} />
                    <Tooltip formatter={(v: number) => `$${fmt.format(v)}`} />
                    <Legend />
                    <Bar dataKey="Facturado" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Cobrado" fill="#22c55e" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="Costos" fill="#ef4444" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
                <h3 className="text-sm font-medium text-gray-700 mb-4">Flujo neto mensual</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${fmt.format(v / 1_000_000)}M`} />
                    <Tooltip formatter={(v: number) => `$${fmt.format(v)}`} />
                    <Line type="monotone" dataKey="Flujo neto" stroke="#6366f1" strokeWidth={2} dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* Tabla detalle */}
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      {["Período","Facturado","Cobrado","C. Mensajero","Gastos Admin","Nómina","Flujo neto"].map((h) => (
                        <th key={h} className="text-right first:text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {mensual.map((m) => (
                      <tr key={`${m.anio}-${m.mes}`} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">
                          {MESES[m.mes - 1]} {m.anio}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-700"><CurrencyCell value={m.total_facturado} /></td>
                        <td className="px-4 py-3 text-right text-green-700 font-medium"><CurrencyCell value={m.cobrado} /></td>
                        <td className="px-4 py-3 text-right text-gray-600"><CurrencyCell value={m.costo_mensajero} /></td>
                        <td className="px-4 py-3 text-right text-gray-600"><CurrencyCell value={m.gastos_admin} /></td>
                        <td className="px-4 py-3 text-right text-gray-600"><CurrencyCell value={m.costo_nomina} /></td>
                        <td className={`px-4 py-3 text-right font-semibold ${m.flujo_neto >= 0 ? "text-green-700" : "text-red-600"}`}>
                          <CurrencyCell value={m.flujo_neto} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
