import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, DollarSign, Trash2, Plus } from "lucide-react";
import api from "@/api/client";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const METODOS = ["efectivo","transferencia","cheque","tarjeta","otros"];

type Tab = "pendientes" | "liquidaciones";

interface Pendiente {
  personal_id: number; codigo: string; nombre_completo: string; tipo_personal: string;
  total_seriales: number; total_mensajero: number; total_horas: number; total_horas_monto: number;
  total_labores: number; total_labores_monto: number; total_pendiente: number; ya_liquidado: boolean;
}
interface Liquidacion {
  id: number; numero_liquidacion: string; personal_id: number;
  periodo_mes: number; periodo_anio: number; fecha_generacion: string;
  fecha_pago_programada: string; total_entregas: number; cantidad_entregas: number;
  total_horas: number; total_labores: number; bonificaciones: number; descuentos: number;
  total_a_pagar: number; estado: string; fecha_pago_real: string | null;
  metodo_pago: string; referencia_pago: string | null; observaciones: string | null;
}

const liqApi = {
  pendientes: (mes: number, anio: number) =>
    api.get<Pendiente[]>("/liquidaciones/pendientes", { params: { mes, anio } }),
  list: (params: object) => api.get<Liquidacion[]>("/liquidaciones/", { params }),
  generar: (data: object) => api.post<Liquidacion>("/liquidaciones/generar", data),
  aprobar: (id: number) => api.post<Liquidacion>(`/liquidaciones/${id}/aprobar`),
  pagar: (id: number, data: object) => api.post<Liquidacion>(`/liquidaciones/${id}/pagar`, data),
  delete: (id: number) => api.delete(`/liquidaciones/${id}`),
};

const ESTADO_STYLE: Record<string, string> = {
  generada:  "bg-yellow-50 text-yellow-700",
  aprobada:  "bg-blue-50 text-blue-700",
  pagada:    "bg-green-50 text-green-700",
};

