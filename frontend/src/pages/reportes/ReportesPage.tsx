import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Download } from "lucide-react";
import { reportesApi } from "@/api/reportes";
import { clientesApi } from "@/api/clientes";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

// ── Utilidades ────────────────────────────────────────────────────────────────
const MESES = ["", "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];

const HOY = new Date().toISOString().split("T")[0];
const INICIO_MES = new Date(new Date().getFullYear(), new Date().getMonth(), 1)
  .toISOString().split("T")[0];

function fmt(n: number) { return `$${n.toLocaleString("es-CO", { maximumFractionDigits: 0 })}`; }
function pct(n: number | null) { return n != null ? `${n.toFixed(1)}%` : "—"; }

function downloadCsv(rows: Record<string, unknown>[], filename: string) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const lines = [cols.join(","), ...rows.map(r => cols.map(c => JSON.stringify(r[c] ?? "")).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

// ── Tab bar ───────────────────────────────────────────────────────────────────
const TABS = ["Operacional", "Mensajeros", "Órdenes", "Facturación", "Tendencias"] as const;
type Tab = (typeof TABS)[number];

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div className="flex gap-1 bg-gray-100 p-1 rounded-lg mb-6">
      {TABS.map((t) => (
        <button key={t} onClick={() => onChange(t)}
          className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors
            ${active === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
          {t}
        </button>
      ))}
    </div>
  );
}

// ── Resumen métricas ──────────────────────────────────────────────────────────
function MetricCards({ items }: { items: { label: string; value: string; sub?: string }[] }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
      {items.map(({ label, value, sub }) => (
        <div key={label} className="bg-white rounded-xl border border-gray-200 px-5 py-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
          <p className="text-xl font-semibold text-gray-900 mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
        </div>
      ))}
    </div>
  );
}

// ── Tab 1: Operacional ────────────────────────────────────────────────────────
function TabOperacional() {
  const anioActual = new Date().getFullYear();
  const [anio, setAnio] = useState(anioActual);
  const [mes, setMes] = useState<number | undefined>(new Date().getMonth() + 1);

  const { data = [], isLoading } = useQuery({
    queryKey: ["reporte-operacional", anio, mes],
    queryFn: () => reportesApi.operacional(anio, mes).then((r) => r.data),
  });

  const totalSer = data.reduce((s, r) => s + r.total_seriales, 0);
  const totalIng = data.reduce((s, r) => s + r.ingreso_cliente, 0);
  const totalCos = data.reduce((s, r) => s + r.costo_mensajero, 0);
  const totalMar = totalIng - totalCos;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={anio} onChange={(e) => setAnio(+e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white">
          {[anioActual - 1, anioActual, anioActual + 1].map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={mes ?? ""} onChange={(e) => setMes(e.target.value ? +e.target.value : undefined)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">Año completo</option>
          {MESES.slice(1).map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
        </select>
        <button onClick={() => downloadCsv(data as never, `operacional_${anio}_${mes ?? "anual"}.csv`)}
          className="ml-auto flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg px-3 py-2">
          <Download size={14} /> CSV
        </button>
      </div>

      <MetricCards items={[
        { label: "Seriales", value: totalSer.toLocaleString() },
        { label: "Ingreso estimado", value: fmt(totalIng) },
        { label: "Costo mensajero", value: fmt(totalCos) },
        { label: "Margen", value: fmt(totalMar), sub: totalIng ? pct(totalMar / totalIng * 100) : "—" },
      ]} />

      {isLoading ? <div className="text-center py-16 text-gray-400">Cargando...</div> : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[750px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>{["Cliente","Entregas","Dev.","Total","Ingreso","Costo Mensajero","Margen","Margen %"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-600 uppercase tracking-wide">{h}</th>
              ))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((r) => (
                <tr key={r.cliente} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-medium text-gray-900 max-w-[180px] truncate">{r.cliente}</td>
                  <td className="px-4 py-2.5 text-green-700">{r.entregas.toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-orange-600">{r.devoluciones.toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-gray-700">{r.total_seriales.toLocaleString()}</td>
                  <td className="px-4 py-2.5"><CurrencyCell value={r.ingreso_cliente} /></td>
                  <td className="px-4 py-2.5"><CurrencyCell value={r.costo_mensajero} /></td>
                  <td className="px-4 py-2.5"><CurrencyCell value={r.margen} /></td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs font-medium ${(r.margen_pct ?? 0) >= 0 ? "text-green-700" : "text-red-600"}`}>
                      {pct(r.margen_pct)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.length && <div className="text-center py-12 text-gray-400">Sin datos para este período</div>}
        </div>
      )}
    </div>
  );
}

// ── Tab 2: Mensajeros ─────────────────────────────────────────────────────────
function TabMensajeros() {
  const [desde, setDesde] = useState(INICIO_MES);
  const [hasta, setHasta] = useState(HOY);

  const { data = [], isLoading } = useQuery({
    queryKey: ["reporte-mensajeros", desde, hasta],
    queryFn: () => reportesApi.mensajeros(desde, hasta).then((r) => r.data),
  });

  const top10 = data.slice(0, 10);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span className="text-gray-400">—</span>
        <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <button onClick={() => downloadCsv(data as never, `mensajeros_${desde}_${hasta}.csv`)}
          className="ml-auto flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg px-3 py-2">
          <Download size={14} /> CSV
        </button>
      </div>

      <MetricCards items={[
        { label: "Personal", value: data.length.toString() },
        { label: "Total seriales", value: data.reduce((s, r) => s + r.total_seriales, 0).toLocaleString() },
        { label: "Costo mensajero", value: fmt(data.reduce((s, r) => s + r.total_mensajero, 0)) },
        { label: "Costo alistamiento", value: fmt(data.reduce((s, r) => s + r.costo_alistamiento, 0)) },
      ]} />

      {isLoading ? <div className="text-center py-16 text-gray-400">Cargando...</div> : (
        <>
          {top10.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4">
              <p className="text-xs font-medium text-gray-500 uppercase mb-3">Top 10 por costo total</p>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={top10} margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="cod_men" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v: number) => fmt(v)} />
                  <Bar dataKey="total_mensajero" name="Mensajero" fill="#6366f1" stackId="a" radius={[0,0,0,0]} />
                  <Bar dataKey="costo_alistamiento" name="Alistamiento" fill="#f59e0b" stackId="a" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm min-w-[650px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>{["Código","Nombre","Planillas","Entregas","Dev.","Seriales","Costo Mensajero","Costo Alistamiento","Total"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-600 uppercase tracking-wide">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.map((r) => (
                  <tr key={r.cod_men} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono font-medium text-gray-900">{r.cod_men}</td>
                    <td className="px-4 py-2.5 text-gray-700">{r.nombre ?? "—"}</td>
                    <td className="px-4 py-2.5 text-gray-600">{r.planillas || "—"}</td>
                    <td className="px-4 py-2.5 text-green-700">{r.entregas ? r.entregas.toLocaleString() : "—"}</td>
                    <td className="px-4 py-2.5 text-orange-600">{r.devoluciones ? r.devoluciones.toLocaleString() : "—"}</td>
                    <td className="px-4 py-2.5 text-gray-700">{r.total_seriales ? r.total_seriales.toLocaleString() : "—"}</td>
                    <td className="px-4 py-2.5"><CurrencyCell value={r.total_mensajero} /></td>
                    <td className="px-4 py-2.5"><CurrencyCell value={r.costo_alistamiento} /></td>
                    <td className="px-4 py-2.5 font-medium"><CurrencyCell value={r.total_mensajero + r.costo_alistamiento} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.length && <div className="text-center py-12 text-gray-400">Sin datos para este período</div>}
          </div>
        </>
      )}
    </div>
  );
}

// ── Tab 3: Órdenes ────────────────────────────────────────────────────────────
function TabOrdenes() {
  const [desde, setDesde] = useState(INICIO_MES);
  const [hasta, setHasta] = useState(HOY);
  const [clienteId, setClienteId] = useState<number | undefined>();

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes", true],
    queryFn: () => clientesApi.list(true).then((r) => r.data),
  });

  const { data = [], isLoading } = useQuery({
    queryKey: ["reporte-ordenes", desde, hasta, clienteId],
    queryFn: () => reportesApi.ordenes(desde, hasta, clienteId).then((r) => r.data),
  });

  const completadas = data.filter((r) => r.pct_gestionado >= 100).length;

  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span className="text-gray-400">—</span>
        <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <select value={clienteId ?? ""} onChange={(e) => setClienteId(e.target.value ? +e.target.value : undefined)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white">
          <option value="">Todos los clientes</option>
          {clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre_empresa}</option>)}
        </select>
        <button onClick={() => downloadCsv(data as never, `ordenes_${desde}_${hasta}.csv`)}
          className="ml-auto flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg px-3 py-2">
          <Download size={14} /> CSV
        </button>
      </div>

      <MetricCards items={[
        { label: "Órdenes", value: data.length.toString() },
        { label: "Completadas", value: `${completadas} / ${data.length}` },
        { label: "Total ítems", value: data.reduce((s, r) => s + r.cantidad_total, 0).toLocaleString() },
        { label: "Valor total", value: fmt(data.reduce((s, r) => s + r.valor_total, 0)) },
      ]} />

      {isLoading ? <div className="text-center py-16 text-gray-400">Cargando...</div> : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>{["Orden","Cliente","Fecha","Total","Entregados","Dev.","Pendientes","% Gestión","Estado"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-600 uppercase tracking-wide">{h}</th>
              ))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((r) => (
                <tr key={r.numero_orden} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{r.numero_orden}</td>
                  <td className="px-4 py-2.5 text-gray-900 max-w-[140px] truncate">{r.cliente}</td>
                  <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">{r.fecha_recepcion}</td>
                  <td className="px-4 py-2.5 text-gray-700">{r.cantidad_total}</td>
                  <td className="px-4 py-2.5 text-green-700">{r.cantidad_entregados}</td>
                  <td className="px-4 py-2.5 text-orange-600">{r.cantidad_devolucion}</td>
                  <td className="px-4 py-2.5 text-gray-500">{r.pendientes}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-gray-200 rounded-full h-1.5 w-16">
                        <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${Math.min(100, r.pct_gestionado)}%` }} />
                      </div>
                      <span className="text-xs text-gray-500">{r.pct_gestionado.toFixed(0)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                      ${r.estado === "activa" ? "bg-blue-50 text-blue-700" :
                        r.estado === "finalizada" ? "bg-green-50 text-green-700" :
                        "bg-red-50 text-red-500"}`}>
                      {r.estado}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.length && <div className="text-center py-12 text-gray-400">Sin órdenes para este período</div>}
        </div>
      )}
    </div>
  );
}

// ── Tab 4: Facturación ────────────────────────────────────────────────────────
function TabFacturacion() {
  const [desde, setDesde] = useState(INICIO_MES);
  const [hasta, setHasta] = useState(HOY);

  const { data = [], isLoading } = useQuery({
    queryKey: ["reporte-facturacion", desde, hasta],
    queryFn: () => reportesApi.facturacion(desde, hasta).then((r) => r.data),
  });

  const totalFac = data.reduce((s, r) => s + r.total_facturado, 0);
  const totalCob = data.reduce((s, r) => s + r.total_cobrado, 0);
  const totalPen = data.reduce((s, r) => s + r.pendiente, 0);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span className="text-gray-400">—</span>
        <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <button onClick={() => downloadCsv(data as never, `facturacion_${desde}_${hasta}.csv`)}
          className="ml-auto flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg px-3 py-2">
          <Download size={14} /> CSV
        </button>
      </div>

      <MetricCards items={[
        { label: "Facturas", value: data.reduce((s, r) => s + r.num_facturas, 0).toString() },
        { label: "Total facturado", value: fmt(totalFac) },
        { label: "Cobrado", value: fmt(totalCob), sub: totalFac ? pct(totalCob / totalFac * 100) : undefined },
        { label: "Pendiente", value: fmt(totalPen) },
      ]} />

      {isLoading ? <div className="text-center py-16 text-gray-400">Cargando...</div> : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[600px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>{["Cliente","Facturas","Facturado","Cobrado","Pendiente","% Cobrado"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-600 uppercase tracking-wide">{h}</th>
              ))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.map((r) => (
                <tr key={r.cliente} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-medium text-gray-900 max-w-[180px] truncate">{r.cliente}</td>
                  <td className="px-4 py-2.5 text-gray-600">{r.num_facturas}</td>
                  <td className="px-4 py-2.5"><CurrencyCell value={r.total_facturado} /></td>
                  <td className="px-4 py-2.5"><CurrencyCell value={r.total_cobrado} /></td>
                  <td className="px-4 py-2.5">
                    <span className={r.pendiente > 0 ? "text-amber-600 font-medium" : "text-gray-400"}>
                      {fmt(r.pendiente)}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-sm text-gray-600">
                    {r.total_facturado > 0 ? pct(r.total_cobrado / r.total_facturado * 100) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data.length && <div className="text-center py-12 text-gray-400">Sin facturas para este período</div>}
        </div>
      )}
    </div>
  );
}

// ── Tab 5: Tendencias ─────────────────────────────────────────────────────────
function TabTendencias() {
  const [meses, setMeses] = useState(12);

  const { data = [], isLoading } = useQuery({
    queryKey: ["reporte-tendencias", meses],
    queryFn: () => reportesApi.tendencias(meses).then((r) => r.data),
  });

  const chartData = data.map((r) => ({
    ...r,
    mes: r.mes.slice(5),  // "2026-06" → "06"
    mesLabel: r.mes,
  }));

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        {[3, 6, 12, 24].map((m) => (
          <button key={m} onClick={() => setMeses(m)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors
              ${meses === m ? "bg-primary text-white" : "border border-gray-300 text-gray-600 hover:bg-gray-50"}`}>
            {m} meses
          </button>
        ))}
      </div>

      {isLoading ? <div className="text-center py-16 text-gray-400">Cargando...</div> : (
        <>
          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <p className="text-xs font-medium text-gray-500 uppercase mb-4">Seriales por mes</p>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(_, p) => p[0]?.payload?.mesLabel ?? ""}
                  formatter={(v: number, name: string) => [v.toLocaleString(), name]}
                />
                <Legend />
                <Bar dataKey="entregas" name="Entregas" fill="#22c55e" radius={[3,3,0,0]} />
                <Bar dataKey="devoluciones" name="Devoluciones" fill="#f97316" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-5 mb-4">
            <p className="text-xs font-medium text-gray-500 uppercase mb-4">Ingreso estimado vs Costo mensajero</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                <Tooltip
                  labelFormatter={(_, p) => p[0]?.payload?.mesLabel ?? ""}
                  formatter={(v: number) => [fmt(v)]}
                />
                <Legend />
                <Line type="monotone" dataKey="ingreso_estimado" name="Ingreso" stroke="#6366f1" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="costo_mensajero" name="Costo mensajero" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>{["Mes","Entregas","Dev.","Total Seriales","Ingreso Est.","Costo Mensajero","Margen"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-medium text-gray-600 uppercase tracking-wide">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[...data].reverse().map((r) => (
                  <tr key={r.mes} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-mono text-gray-700">{r.mes}</td>
                    <td className="px-4 py-2.5 text-green-700">{r.entregas.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-orange-600">{r.devoluciones.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-gray-700">{r.total_seriales.toLocaleString()}</td>
                    <td className="px-4 py-2.5"><CurrencyCell value={r.ingreso_estimado} /></td>
                    <td className="px-4 py-2.5"><CurrencyCell value={r.costo_mensajero} /></td>
                    <td className="px-4 py-2.5"><CurrencyCell value={r.ingreso_estimado - r.costo_mensajero} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.length && <div className="text-center py-12 text-gray-400">Sin datos</div>}
          </div>
        </>
      )}
    </div>
  );
}

// ── Página raíz ───────────────────────────────────────────────────────────────
export function ReportesPage() {
  const [tab, setTab] = useState<Tab>("Operacional");

  return (
    <div>
      <h1 className="text-xl font-semibold text-gray-900 mb-4">Reportes</h1>
      <TabBar active={tab} onChange={setTab} />
      {tab === "Operacional"  && <TabOperacional />}
      {tab === "Mensajeros"   && <TabMensajeros />}
      {tab === "Órdenes"      && <TabOrdenes />}
      {tab === "Facturación"  && <TabFacturacion />}
      {tab === "Tendencias"   && <TabTendencias />}
    </div>
  );
}
