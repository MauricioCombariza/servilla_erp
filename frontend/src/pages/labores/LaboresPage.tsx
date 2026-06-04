import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, CheckCircle, Trash2 } from "lucide-react";
import { laboresApi } from "@/api/labores";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { RegistroHoras, RegistroLabores } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const TIPOS_TRABAJO = ["alistamiento_sobres", "alistamiento_paquetes"];
const TIPOS_LABOR = ["pegado_guia", "transporte_completo", "medio_transporte"];

type Tab = "horas" | "labores" | "resumen";

export function LaboresPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("horas");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showHoraForm, setShowHoraForm] = useState(false);
  const [showLaborForm, setShowLaborForm] = useState(false);

  const filtros = { mes, anio };

  const { data: horas = [], isLoading: loadH } = useQuery({
    queryKey: ["labores-horas", mes, anio],
    queryFn: () => laboresApi.listHoras(filtros).then((r) => r.data),
    enabled: tab === "horas",
  });

  const { data: labores = [], isLoading: loadL } = useQuery({
    queryKey: ["labores-labores", mes, anio],
    queryFn: () => laboresApi.listLabores(filtros).then((r) => r.data),
    enabled: tab === "labores",
  });

  const { data: resumen = [] } = useQuery({
    queryKey: ["labores-resumen", mes, anio],
    queryFn: () => laboresApi.resumen(filtros).then((r) => r.data),
    enabled: tab === "resumen",
  });

  const aprobarHora = useMutation({
    mutationFn: (id: number) => laboresApi.aprobarHora(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-horas"] }),
  });
  const deleteHora = useMutation({
    mutationFn: (id: number) => laboresApi.deleteHora(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-horas"] }),
  });
  const aprobarLabor = useMutation({
    mutationFn: (id: number) => laboresApi.aprobarLabor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-labores"] }),
  });
  const deleteLabor = useMutation({
    mutationFn: (id: number) => laboresApi.deleteLabor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-labores"] }),
  });

  const totalHoras = horas.reduce((s, h) => s + h.horas_trabajadas, 0);
  const totalHorasMonto = horas.reduce((s, h) => s + (h.total ?? h.horas_trabajadas * h.tarifa_hora), 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Registro de Labores</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {MESES[mes - 1]} {anio} · {horas.length} horas · {labores.length} labores
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
          {tab === "horas" && (
            <button
              onClick={() => setShowHoraForm(true)}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Registrar horas
            </button>
          )}
          {tab === "labores" && (
            <button
              onClick={() => setShowLaborForm(true)}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Registrar labor
            </button>
          )}
        </div>
      </div>

      <div className="flex border-b border-gray-200 mb-4">
        {(["horas", "labores", "resumen"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors capitalize ${
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t === "horas" ? "Registro Horas" : t === "labores" ? "Registro Labores" : "Resumen"}
          </button>
        ))}
      </div>

      {tab === "horas" && (
        <>
          {horas.length > 0 && (
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total horas</p>
                <p className="text-xl font-semibold text-gray-900 mt-1">{fmt.format(totalHoras)} h</p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total a pagar</p>
                <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(totalHorasMonto)}</p>
              </div>
            </div>
          )}
          {loadH ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : horas.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin registros en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Personal ID", "Tipo trabajo", "Horas", "Tarifa/h", "Total", "Estado", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {horas.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.fecha}</td>
                      <td className="px-4 py-3 text-gray-600">{r.personal_id}</td>
                      <td className="px-4 py-3">
                        <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs">
                          {r.tipo_trabajo.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900">{r.horas_trabajadas}h</td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={r.tarifa_hora} /></td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <CurrencyCell value={r.total ?? r.horas_trabajadas * r.tarifa_hora} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          r.aprobado ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}>
                          {r.aprobado ? "Aprobado" : "Pendiente"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {!r.aprobado && (
                            <button
                              onClick={() => aprobarHora.mutate(r.id)}
                              className="text-gray-400 hover:text-green-600 transition-colors"
                              title="Aprobar"
                            >
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {!r.liquidado && (
                            <button
                              onClick={() => { if (confirm("¿Eliminar este registro?")) deleteHora.mutate(r.id); }}
                              className="text-gray-400 hover:text-red-500 transition-colors"
                            >
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

      {tab === "labores" && (
        <>
          {loadL ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : labores.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin registros en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Personal ID", "Tipo labor", "Cantidad", "Tarifa", "Total", "Estado", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {labores.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.fecha}</td>
                      <td className="px-4 py-3 text-gray-600">{r.personal_id}</td>
                      <td className="px-4 py-3">
                        <span className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded text-xs">
                          {r.tipo_labor.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900">{r.cantidad}</td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={r.tarifa_unitaria} /></td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <CurrencyCell value={r.total ?? r.cantidad * r.tarifa_unitaria} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          r.aprobado ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}>
                          {r.aprobado ? "Aprobado" : "Pendiente"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {!r.aprobado && (
                            <button
                              onClick={() => aprobarLabor.mutate(r.id)}
                              className="text-gray-400 hover:text-green-600 transition-colors"
                              title="Aprobar"
                            >
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {!r.liquidado && (
                            <button
                              onClick={() => { if (confirm("¿Eliminar este registro?")) deleteLabor.mutate(r.id); }}
                              className="text-gray-400 hover:text-red-500 transition-colors"
                            >
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

      {tab === "resumen" && (
        <>
          {resumen.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin datos en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Personal", "Horas", "Monto horas", "Labores", "Monto labores", "Total"].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {resumen.map((r) => (
                    <tr key={r.personal_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{r.nombre_completo}</td>
                      <td className="px-4 py-3 text-gray-600">{fmt.format(r.total_horas)}h</td>
                      <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_horas_monto} /></td>
                      <td className="px-4 py-3 text-gray-600">{r.total_labores}</td>
                      <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_labores_monto} /></td>
                      <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={r.total_general} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {showHoraForm && (
        <RegistroHoraForm
          onClose={() => setShowHoraForm(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["labores-horas"] });
            setShowHoraForm(false);
          }}
        />
      )}
      {showLaborForm && (
        <RegistroLaborForm
          onClose={() => setShowLaborForm(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["labores-labores"] });
            setShowLaborForm(false);
          }}
        />
      )}
    </div>
  );
}

// ── Formulario Registro Horas ─────────────────────────────────────────────────

function RegistroHoraForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const HOY_STR = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    personal_id: 0,
    fecha: HOY_STR,
    horas_trabajadas: 0,
    tarifa_hora: 7960.90,
    tipo_trabajo: "alistamiento_sobres",
    observaciones: "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await laboresApi.createHora({ ...form, orden_id: null, observaciones: form.observaciones || null });
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">Registrar horas</h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Personal ID *</label>
              <input type="number" required min={1} value={form.personal_id || ""}
                onChange={(e) => setForm({ ...form, personal_id: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input type="date" required value={form.fecha}
                onChange={(e) => setForm({ ...form, fecha: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Tipo de trabajo *</label>
            <select required value={form.tipo_trabajo}
              onChange={(e) => setForm({ ...form, tipo_trabajo: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              {TIPOS_TRABAJO.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Horas trabajadas *</label>
              <input type="number" required min={0.5} step={0.5} value={form.horas_trabajadas || ""}
                onChange={(e) => setForm({ ...form, horas_trabajadas: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tarifa/hora *</label>
              <input type="number" required min={0} value={form.tarifa_hora}
                onChange={(e) => setForm({ ...form, tarifa_hora: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
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

// ── Formulario Registro Labor ─────────────────────────────────────────────────

function RegistroLaborForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const HOY_STR = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    personal_id: 0,
    fecha: HOY_STR,
    tipo_labor: "pegado_guia",
    cantidad: 0,
    tarifa_unitaria: 11.54,
    observaciones: "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await laboresApi.createLabor({ ...form, orden_id: null, observaciones: form.observaciones || null });
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">Registrar labor</h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Personal ID *</label>
              <input type="number" required min={1} value={form.personal_id || ""}
                onChange={(e) => setForm({ ...form, personal_id: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input type="date" required value={form.fecha}
                onChange={(e) => setForm({ ...form, fecha: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Tipo de labor *</label>
            <select required value={form.tipo_labor}
              onChange={(e) => setForm({ ...form, tipo_labor: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              {TIPOS_LABOR.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cantidad *</label>
              <input type="number" required min={1} value={form.cantidad || ""}
                onChange={(e) => setForm({ ...form, cantidad: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tarifa unitaria *</label>
              <input type="number" required min={0} step={0.01} value={form.tarifa_unitaria}
                onChange={(e) => setForm({ ...form, tarifa_unitaria: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
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