export function LiquidacionesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("pendientes");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [generando, setGenerando] = useState<Pendiente | null>(null);
  const [pagando, setPagando] = useState<Liquidacion | null>(null);

  const { data: pendientes = [], isLoading: loadPend } = useQuery({
    queryKey: ["liq-pendientes", mes, anio],
    queryFn: () => liqApi.pendientes(mes, anio).then((r) => r.data),
    enabled: tab === "pendientes",
  });

  const { data: liquidaciones = [], isLoading: loadLiq } = useQuery({
    queryKey: ["liquidaciones", mes, anio],
    queryFn: () => liqApi.list({ mes, anio }).then((r) => r.data),
    enabled: tab === "liquidaciones",
  });

  const aprobar = useMutation({
    mutationFn: (id: number) => liqApi.aprobar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["liquidaciones"] }),
  });
  const eliminar = useMutation({
    mutationFn: (id: number) => liqApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["liquidaciones"] });
      qc.invalidateQueries({ queryKey: ["liq-pendientes"] });
    },
  });

  const totalPendiente = pendientes.filter((p) => !p.ya_liquidado).reduce((s, p) => s + p.total_pendiente, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Gestión de Pagos — Mensajeros</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {MESES[mes - 1]} {anio}
            {tab === "pendientes" && ` · Pendiente total: `}
            {tab === "pendientes" && <span className="font-medium text-gray-800">${fmt.format(totalPendiente)}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={mes} onChange={(e) => setMes(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
            {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <input type="number" value={anio} onChange={(e) => setAnio(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20" />
        </div>
      </div>

      <div className="flex border-b border-gray-200 mb-4">
        {(["pendientes", "liquidaciones"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t === "pendientes" ? "Pendientes de liquidar" : "Liquidaciones generadas"}
          </button>
        ))}
      </div>

      {tab === "pendientes" && (
        <>
          {loadPend ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : pendientes.length === 0 ? <div className="text-center py-16 text-gray-400">Sin seriales pendientes en este período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Mensajero","Seriales","Monto seriales","Horas","Labores","Total","Estado",""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pendientes.map((p) => (
                    <tr key={p.personal_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">{p.nombre_completo}</p>
                        <p className="text-xs text-gray-400">{p.codigo}</p>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{p.total_seriales}</td>
                      <td className="px-4 py-3 text-gray-700"><CurrencyCell value={p.total_mensajero} /></td>
                      <td className="px-4 py-3 text-gray-600">{fmt.format(p.total_horas)}h · <CurrencyCell value={p.total_horas_monto} /></td>
                      <td className="px-4 py-3 text-gray-600">{p.total_labores} · <CurrencyCell value={p.total_labores_monto} /></td>
                      <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={p.total_pendiente} /></td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${p.ya_liquidado ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                          {p.ya_liquidado ? "Liquidado" : "Pendiente"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {!p.ya_liquidado && (
                          <button onClick={() => setGenerando(p)}
                            className="flex items-center gap-1 text-xs bg-primary hover:bg-primary-hover text-white px-2 py-1 rounded">
                            <Plus size={12} /> Generar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "liquidaciones" && (
        <>
          {loadLiq ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : liquidaciones.length === 0 ? <div className="text-center py-16 text-gray-400">Sin liquidaciones en este período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["N° Liquidación","Período","Entregas","Horas","Bonif./Desc.","Total","Estado","Pago prog.",""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {liquidaciones.map((l) => (
                    <tr key={l.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{l.numero_liquidacion}</td>
                      <td className="px-4 py-3 text-gray-600">{MESES[l.periodo_mes - 1]} {l.periodo_anio}</td>
                      <td className="px-4 py-3 text-gray-600">{l.cantidad_entregas} · <CurrencyCell value={l.total_entregas} /></td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={l.total_horas} /></td>
                      <td className="px-4 py-3 text-gray-600">+<CurrencyCell value={l.bonificaciones} /> -<CurrencyCell value={l.descuentos} /></td>
                      <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={l.total_a_pagar} /></td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_STYLE[l.estado] ?? ""}`}>{l.estado}</span>
                      </td>
                      <td className="px-4 py-3 text-gray-600 text-xs">
                        {l.fecha_pago_real ?? l.fecha_pago_programada}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {l.estado === "generada" && (
                            <button onClick={() => aprobar.mutate(l.id)}
                              className="text-gray-400 hover:text-blue-600" title="Aprobar">
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {l.estado !== "pagada" && (
                            <button onClick={() => setPagando(l)}
                              className="text-gray-400 hover:text-green-600" title="Pagar">
                              <DollarSign size={15} />
                            </button>
                          )}
                          {l.estado !== "pagada" && (
                            <button onClick={() => { if (confirm("¿Eliminar liquidación? Se revierten los seriales a pendiente.")) eliminar.mutate(l.id); }}
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

      {generando && (
        <GenerarLiquidacionModal
          pendiente={generando} mes={mes} anio={anio}
          onClose={() => setGenerando(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["liq-pendientes"] });
            qc.invalidateQueries({ queryKey: ["liquidaciones"] });
            setGenerando(null);
            setTab("liquidaciones");
          }}
        />
      )}
      {pagando && (
        <PagarLiquidacionModal
          liquidacion={pagando}
          onClose={() => setPagando(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["liquidaciones"] }); setPagando(null); }}
        />
      )}
    </div>
  );
}

// ── Modal generar liquidación ──────────────────────────────────────────────────

function GenerarLiquidacionModal({ pendiente, mes, anio, onClose, onSaved }: {
  pendiente: Pendiente; mes: number; anio: number; onClose: () => void; onSaved: () => void;
}) {
  const hoy = new Date();
  const diasPago = new Date(hoy.getFullYear(), hoy.getMonth(), 8).toISOString().slice(0, 10);
  const [form, setForm] = useState({ fecha_pago_programada: diasPago, bonificaciones: 0, descuentos: 0, observaciones: "" });
  const [saving, setSaving] = useState(false);
  const total = pendiente.total_pendiente + form.bonificaciones - form.descuentos;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await liqApi.generar({
        personal_id: pendiente.personal_id,
        periodo_mes: mes, periodo_anio: anio,
        ...form, observaciones: form.observaciones || null,
      });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Generar liquidación</h2>
          <p className="text-xs text-gray-500 mt-0.5">{pendiente.nombre_completo} · {MESES[mes - 1]} {anio}</p>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
            <div className="flex justify-between"><span className="text-gray-600">Seriales ({pendiente.total_seriales})</span><span className="font-medium">${fmt.format(pendiente.total_mensajero)}</span></div>
            <div className="flex justify-between"><span className="text-gray-600">Horas</span><span>${fmt.format(pendiente.total_horas_monto)}</span></div>
            <div className="flex justify-between"><span className="text-gray-600">Labores</span><span>${fmt.format(pendiente.total_labores_monto)}</span></div>
            <div className="flex justify-between border-t pt-1 mt-1 font-semibold"><span>Subtotal</span><span>${fmt.format(pendiente.total_pendiente)}</span></div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Bonificación</label>
              <input type="number" min={0} value={form.bonificaciones}
                onChange={(e) => setForm({ ...form, bonificaciones: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Descuento</label>
              <input type="number" min={0} value={form.descuentos}
                onChange={(e) => setForm({ ...form, descuentos: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha de pago programada *</label>
            <input type="date" required value={form.fecha_pago_programada}
              onChange={(e) => setForm({ ...form, fecha_pago_programada: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <p className="text-sm font-semibold text-gray-900">
            Total a pagar: <span className="text-primary">${fmt.format(total)}</span>
          </p>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Generando..." : "Generar liquidación"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal pagar liquidación ────────────────────────────────────────────────────

function PagarLiquidacionModal({ liquidacion, onClose, onSaved }: {
  liquidacion: Liquidacion; onClose: () => void; onSaved: () => void;
}) {
  const HOY = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ fecha_pago_real: HOY, metodo_pago: "transferencia", referencia_pago: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await liqApi.pagar(liquidacion.id, { ...form, referencia_pago: form.referencia_pago || null, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Registrar pago</h2>
          <p className="text-xs text-gray-500 mt-0.5">{liquidacion.numero_liquidacion} · Total: ${fmt.format(liquidacion.total_a_pagar)}</p>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha de pago *</label>
              <input type="date" required value={form.fecha_pago_real}
                onChange={(e) => setForm({ ...form, fecha_pago_real: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Método *</label>
              <select required value={form.metodo_pago}
                onChange={(e) => setForm({ ...form, metodo_pago: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {METODOS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Referencia</label>
            <input value={form.referencia_pago} onChange={(e) => setForm({ ...form, referencia_pago: e.target.value })}
              placeholder="N° transferencia, cheque, etc."
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
