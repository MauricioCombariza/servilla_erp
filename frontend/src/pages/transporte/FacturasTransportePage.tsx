import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, DollarSign, Trash2 } from "lucide-react";
import api from "@/api/client";
import { personalApi } from "@/api/personal";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();

interface PrefacturaCourier {
  cod_mensajero: string; mensajero_id: number | null; nombre_completo: string | null;
  periodo_mes: number; periodo_anio: number; total_planillas: number;
  total_local: number; total_nacional: number; total_seriales: number;
  precio_local_promedio: number; precio_nacional_promedio: number; monto_estimado: number;
}

interface FacturaTransporte {
  id: number; numero_factura: string; fecha_factura: string;
  courrier_id: number; courrier: { id: number; codigo: string; nombre_completo: string };
  monto_total: number; total_sobres: number; monto_pagado: number;
  estado: string; fecha_vencimiento: string | null; observaciones: string | null;
  fecha_creacion: string | null; detalles: unknown[];
}

const transpApi = {
  prefacturas: (mes: number, anio: number) =>
    api.get<PrefacturaCourier[]>("/transporte/prefacturas", { params: { mes, anio } }),
  list: (params: object) => api.get<FacturaTransporte[]>("/transporte/", { params }),
  create: (data: object) => api.post<FacturaTransporte>("/transporte/", data),
  pagar: (id: number, data: object) => api.post<FacturaTransporte>(`/transporte/${id}/pagar`, data),
  delete: (id: number) => api.delete(`/transporte/${id}`),
};

const ESTADO_STYLE: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  pagada:    "bg-green-50 text-green-700",
  anulada:   "bg-gray-100 text-gray-400",
};

type Tab = "prefacturas" | "facturas";

export function FacturasTransportePage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("prefacturas");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showForm, setShowForm] = useState(false);
  const [pagando, setPagando] = useState<FacturaTransporte | null>(null);

  const { data: prefacturas = [], isLoading: loadPre } = useQuery({
    queryKey: ["prefacturas", mes, anio],
    queryFn: () => transpApi.prefacturas(mes, anio).then((r) => r.data),
    enabled: tab === "prefacturas",
  });

  const { data: facturas = [], isLoading: loadFact } = useQuery({
    queryKey: ["facturas-transporte"],
    queryFn: () => transpApi.list({}).then((r) => r.data),
    enabled: tab === "facturas",
  });

  const eliminar = useMutation({
    mutationFn: (id: number) => transpApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facturas-transporte"] }),
  });

  const totalPrefacturas = prefacturas.reduce((s, p) => s + p.monto_estimado, 0);
  const totalPendienteFact = facturas.filter((f) => f.estado !== "pagada").reduce((s, f) => s + (f.monto_total - f.monto_pagado), 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Facturas Transporte / Couriers</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {tab === "prefacturas"
              ? `${MESES[mes-1]} ${anio} · Estimado: $${fmt.format(totalPrefacturas)}`
              : `Saldo pendiente: $${fmt.format(totalPendienteFact)}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tab === "prefacturas" && (
            <>
              <select value={mes} onChange={(e) => setMes(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
                {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
              </select>
              <input type="number" value={anio} onChange={(e) => setAnio(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20" />
            </>
          )}
          {tab === "facturas" && (
            <button onClick={() => setShowForm(true)}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium">
              <Plus size={16} /> Registrar factura
            </button>
          )}
        </div>
      </div>

      <div className="flex border-b border-gray-200 mb-4">
        {(["prefacturas","facturas"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t === "prefacturas" ? "Resumen por courier (prefacturas)" : "Facturas registradas"}
          </button>
        ))}
      </div>

      {tab === "prefacturas" && (
        <>
          {loadPre ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : prefacturas.length === 0 ? <div className="text-center py-16 text-gray-400">Sin gestiones de couriers en este período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Courier","Planillas","Local","Nacional","Total seriales","P. local prom.","P. nac. prom.","Monto estimado"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {prefacturas.map((p) => (
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
                    <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={totalPrefacturas} /></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "facturas" && (
        <>
          {loadFact ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : facturas.length === 0 ? <div className="text-center py-16 text-gray-400">Sin facturas registradas</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["N° Factura","Courier","Fecha","Vencimiento","Sobres","Total","Pagado","Estado",""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {facturas.map((f) => (
                    <tr key={f.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{f.numero_factura}</td>
                      <td className="px-4 py-3 text-gray-900">{f.courrier?.nombre_completo ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-600 text-xs">{f.fecha_factura}</td>
                      <td className="px-4 py-3 text-gray-600 text-xs">{f.fecha_vencimiento ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-600">{f.total_sobres}</td>
                      <td className="px-4 py-3 font-medium"><CurrencyCell value={f.monto_total} /></td>
                      <td className="px-4 py-3 text-green-700"><CurrencyCell value={f.monto_pagado} /></td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_STYLE[f.estado] ?? ""}`}>{f.estado}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {f.estado !== "pagada" && (
                            <button onClick={() => setPagando(f)}
                              className="text-gray-400 hover:text-green-600" title="Registrar pago">
                              <DollarSign size={15} />
                            </button>
                          )}
                          {f.estado !== "pagada" && (
                            <button onClick={() => { if (confirm("¿Eliminar factura?")) eliminar.mutate(f.id); }}
                              className="text-gray-400 hover:text-red-500">
                              <Trash2 size={15} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {showForm && <FacturaTransporteForm onClose={() => setShowForm(false)} onSaved={() => { qc.invalidateQueries({ queryKey: ["facturas-transporte"] }); setShowForm(false); }} />}
      {pagando && <PagarTransporteModal factura={pagando} onClose={() => setPagando(null)} onSaved={() => { qc.invalidateQueries({ queryKey: ["facturas-transporte"] }); setPagando(null); }} />}
    </div>
  );
}

// ── Formulario nueva factura ───────────────────────────────────────────────────

function FacturaTransporteForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const HOY_STR = new Date().toISOString().slice(0, 10);
  const { data: personal = [] } = useQuery({
    queryKey: ["personal-courier"],
    queryFn: () => personalApi.list({ activo: true }).then((r) =>
      r.data.filter((p) => ["courier_externo","transportadora"].includes(p.tipo_personal))
    ),
  });
  const [form, setForm] = useState({ numero_factura: "", courrier_id: 0, fecha_factura: HOY_STR, monto_total: 0, total_sobres: 0, fecha_vencimiento: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await transpApi.create({ ...form, fecha_vencimiento: form.fecha_vencimiento || null, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b"><h2 className="text-base font-semibold">Registrar factura de transporte</h2></div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
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
              <label className="block text-xs font-medium text-gray-700 mb-1">Total sobres</label>
              <input type="number" min={0} value={form.total_sobres}
                onChange={(e) => setForm({ ...form, total_sobres: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento</label>
            <input type="date" value={form.fecha_vencimiento} onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal pagar factura transporte ────────────────────────────────────────────

function PagarTransporteModal({ factura, onClose, onSaved }: {
  factura: FacturaTransporte; onClose: () => void; onSaved: () => void;
}) {
  const saldo = factura.monto_total - factura.monto_pagado;
  const [form, setForm] = useState({ monto_pago: saldo, referencia: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await transpApi.pagar(factura.id, { ...form, referencia: form.referencia || null, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Registrar pago</h2>
          <p className="text-xs text-gray-500 mt-0.5">{factura.numero_factura} · Saldo: ${fmt.format(saldo)}</p>
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
