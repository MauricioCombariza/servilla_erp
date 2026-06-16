import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, DollarSign, Trash2, ChevronDown, ChevronRight, Pencil, X } from "lucide-react";
import api from "@/api/client";
import { personalApi } from "@/api/personal";
import { ordenesApi } from "@/api/ordenes";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { Orden } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const HOY_STR = HOY.toISOString().slice(0, 10);
const PRIMER_DIA = new Date(HOY.getFullYear(), HOY.getMonth(), 1).toISOString().slice(0, 10);

interface DetalleFactura {
  id: number; factura_id: number; orden_id: number | null;
  cantidad_sobres: number; costo_asignado: number;
  numero_orden: string | null; cliente_nombre: string | null;
}

interface FacturaTransporte {
  id: number; numero_factura: string; fecha_factura: string;
  courrier_id: number; courrier: { id: number; codigo: string; nombre_completo: string };
  monto_total: number; total_sobres: number; monto_pagado: number;
  estado: string; fecha_vencimiento: string | null; observaciones: string | null;
  fecha_creacion: string | null; detalles: DetalleFactura[];
}

interface ResumenCourierReal {
  courrier: string; total_facturas: number; monto_total: number;
  monto_pagado: number; pendiente: number; total_sobres: number; costo_por_sobre: number;
}

interface ResumenClienteFlete {
  cliente: string; total_sobres: number; costo_total: number; costo_por_sobre: number;
}

const transpApi = {
  prefacturas: (mes: number, anio: number) =>
    api.get("/transporte/prefacturas", { params: { mes, anio } }),
  list: (params: object) => api.get<FacturaTransporte[]>("/transporte/", { params }),
  create: (data: object) => api.post<FacturaTransporte>("/transporte/", data),
  update: (id: number, data: object) => api.put<FacturaTransporte>(`/transporte/${id}`, data),
  pagar: (id: number, data: object) => api.post<FacturaTransporte>(`/transporte/${id}/pagar`, data),
  delete: (id: number) => api.delete(`/transporte/${id}`),
  addDetalle: (facturaId: number, data: object) =>
    api.post<FacturaTransporte>(`/transporte/${facturaId}/detalles`, data),
  removeDetalle: (facturaId: number, detalleId: number) =>
    api.delete<FacturaTransporte>(`/transporte/${facturaId}/detalles/${detalleId}`),
  resumenReal: (anio: number, mes?: number) =>
    api.get<{ couriers: ResumenCourierReal[]; clientes: ResumenClienteFlete[] }>(
      "/transporte/resumen-real", { params: { anio, ...(mes ? { mes } : {}) } }
    ),
};

const ESTADO_STYLE: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  pagada:    "bg-green-50 text-green-700",
  anulada:   "bg-gray-100 text-gray-400",
};

type Tab = "prefacturas" | "resumen" | "facturas";

// ── Página principal ──────────────────────────────────────────────────────────

