import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, CheckCircle } from "lucide-react";
import { gastosApi } from "@/api/gastos";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { Badge } from "@/components/ui/Badge";
import type { GastoAdmin, GastoFijo } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const CATEGORIAS = [
  "mantenimiento","polizas","servicios_publicos","caja_menor","papeleria",
  "aseo","internet","software","alquiler_equipos","arriendo","honorarios",
  "impuestos","otros",
];

type Tab = "gastos" | "fijos";

export function GastosPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("gastos");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<GastoAdmin | null>(null);

  const { data: gastos = [], isLoading } = useQuery({
    queryKey: ["gastos", mes, anio],
    queryFn: () => gastosApi.list({ mes, anio }).then((r) => r.data),
  });

  const { data: resumen = [] } = useQuery({
    queryKey: ["gastos-resumen", mes, anio],
    queryFn: () => gastosApi.resumen({ mes, anio }).then((r) => r.data),
  });

  const { data: fijos = [] } = useQuery({
    queryKey: ["gastos-fijos"],
    queryFn: () => gastosApi.listFijos().then((r) => r.data),
    enabled: tab === "fijos",
  });

  const marcarPagado = useMutation({
    mutationFn: (g: GastoAdmin) =>
      gastosApi.update(g.id, { estado: "pagado", fecha_pago: new Date().toISOString().slice(0, 10) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos"] }),
  });

  const deleteGasto = useMutation({
    mutationFn: (id: number) => gastosApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos"] }),
  });

  const totalMes = gastos.reduce((s, g) => s + g.monto, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Gastos Administrativos</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Total {MESES[mes - 1]} {anio}: <span className="font-medium text-gray-800">${fmt.format(totalMes)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={mes}
            onChange={(e) => setMes(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
          >
            {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <input
            type="number"
            value={anio}
            onChange={(e) => setAnio(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20"
          />
          <button
            onClick={() => { setEditing(null); setShowForm(true); }}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} /> Nuevo gasto
          </button>
        </div>
      </div>

      {/* Resumen por categoría */}
      {resumen.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          {resumen.slice(0, 4).map((r) => (
            <div key={r.categoria} className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-xs text-gray-500 uppercase tracking-wide">{r.categoria.replace(/_/g, " ")}</p>
              <p className="text-lg font-semibold text-gray-900 mt-1">${fmt.format(r.total)}</p>
              <p className="text-xs text-gray-400">{r.cantidad} registros</p>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        {(["gastos", "fijos"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "gastos" ? "Gastos del mes" : "Gastos fijos"}
          </button>
        ))}
      </div>

      {tab === "gastos" && (
        <>
          {isLoading ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : gastos.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin gastos en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Categoría", "Descripción", "Proveedor", "Monto", "Estado", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {gastos.map((g) => (
                    <tr key={g.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-600 font-mono text-xs">{g.fecha}</td>
                      <td className="px-4 py-3">
                        <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-xs">
                          {g.categoria.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900">{g.descripcion}</td>
                      <td className="px-4 py-3 text-gray-600">{g.proveedor ?? "—"}</td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <CurrencyCell value={g.monto} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          g.estado === "pagado" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"
                        }`}>
                          {g.estado}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {g.estado === "pendiente" && (
                            <button
                              onClick={() => marcarPagado.mutate(g)}
                              className="text-gray-400 hover:text-green-600 transition-colors"
                              title="Marcar pagado"
                            >
                              <CheckCircle size={15} />
                            </button>
                          )}
                          <button
                            onClick={() => { setEditing(g); setShowForm(true); }}
                            className="text-gray-400 hover:text-primary transition-colors"
                            title="Editar"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            onClick={() => { if (confirm("¿Eliminar este gasto?")) deleteGasto.mutate(g.id); }}
                            className="text-gray-400 hover:text-red-500 transition-colors"
                            title="Eliminar"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50 border-t border-gray-200">
                  <tr>
                    <td colSpan={4} className="px-4 py-3 text-sm font-medium text-gray-700">Total</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">
                      <CurrencyCell value={totalMes} />
                    </td>
                    <td colSpan={2} />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "fijos" && <GastosFijosTab fijos={fijos} />}

      {showForm && (
        <GastoForm
          initial={editing}
          defaultFecha={`${anio}-${String(mes).padStart(2, "0")}-01`}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["gastos"] });
            qc.invalidateQueries({ queryKey: ["gastos-resumen"] });
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// ── Subcomponente: Gastos Fijos ───────────────────────────────────────────────

function GastosFijosTab({ fijos }: { fijos: GastoFijo[] }) {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<GastoFijo | null>(null);

  const toggleActivo = useMutation({
    mutationFn: (f: GastoFijo) => gastosApi.updateFijo(f.id, { activo: !f.activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gastos-fijos"] }),
  });

  if (fijos.length === 0)
    return <div className="text-center py-16 text-gray-400">Sin gastos fijos configurados</div>;

  return (
    <>
      <div className="flex justify-end mb-3">
        <button
          onClick={() => { setEditing(null); setShowForm(true); }}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> Nuevo fijo
        </button>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Categoría", "Descripción", "Monto mensual", "Día pago", "Estado", ""].map((h) => (
                <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {fijos.map((f) => (
              <tr key={f.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-xs">
                    {f.categoria.replace(/_/g, " ")}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-900">{f.descripcion}</td>
                <td className="px-4 py-3 font-medium text-gray-900"><CurrencyCell value={f.monto} /></td>
                <td className="px-4 py-3 text-gray-600">Día {f.dia_pago}</td>
                <td className="px-4 py-3">
                  <button onClick={() => toggleActivo.mutate(f)}>
                    <Badge active={f.activo} />
                  </button>
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => { setEditing(f); setShowForm(true); }}
                    className="text-gray-400 hover:text-primary transition-colors"
                  >
                    <Pencil size={15} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showForm && (
        <GastoFijoForm
          initial={editing}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["gastos-fijos"] });
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

// ── Formulario Gasto Admin ────────────────────────────────────────────────────

function GastoForm({
  initial,
  defaultFecha,
  onClose,
  onSaved,
}: {
  initial: GastoAdmin | null;
  defaultFecha: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    fecha: initial?.fecha ?? defaultFecha,
    categoria: initial?.categoria ?? "otros",
    descripcion: initial?.descripcion ?? "",
    monto: initial?.monto ?? 0,
    proveedor: initial?.proveedor ?? "",
    numero_factura: initial?.numero_factura ?? "",
    observaciones: initial?.observaciones ?? "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        proveedor: form.proveedor || null,
        numero_factura: form.numero_factura || null,
        observaciones: form.observaciones || null,
      };
      if (initial) {
        await gastosApi.update(initial.id, payload);
      } else {
        await gastosApi.create({ ...payload, estado: "pendiente", fecha_pago: null });
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">
            {initial ? "Editar gasto" : "Nuevo gasto"}
          </h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input
                type="date"
                required
                value={form.fecha}
                onChange={(e) => setForm({ ...form, fecha: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Categoría *</label>
              <select
                required
                value={form.categoria}
                onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                {CATEGORIAS.map((c) => (
                  <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Descripción *</label>
            <input
              required
              value={form.descripcion}
              onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              placeholder="Descripción del gasto"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Monto *</label>
              <input
                type="number"
                required
                min={0}
                value={form.monto}
                onChange={(e) => setForm({ ...form, monto: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Proveedor</label>
              <input
                value={form.proveedor}
                onChange={(e) => setForm({ ...form, proveedor: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">N° Factura</label>
            <input
              value={form.numero_factura}
              onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60"
            >
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Formulario Gasto Fijo ─────────────────────────────────────────────────────

function GastoFijoForm({
  initial,
  onClose,
  onSaved,
}: {
  initial: GastoFijo | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    categoria: initial?.categoria ?? "otros",
    descripcion: initial?.descripcion ?? "",
    monto: initial?.monto ?? 0,
    dia_pago: initial?.dia_pago ?? 1,
    observaciones: initial?.observaciones ?? "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...form, observaciones: form.observaciones || null };
      if (initial) {
        await gastosApi.updateFijo(initial.id, payload);
      } else {
        await gastosApi.createFijo(payload);
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">
            {initial ? "Editar gasto fijo" : "Nuevo gasto fijo"}
          </h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Categoría *</label>
            <select
              required
              value={form.categoria}
              onChange={(e) => setForm({ ...form, categoria: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            >
              {CATEGORIAS.map((c) => (
                <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Descripción *</label>
            <input
              required
              value={form.descripcion}
              onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Monto mensual *</label>
              <input
                type="number"
                required
                min={0}
                value={form.monto}
                onChange={(e) => setForm({ ...form, monto: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Día de pago</label>
              <input
                type="number"
                min={1}
                max={31}
                value={form.dia_pago}
                onChange={(e) => setForm({ ...form, dia_pago: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60"
            >
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
