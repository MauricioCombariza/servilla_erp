import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, DollarSign, Pencil } from "lucide-react";
import { facturacionApi } from "@/api/facturacion";
import { personalApi } from "@/api/personal";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { FacturaRecibida } from "@/api/facturacion";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const ESTADO_STYLE: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  parcial:   "bg-blue-50 text-blue-700",
  pagada:    "bg-green-50 text-green-700",
  anulada:   "bg-gray-100 text-gray-400",
};
const TIPOS = ["courier", "transportadora", "materiales", "otros"];
const METODOS = ["efectivo", "transferencia", "cheque", "tarjeta", "otros"];

export function FacturasRecibidasPage() {
  const qc = useQueryClient();
  const [tipoFiltro, setTipoFiltro] = useState("");
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [showPago, setShowPago] = useState<FacturaRecibida | null>(null);

  const params: Record<string, string> = {};
  if (tipoFiltro) params.tipo = tipoFiltro;
  if (estadoFiltro) params.estado = estadoFiltro;

  const { data: facturas = [], isLoading } = useQuery({
    queryKey: ["facturas-recibidas", tipoFiltro, estadoFiltro],
    queryFn: () => facturacionApi.listRecibidas(params).then((r) => r.data),
  });

  const totalPendiente = facturas
    .filter((f) => !["pagada", "anulada"].includes(f.estado))
    .reduce((s, f) => s + f.saldo_pendiente, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Facturas Recibidas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Saldo pendiente: <span className="font-medium text-red-600">${fmt.format(totalPendiente)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={tipoFiltro} onChange={(e) => setTipoFiltro(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
            <option value="">Todos los tipos</option>
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={estadoFiltro} onChange={(e) => setEstadoFiltro(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
            <option value="">Todos los estados</option>
            {["pendiente","parcial","pagada","anulada"].map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <button onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium">
            <Plus size={16} /> Nueva factura
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : facturas.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin facturas recibidas</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["N° Factura","Proveedor","Tipo","Fecha recep.","Vencimiento","Total","Pagado","Saldo","Estado",""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {facturas.map((f) => (
                <tr key={f.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{f.numero_factura}</td>
                  <td className="px-4 py-3 text-gray-900">{f.personal?.nombre_completo ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-xs">{f.tipo}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{f.fecha_recepcion}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{f.fecha_vencimiento}</td>
                  <td className="px-4 py-3 font-medium"><CurrencyCell value={f.total} /></td>
                  <td className="px-4 py-3 text-green-700"><CurrencyCell value={f.total - f.saldo_pendiente} /></td>
                  <td className="px-4 py-3 text-red-600 font-medium"><CurrencyCell value={f.saldo_pendiente} /></td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_STYLE[f.estado] ?? ""}`}>{f.estado}</span>
                  </td>
                  <td className="px-4 py-3">
                    {f.estado !== "pagada" && f.estado !== "anulada" && (
                      <button onClick={() => setShowPago(f)}
                        className="text-gray-400 hover:text-green-600" title="Registrar pago">
                        <DollarSign size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <FacturaRecibidaForm
          onClose={() => setShowForm(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["facturas-recibidas"] }); setShowForm(false); }}
        />
      )}
      {showPago && (
        <PagoRealizadoModal
          factura={showPago}
          onClose={() => setShowPago(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["facturas-recibidas"] }); setShowPago(null); }}
        />
      )}
    </div>
  );
}

// ── Formulario nueva factura recibida ─────────────────────────────────────────

function FacturaRecibidaForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const HOY = new Date().toISOString().slice(0, 10);
  const { data: personal = [] } = useQuery({
    queryKey: ["personal-activo"],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
  });
  const [form, setForm] = useState<{
    numero_factura: string; personal_id: number;
    tipo: "courier" | "transportadora" | "materiales" | "otros";
    fecha_recepcion: string; fecha_vencimiento: string;
    subtotal: number; descuento: number; total: number; saldo_pendiente: number;
    observaciones: string;
  }>({
    numero_factura: "", personal_id: 0, tipo: "courier",
    fecha_recepcion: HOY, fecha_vencimiento: HOY,
    subtotal: 0, descuento: 0, total: 0, saldo_pendiente: 0,
    observaciones: "",
  });
  const [saving, setSaving] = useState(false);

  function calcTotal() {
    const t = form.subtotal - form.descuento;
    setForm((f) => ({ ...f, total: t, saldo_pendiente: t }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await facturacionApi.createRecibida({ ...form, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b"><h2 className="text-base font-semibold">Nueva factura recibida</h2></div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">N° Factura *</label>
              <input required value={form.numero_factura}
                onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tipo *</label>
              <select required value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value as typeof form.tipo })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Proveedor *</label>
            <select required value={form.personal_id || ""} onChange={(e) => setForm({ ...form, personal_id: +e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option value="">— Seleccionar —</option>
              {personal.map((p) => <option key={p.id} value={p.id}>{p.codigo} — {p.nombre_completo}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha recepción *</label>
              <input type="date" required value={form.fecha_recepcion}
                onChange={(e) => setForm({ ...form, fecha_recepcion: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento *</label>
              <input type="date" required value={form.fecha_vencimiento}
                onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Subtotal *</label>
              <input type="number" required min={0} value={form.subtotal}
                onChange={(e) => setForm({ ...form, subtotal: +e.target.value })}
                onBlur={calcTotal}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Descuento</label>
              <input type="number" min={0} value={form.descuento}
                onChange={(e) => setForm({ ...form, descuento: +e.target.value })}
                onBlur={calcTotal}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <p className="text-sm text-gray-600">Total calculado: <strong>${fmt.format(form.total)}</strong></p>
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

// ── Modal pago recibida ───────────────────────────────────────────────────────

function PagoRealizadoModal({ factura, onClose, onSaved }: {
  factura: FacturaRecibida; onClose: () => void; onSaved: () => void;
}) {
  const HOY = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ fecha_pago: HOY, monto: factura.saldo_pendiente, metodo_pago: "transferencia", referencia: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await facturacionApi.registrarPagoRecibida(factura.id, { ...form, referencia: form.referencia || null, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Registrar pago</h2>
          <p className="text-xs text-gray-500 mt-0.5">{factura.numero_factura} · Saldo: ${fmt.format(factura.saldo_pendiente)}</p>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input type="date" required value={form.fecha_pago}
                onChange={(e) => setForm({ ...form, fecha_pago: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Monto *</label>
              <input type="number" required min={1} value={form.monto}
                onChange={(e) => setForm({ ...form, monto: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Método *</label>
            <select required value={form.metodo_pago}
              onChange={(e) => setForm({ ...form, metodo_pago: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              {METODOS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
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