export function FacturasTransportePage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("prefacturas");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [desde, setDesde] = useState(PRIMER_DIA);
  const [hasta, setHasta] = useState(HOY_STR);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [pagando, setPagando] = useState<FacturaTransporte | null>(null);
  const [editando, setEditando] = useState<FacturaTransporte | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data: prefacturas = [], isLoading: loadPre } = useQuery({
    queryKey: ["prefacturas", mes, anio],
    queryFn: () => transpApi.prefacturas(mes, anio).then((r) => r.data),
    enabled: tab === "prefacturas",
  });

  const { data: resumen, isLoading: loadResumen } = useQuery({
    queryKey: ["transporte-resumen-real", anio, mes],
    queryFn: () => transpApi.resumenReal(anio, mes).then((r) => r.data),
    enabled: tab === "resumen",
  });

  const { data: facturas = [], isLoading: loadFact } = useQuery({
    queryKey: ["facturas-transporte", desde, hasta, search],
    queryFn: () => transpApi.list({ fecha_desde: desde, fecha_hasta: hasta, search: search || undefined }).then((r) => r.data),
    enabled: tab === "facturas",
  });

  const { data: ordenes = [] } = useQuery({
    queryKey: ["ordenes-activas"],
    queryFn: () => ordenesApi.list({ estado: "activa", limit: 500 }).then((r) => r.data),
    enabled: tab === "facturas",
  });

  const eliminar = useMutation({
    mutationFn: (id: number) => transpApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facturas-transporte"] }),
  });

  const totalPre = (prefacturas as any[]).reduce((s: number, p: any) => s + p.monto_estimado, 0);
  const totalPendiente = facturas.filter((f) => f.estado !== "pagada").reduce((s, f) => s + (f.monto_total - f.monto_pagado), 0);

  const tabs: { key: Tab; label: string }[] = [
    { key: "prefacturas", label: "Prefacturas (estimado)" },
    { key: "resumen",     label: "Resumen real" },
    { key: "facturas",    label: "Facturas registradas" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Facturas Transporte / Couriers</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {tab === "prefacturas" && `${MESES[mes-1]} ${anio} · Estimado: $${fmt.format(totalPre)}`}
            {tab === "resumen"     && `${MESES[mes-1]} ${anio}`}
            {tab === "facturas"   && `Saldo pendiente: $${fmt.format(totalPendiente)}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(tab === "prefacturas" || tab === "resumen") && (
            <>
              <select value={mes} onChange={(e) => setMes(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
                {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
              </select>
              <input type="number" value={anio} onChange={(e) => setAnio(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20" />
            </>
          )}
          <button onClick={() => { setTab("facturas"); setShowForm(true); }}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium">
            <Plus size={16} /> Registrar factura
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Prefacturas */}
      {tab === "prefacturas" && (
        loadPre ? <div className="text-center py-16 text-gray-500">Cargando...</div>
        : (prefacturas as any[]).length === 0 ? <div className="text-center py-16 text-gray-400">Sin gestiones de couriers en este período</div>
        : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>{["Courier","Planillas","Local","Nacional","Total seriales","P. local prom.","P. nac. prom.","Monto estimado"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(prefacturas as any[]).map((p) => (
                  <tr key={p.cod_mensajero} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{p.nombre_completo ?? p.cod_mensajero}</p>
                      <p className="text-xs text-gray-400">{p.cod_mensajero}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{p.total_planillas}</td>
                    <td className="px-4 py-3 text-gray-600">{p.total_local}</td>
                    <td className="px-4 py-3 text-gray-600">{p.total_nacional}</td>
                    <td className="px-4 py-3 text-gray-600">{p.total_seriales}</td>
                    <td className="px-4 py-3 text-gray-600"><CurrencyCell value={p.precio_local_promedio} /></td>
                    <td className="px-4 py-3 text-gray-600"><CurrencyCell value={p.precio_nacional_promedio} /></td>
                    <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={p.monto_estimado} /></td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-gray-50 border-t border-gray-200">
                <tr>
                  <td colSpan={7} className="px-4 py-3 text-sm font-medium text-gray-700">Total estimado</td>
                  <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={totalPre} /></td>
                </tr>
              </tfoot>
            </table>
          </div>
        )
      )}

      {/* Tab: Resumen real */}
      {tab === "resumen" && (
        loadResumen ? <div className="text-center py-16 text-gray-500">Cargando...</div>
        : !resumen || resumen.couriers.length === 0 ? <div className="text-center py-16 text-gray-400">Sin facturas en este período</div>
        : (
          <div className="space-y-6">
            {/* Por courier */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                <h2 className="text-sm font-semibold text-gray-700">Por courier</h2>
              </div>
              <table className="w-full text-sm">
                <thead className="border-b border-gray-200">
                  <tr>{["Courier","Facturas","Monto total","Pagado","Pendiente","Sobres","$/Sobre"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {resumen.couriers.map((c) => (
                    <tr key={c.courrier} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{c.courrier}</td>
                      <td className="px-4 py-3 text-gray-600">{c.total_facturas}</td>
                      <td className="px-4 py-3 font-semibold"><CurrencyCell value={c.monto_total} /></td>
                      <td className="px-4 py-3 text-green-700"><CurrencyCell value={c.monto_pagado} /></td>
                      <td className="px-4 py-3 text-red-600"><CurrencyCell value={c.pendiente} /></td>
                      <td className="px-4 py-3 text-gray-600">{fmt.format(c.total_sobres)}</td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={c.costo_por_sobre} /></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50 border-t border-gray-200">
                  <tr>
                    <td className="px-4 py-3 text-sm font-medium text-gray-700">Total</td>
                    <td className="px-4 py-3 text-gray-600">{resumen.couriers.reduce((s, c) => s + c.total_facturas, 0)}</td>
                    <td className="px-4 py-3 font-semibold"><CurrencyCell value={resumen.couriers.reduce((s, c) => s + c.monto_total, 0)} /></td>
                    <td className="px-4 py-3 text-green-700"><CurrencyCell value={resumen.couriers.reduce((s, c) => s + c.monto_pagado, 0)} /></td>
                    <td className="px-4 py-3 text-red-600"><CurrencyCell value={resumen.couriers.reduce((s, c) => s + c.pendiente, 0)} /></td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Por cliente */}
            {resumen.clientes.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
                  <h2 className="text-sm font-semibold text-gray-700">Distribución por cliente</h2>
                </div>
                <table className="w-full text-sm">
                  <thead className="border-b border-gray-200">
                    <tr>{["Cliente","Sobres","Costo total","$/Sobre"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}</tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {resumen.clientes.map((c) => (
                      <tr key={c.cliente} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{c.cliente}</td>
                        <td className="px-4 py-3 text-gray-600">{fmt.format(c.total_sobres)}</td>
                        <td className="px-4 py-3 font-semibold"><CurrencyCell value={c.costo_total} /></td>
                        <td className="px-4 py-3 text-gray-600"><CurrencyCell value={c.costo_por_sobre} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      )}

      {/* Tab: Facturas */}
      {tab === "facturas" && (
        <>
          {/* Filtros */}
          <div className="flex items-center gap-3 mb-4">
            <input placeholder="Buscar factura o courier..." value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-60" />
            <label className="text-xs text-gray-500">Desde</label>
            <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" />
            <label className="text-xs text-gray-500">Hasta</label>
            <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" />
          </div>

          {loadFact ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : facturas.length === 0 ? <div className="text-center py-16 text-gray-400">Sin facturas en el período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>{["","N° Factura","Courier","Fecha","Vencimiento","Sobres","Total","Pagado","Estado",""].map((h, i) => (
                    <th key={i} className="text-left px-3 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                  ))}</tr>
                </thead>
                <tbody>
                  {facturas.map((f) => (
                    <>
                      <tr key={f.id} className={`border-b border-gray-100 hover:bg-gray-50 ${expandedId === f.id ? "bg-blue-50" : ""}`}>
                        <td className="px-3 py-3 w-6">
                          <button onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}
                            className="text-gray-400 hover:text-gray-700">
                            {expandedId === f.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                          </button>
                        </td>
                        <td className="px-3 py-3 font-mono text-xs text-gray-700">{f.numero_factura}</td>
                        <td className="px-3 py-3 text-gray-900">{f.courrier?.nombre_completo ?? "—"}</td>
                        <td className="px-3 py-3 text-gray-600 text-xs">{f.fecha_factura}</td>
                        <td className="px-3 py-3 text-gray-600 text-xs">{f.fecha_vencimiento ?? "—"}</td>
                        <td className="px-3 py-3 text-gray-600">
                          {f.detalles.length > 0
                            ? f.detalles.reduce((s, d) => s + d.cantidad_sobres, 0)
                            : f.total_sobres}
                        </td>
                        <td className="px-3 py-3 font-medium"><CurrencyCell value={f.monto_total} /></td>
                        <td className="px-3 py-3 text-green-700"><CurrencyCell value={f.monto_pagado} /></td>
                        <td className="px-3 py-3">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_STYLE[f.estado] ?? ""}`}>{f.estado}</span>
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center gap-2">
                            <button onClick={() => setEditando(f)} className="text-gray-400 hover:text-blue-600" title="Editar">
                              <Pencil size={14} />
                            </button>
                            {f.estado !== "pagada" && (
                              <button onClick={() => setPagando(f)} className="text-gray-400 hover:text-green-600" title="Registrar pago">
                                <DollarSign size={14} />
                              </button>
                            )}
                            {f.estado !== "pagada" && (
                              <button onClick={() => { if (confirm("¿Eliminar factura?")) eliminar.mutate(f.id); }}
                                className="text-gray-400 hover:text-red-500" title="Eliminar">
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {expandedId === f.id && (
                        <tr key={`det-${f.id}`}>
                          <td colSpan={10} className="bg-blue-50 px-6 py-4 border-b border-gray-200">
                            <DetallePanel
                              factura={f}
                              ordenes={ordenes}
                              onUpdated={(updated) => {
                                qc.setQueryData<FacturaTransporte[]>(
                                  ["facturas-transporte", desde, hasta, search],
                                  (prev) => prev?.map((x) => x.id === updated.id ? updated : x) ?? prev
                                );
                              }}
                            />
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {showForm && (
        <FacturaTransporteForm
          onClose={() => setShowForm(false)}
          onSaved={(nueva) => {
            qc.setQueryData<FacturaTransporte[]>(
              ["facturas-transporte", desde, hasta, search],
              (prev) => [nueva, ...(prev ?? [])],
            );
            setShowForm(false);
          }}
        />
      )}
      {pagando && (
        <PagarTransporteModal
          factura={pagando}
          onClose={() => setPagando(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["facturas-transporte"] }); setPagando(null); }}
        />
      )}
      {editando && (
        <EditFacturaModal
          factura={editando}
          ordenes={ordenes}
          onClose={() => setEditando(null)}
          onSaved={(updated) => {
            qc.setQueryData<FacturaTransporte[]>(
              ["facturas-transporte", desde, hasta, search],
              (prev) => prev?.map((x) => x.id === updated.id ? updated : x) ?? prev
            );
            setEditando(null);
          }}
          onDetalleChanged={(updated) => {
            qc.setQueryData<FacturaTransporte[]>(
              ["facturas-transporte", desde, hasta, search],
              (prev) => prev?.map((x) => x.id === updated.id ? updated : x) ?? prev
            );
            setEditando(updated);
          }}
        />
      )}
    </div>
  );
}

// ── Panel de detalles (órdenes asignadas) ─────────────────────────────────────

function DetallePanel({
  factura, ordenes, onUpdated,
}: {
  factura: FacturaTransporte;
  ordenes: Orden[];
  onUpdated: (updated: FacturaTransporte) => void;
}) {
  const [addOrdenId, setAddOrdenId] = useState<number | "">("");
  const [addSobres, setAddSobres] = useState(1);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);

  const asignadasIds = new Set(factura.detalles.map((d) => d.orden_id));
  const disponibles = ordenes.filter((o) => !asignadasIds.has(o.id));

  async function handleAdd() {
    if (!addOrdenId) return;
    setSaving(true);
    try {
      const res = await transpApi.addDetalle(factura.id, { orden_id: addOrdenId, cantidad_sobres: addSobres });
      onUpdated(res.data);
      setAddOrdenId("");
      setAddSobres(1);
    } finally { setSaving(false); }
  }

  async function handleRemove(detalleId: number) {
    setRemoving(detalleId);
    try {
      const res = await transpApi.removeDetalle(factura.id, detalleId);
      onUpdated(res.data);
    } finally { setRemoving(null); }
  }

  const totalSobresDetalle = factura.detalles.reduce((s, d) => s + d.cantidad_sobres, 0);

  return (
    <div>
      <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
        Órdenes asignadas ({factura.detalles.length})
      </p>
      {factura.detalles.length > 0 ? (
        <table className="w-full text-xs mb-3">
          <thead>
            <tr className="text-gray-500">
              <th className="text-left py-1 pr-4 font-medium">Orden</th>
              <th className="text-left py-1 pr-4 font-medium">Cliente</th>
              <th className="text-right py-1 pr-4 font-medium">Sobres</th>
              <th className="text-right py-1 pr-4 font-medium">%</th>
              <th className="text-right py-1 pr-4 font-medium">Costo asignado</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-blue-100">
            {factura.detalles.map((d) => {
              const pct = totalSobresDetalle > 0 ? (d.cantidad_sobres / totalSobresDetalle * 100).toFixed(1) : "0";
              return (
                <tr key={d.id} className="text-gray-700">
                  <td className="py-1 pr-4 font-mono">{d.numero_orden ?? `#${d.orden_id}`}</td>
                  <td className="py-1 pr-4">{d.cliente_nombre ?? "—"}</td>
                  <td className="py-1 pr-4 text-right">{d.cantidad_sobres}</td>
                  <td className="py-1 pr-4 text-right text-gray-500">{pct}%</td>
                  <td className="py-1 pr-4 text-right font-medium">
                    <CurrencyCell value={d.costo_asignado} />
                  </td>
                  <td className="py-1">
                    <button onClick={() => handleRemove(d.id)} disabled={removing === d.id}
                      className="text-gray-300 hover:text-red-500 disabled:opacity-40">
                      <X size={13} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="text-xs text-gray-400 mb-3">Sin órdenes asignadas</p>
      )}

      {/* Agregar orden */}
      <div className="flex items-center gap-2 mt-1">
        <select value={addOrdenId} onChange={(e) => setAddOrdenId(e.target.value ? +e.target.value : "")}
          className="border border-gray-300 rounded px-2 py-1 text-xs flex-1">
          <option value="">— Agregar orden —</option>
          {disponibles.map((o) => (
            <option key={o.id} value={o.id}>
              {o.numero_orden} · {o.cliente.nombre_empresa}
            </option>
          ))}
        </select>
        <input type="number" min={1} value={addSobres} onChange={(e) => setAddSobres(+e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 text-xs w-20 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
          placeholder="Sobres" />
        <button onClick={handleAdd} disabled={!addOrdenId || saving}
          className="bg-blue-600 text-white rounded px-3 py-1 text-xs hover:bg-blue-700 disabled:opacity-40">
          {saving ? "..." : "Agregar"}
        </button>
      </div>
    </div>
  );
}

// ── Formulario nueva factura ──────────────────────────────────────────────────

interface LineaOrden { orden: Orden; cantidad_sobres: number }

function FacturaTransporteForm({ onClose, onSaved }: { onClose: () => void; onSaved: (f: FacturaTransporte) => void }) {
  const { data: personal = [] } = useQuery({
    queryKey: ["personal-courier"],
    queryFn: () => personalApi.list({ activo: true }).then((r) =>
      r.data.filter((p) => ["courier_externo","transportadora"].includes(p.tipo_personal))
    ),
  });
  const { data: ordenesDisp = [] } = useQuery({
    queryKey: ["ordenes-activas-form"],
    queryFn: () => ordenesApi.list({ estado: "activa", limit: 500 }).then((r) => r.data),
  });

  const [form, setForm] = useState({
    numero_factura: "", courrier_id: 0, fecha_factura: HOY_STR,
    monto_total: 0, fecha_vencimiento: "", observaciones: "",
  });
  const [lineas, setLineas] = useState<LineaOrden[]>([]);
  const [selOrdenId, setSelOrdenId] = useState<number | "">("");
  const [selSobres, setSelSobres] = useState(1);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const totalSobres = lineas.reduce((s, l) => s + l.cantidad_sobres, 0);
  const asignadasIds = new Set(lineas.map((l) => l.orden.id));
  const disponibles = ordenesDisp.filter((o) => !asignadasIds.has(o.id));

  function agregarLinea() {
    if (!selOrdenId) return;
    const orden = ordenesDisp.find((o) => o.id === selOrdenId);
    if (!orden) return;
    setLineas((prev) => [...prev, { orden, cantidad_sobres: selSobres }]);
    setSelOrdenId("");
    setSelSobres(1);
  }

  function quitarLinea(idx: number) {
    setLineas((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      const res = await transpApi.create({
        ...form,
        total_sobres: totalSobres,
        fecha_vencimiento: form.fecha_vencimiento || null,
        observaciones: form.observaciones || null,
      });
      let facturaFinal: FacturaTransporte = res.data;
      const facturaId = facturaFinal.id;
      const errores: string[] = [];
      for (const linea of lineas) {
        try {
          const det = await transpApi.addDetalle(facturaId, {
            orden_id: linea.orden.id,
            cantidad_sobres: linea.cantidad_sobres,
          });
          facturaFinal = det.data;
        } catch (err: any) {
          errores.push(`${linea.orden.numero_orden}: ${err?.response?.data?.detail ?? "error"}`);
        }
      }
      if (errores.length) {
        onSaved(facturaFinal);
        setFormError(`Factura guardada. Errores en órdenes: ${errores.join("; ")}`);
      } else {
        onSaved(facturaFinal);
      }
    } catch (err: any) {
      setFormError(err?.response?.data?.detail ?? "Error al guardar la factura");
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex items-center justify-between shrink-0">
          <h2 className="text-base font-semibold">Registrar factura de transporte</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4 overflow-y-auto flex-1">

          {/* Cabecera */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">N° Factura *</label>
              <input required value={form.numero_factura} onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input type="date" required value={form.fecha_factura} onChange={(e) => setForm({ ...form, fecha_factura: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Courier / Transportadora *</label>
            <select required value={form.courrier_id || ""} onChange={(e) => setForm({ ...form, courrier_id: +e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option value="">— Seleccionar —</option>
              {personal.map((p) => <option key={p.id} value={p.id}>{p.codigo} — {p.nombre_completo}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Monto total *</label>
              <input type="number" required min={0} value={form.monto_total}
                onChange={(e) => setForm({ ...form, monto_total: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento</label>
              <input type="date" value={form.fecha_vencimiento} onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>

          {/* Detalle por orden */}
          <div className="border-t pt-4">
            <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-3">
              Detalle por orden
            </p>

            {/* Selector para agregar */}
            <div className="flex items-center gap-2 mb-3">
              <select value={selOrdenId} onChange={(e) => setSelOrdenId(e.target.value ? +e.target.value : "")}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm flex-1">
                <option value="">— Seleccionar orden —</option>
                {disponibles.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.numero_orden} · {o.cliente.nombre_empresa} ({o.cantidad_total} items)
                  </option>
                ))}
              </select>
              <input type="number" min={1} value={selSobres}
                onChange={(e) => setSelSobres(Math.max(1, +e.target.value))}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-24 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                placeholder="Sobres" />
              <button type="button" onClick={agregarLinea} disabled={!selOrdenId}
                className="bg-gray-800 text-white rounded-lg px-4 py-2 text-sm hover:bg-gray-700 disabled:opacity-40 whitespace-nowrap">
                + Agregar
              </button>
            </div>

            {/* Tabla preview */}
            {lineas.length > 0 && (
              <div className="rounded-lg border border-gray-200 overflow-hidden mb-3">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      {["Orden","Cliente","Sobres","%","Costo asignado",""].map((h) => (
                        <th key={h} className="text-left px-3 py-2 font-medium text-gray-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {lineas.map((l, idx) => {
                      const pct = totalSobres > 0 ? (l.cantidad_sobres / totalSobres * 100) : 0;
                      const costo = totalSobres > 0 ? (form.monto_total * l.cantidad_sobres / totalSobres) : 0;
                      return (
                        <tr key={idx} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono text-gray-700">{l.orden.numero_orden}</td>
                          <td className="px-3 py-2 text-gray-600">{l.orden.cliente.nombre_empresa}</td>
                          <td className="px-3 py-2 text-gray-600">{l.cantidad_sobres}</td>
                          <td className="px-3 py-2 text-gray-500">{pct.toFixed(1)}%</td>
                          <td className="px-3 py-2 font-medium text-gray-800">
                            ${fmt.format(costo)}
                          </td>
                          <td className="px-3 py-2">
                            <button type="button" onClick={() => quitarLinea(idx)}
                              className="text-gray-300 hover:text-red-500">
                              <X size={13} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot className="bg-gray-50 border-t border-gray-200">
                    <tr>
                      <td colSpan={2} className="px-3 py-2 text-xs font-medium text-gray-600">
                        {lineas.length} orden{lineas.length !== 1 ? "es" : ""}
                      </td>
                      <td className="px-3 py-2 font-medium text-gray-700">{totalSobres}</td>
                      <td className="px-3 py-2 text-gray-500">100%</td>
                      <td className="px-3 py-2 font-semibold text-gray-800">${fmt.format(form.monto_total)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
            <textarea rows={2} value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
          </div>

          {formError && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{formError}</p>
          )}

          <div className="flex justify-end gap-3 pt-2 border-t">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : `Guardar factura${lineas.length > 0 ? ` (${lineas.length} órdenes)` : ""}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal editar factura ──────────────────────────────────────────────────────

function EditFacturaModal({
  factura, ordenes, onClose, onSaved, onDetalleChanged,
}: {
  factura: FacturaTransporte;
  ordenes: Orden[];
  onClose: () => void;
  onSaved: (updated: FacturaTransporte) => void;
  onDetalleChanged: (updated: FacturaTransporte) => void;
}) {
  const { data: personal = [] } = useQuery({
    queryKey: ["personal-courier"],
    queryFn: () => personalApi.list({ activo: true }).then((r) =>
      r.data.filter((p) => ["courier_externo","transportadora"].includes(p.tipo_personal))
    ),
  });
  const [form, setForm] = useState({
    numero_factura: factura.numero_factura,
    fecha_factura: factura.fecha_factura,
    courrier_id: factura.courrier_id,
    monto_total: factura.monto_total,
    total_sobres: factura.total_sobres,
    fecha_vencimiento: factura.fecha_vencimiento ?? "",
    estado: factura.estado,
    monto_pagado: factura.monto_pagado,
    observaciones: factura.observaciones ?? "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await transpApi.update(factura.id, {
        ...form,
        fecha_vencimiento: form.fecha_vencimiento || null,
        observaciones: form.observaciones || null,
      });
      onSaved(res.data);
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex items-center justify-between shrink-0">
          <h2 className="text-base font-semibold">Editar factura — {factura.numero_factura}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <div className="overflow-y-auto flex-1">
          <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">N° Factura *</label>
                <input required value={form.numero_factura} onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Fecha factura *</label>
                <input type="date" required value={form.fecha_factura} onChange={(e) => setForm({ ...form, fecha_factura: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Courier *</label>
              <select required value={form.courrier_id} onChange={(e) => setForm({ ...form, courrier_id: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {personal.map((p) => <option key={p.id} value={p.id}>{p.codigo} — {p.nombre_completo}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Monto total *</label>
                <input type="number" required min={0} value={form.monto_total}
                  onChange={(e) => setForm({ ...form, monto_total: +e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Total sobres</label>
                <input type="number" min={0} value={form.total_sobres}
                  onChange={(e) => setForm({ ...form, total_sobres: +e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Monto pagado</label>
                <input type="number" min={0} value={form.monto_pagado}
                  onChange={(e) => setForm({ ...form, monto_pagado: +e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento</label>
                <input type="date" value={form.fecha_vencimiento} onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Estado</label>
                <select value={form.estado} onChange={(e) => setForm({ ...form, estado: e.target.value })}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                  {["pendiente","pagada","anulada"].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
              <textarea rows={2} value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
            <div className="flex justify-end gap-3 pt-2 border-t">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
              <button type="submit" disabled={saving}
                className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
                {saving ? "Guardando..." : "Guardar cambios"}
              </button>
            </div>
          </form>

          {/* Órdenes asignadas */}
          <div className="px-6 pb-6 border-t pt-4">
            <DetallePanel
              factura={factura}
              ordenes={ordenes}
              onUpdated={(updated) => {
                onDetalleChanged(updated);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Modal pagar ───────────────────────────────────────────────────────────────

function PagarTransporteModal({
  factura, onClose, onSaved,
}: {
  factura: FacturaTransporte; onClose: () => void; onSaved: () => void;
}) {
  const saldo = factura.monto_total - factura.monto_pagado;
  const [form, setForm] = useState({ monto_pago: saldo, referencia: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await transpApi.pagar(factura.id, {
        ...form,
        referencia: form.referencia || null,
        observaciones: form.observaciones || null,
      });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Registrar pago</h2>
            <p className="text-xs text-gray-500 mt-0.5">{factura.numero_factura} · Saldo: ${fmt.format(saldo)}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Monto *</label>
            <input type="number" required min={1} value={form.monto_pago}
              onChange={(e) => setForm({ ...form, monto_pago: +e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Referencia</label>
            <input value={form.referencia} onChange={(e) => setForm({ ...form, referencia: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Registrar pago"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
