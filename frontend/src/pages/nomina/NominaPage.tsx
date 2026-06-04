import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Calculator } from "lucide-react";
import { nominaApi } from "@/api/nomina";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { Badge } from "@/components/ui/Badge";
import type { NominaEmpleado, NominaProvision } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();

type Tab = "empleados" | "provisiones";

export function NominaPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("empleados");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<NominaEmpleado | null>(null);
  const [calcResult, setCalcResult] = useState<string | null>(null);

  const { data: empleados = [], isLoading } = useQuery({
    queryKey: ["nomina-empleados"],
    queryFn: () => nominaApi.listEmpleados().then((r) => r.data),
  });

  const { data: provisiones = [], isLoading: loadingProv } = useQuery({
    queryKey: ["nomina-provisiones", mes, anio],
    queryFn: () => nominaApi.listProvisiones({ mes, anio }).then((r) => r.data),
    enabled: tab === "provisiones",
  });

  const calcular = useMutation({
    mutationFn: () => nominaApi.calcularProvisiones(mes, anio),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["nomina-provisiones"] });
      setCalcResult(
        `${res.data.total_empleados} empleados — costo total: $${fmt.format(res.data.costo_total)}`
      );
    },
  });

  const totalSalarios = empleados.filter((e) => e.activo).reduce((s, e) => s + e.salario_mensual, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Nómina</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {empleados.filter((e) => e.activo).length} empleados activos · Masa salarial:{" "}
            <span className="font-medium text-gray-800">${fmt.format(totalSalarios)}</span>
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
          {tab === "provisiones" && (
            <button
              onClick={() => calcular.mutate()}
              disabled={calcular.isPending}
              className="flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60"
            >
              <Calculator size={16} />
              {calcular.isPending ? "Calculando..." : "Calcular período"}
            </button>
          )}
          {tab === "empleados" && (
            <button
              onClick={() => { setEditing(null); setShowForm(true); }}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Nuevo empleado
            </button>
          )}
        </div>
      </div>

      {calcResult && (
        <div className="bg-green-50 border border-green-200 text-green-800 text-sm px-4 py-3 rounded-lg mb-4">
          Provisiones calculadas: {calcResult}
          <button onClick={() => setCalcResult(null)} className="ml-3 text-green-600 hover:text-green-800">✕</button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        {(["empleados", "provisiones"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors capitalize ${
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "empleados" && (
        <>
          {isLoading ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : empleados.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin empleados registrados</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Nombre", "Identificación", "Cargo", "Salario base", "Auxilio transp.", "Aux. no salarial", "Estado", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {empleados.map((e) => (
                    <tr key={e.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{e.nombre_completo}</td>
                      <td className="px-4 py-3 text-gray-600 font-mono text-xs">{e.identificacion ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-600">{e.cargo ?? "—"}</td>
                      <td className="px-4 py-3 font-medium text-gray-900"><CurrencyCell value={e.salario_mensual} /></td>
                      <td className="px-4 py-3 text-center">
                        {e.tiene_auxilio_transporte ? (
                          <span className="text-green-600 text-xs font-medium">Sí · $162k</span>
                        ) : (
                          <span className="text-gray-400 text-xs">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={e.auxilio_no_salarial} /></td>
                      <td className="px-4 py-3">
                        <Badge active={e.activo} />
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => { setEditing(e); setShowForm(true); }}
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
          )}
        </>
      )}

      {tab === "provisiones" && (
        <ProvisionesTab provisiones={provisiones} loading={loadingProv} />
      )}

      {showForm && (
        <EmpleadoForm
          initial={editing}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["nomina-empleados"] });
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// ── Provisiones Tab ───────────────────────────────────────────────────────────

function ProvisionesTab({ provisiones, loading }: { provisiones: NominaProvision[]; loading: boolean }) {
  if (loading) return <div className="text-center py-16 text-gray-500">Cargando...</div>;
  if (provisiones.length === 0)
    return (
      <div className="text-center py-16 text-gray-400">
        Sin provisiones para este período. Use "Calcular período" para generarlas.
      </div>
    );

  const totales = provisiones.reduce(
    (acc, p) => ({
      salario: acc.salario + (p.salario_base ?? 0),
      ss: acc.ss + (p.arl ?? 0) + (p.eps ?? 0) + (p.afp ?? 0) + (p.caja_compensacion ?? 0),
      prov: acc.prov + (p.prima ?? 0) + (p.cesantias ?? 0) + (p.int_cesantias ?? 0) + (p.vacaciones ?? 0),
    }),
    { salario: 0, ss: 0, prov: 0 }
  );

  return (
    <>
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Total salarios", value: totales.salario },
          { label: "Seguridad social", value: totales.ss },
          { label: "Provisiones", value: totales.prov },
        ].map((m) => (
          <div key={m.label} className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide">{m.label}</p>
            <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(m.value)}</p>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Empleado ID", "Salario", "Aux. transp.", "ARL", "EPS", "AFP", "Caja", "Prima", "Cesantías", "Int. ces.", "Vacaciones"].map((h) => (
                <th key={h} className="text-right first:text-left px-3 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {provisiones.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-3 py-3 text-gray-600 font-mono text-xs">{p.empleado_id}</td>
                {[p.salario_base, p.auxilio_transporte, p.arl, p.eps, p.afp, p.caja_compensacion, p.prima, p.cesantias, p.int_cesantias, p.vacaciones].map((v, i) => (
                  <td key={i} className="px-3 py-3 text-right text-gray-700 text-xs">
                    {v != null ? `$${fmt.format(v)}` : "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Formulario Empleado ───────────────────────────────────────────────────────

function EmpleadoForm({
  initial,
  onClose,
  onSaved,
}: {
  initial: NominaEmpleado | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    nombre_completo: initial?.nombre_completo ?? "",
    identificacion: initial?.identificacion ?? "",
    cargo: initial?.cargo ?? "",
    salario_mensual: initial?.salario_mensual ?? 0,
    tiene_auxilio_transporte: initial?.tiene_auxilio_transporte ?? false,
    auxilio_no_salarial: initial?.auxilio_no_salarial ?? 0,
    fecha_ingreso: initial?.fecha_ingreso ?? "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        identificacion: form.identificacion || null,
        cargo: form.cargo || null,
        fecha_ingreso: form.fecha_ingreso || null,
      };
      if (initial) {
        await nominaApi.updateEmpleado(initial.id, payload);
      } else {
        await nominaApi.createEmpleado(payload);
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
            {initial ? "Editar empleado" : "Nuevo empleado"}
          </h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Nombre completo *</label>
            <input
              required
              value={form.nombre_completo}
              onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Identificación</label>
              <input
                value={form.identificacion}
                onChange={(e) => setForm({ ...form, identificacion: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cargo</label>
              <input
                value={form.cargo}
                onChange={(e) => setForm({ ...form, cargo: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Salario mensual *</label>
              <input
                type="number"
                required
                min={0}
                value={form.salario_mensual}
                onChange={(e) => setForm({ ...form, salario_mensual: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Aux. no salarial</label>
              <input
                type="number"
                min={0}
                value={form.auxilio_no_salarial}
                onChange={(e) => setForm({ ...form, auxilio_no_salarial: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="aux_transp"
              checked={form.tiene_auxilio_transporte}
              onChange={(e) => setForm({ ...form, tiene_auxilio_transporte: e.target.checked })}
              className="rounded border-gray-300"
            />
            <label htmlFor="aux_transp" className="text-sm text-gray-700">
              Tiene auxilio de transporte ($162.000)
            </label>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha ingreso</label>
            <input
              type="date"
              value={form.fecha_ingreso}
              onChange={(e) => setForm({ ...form, fecha_ingreso: e.target.value })}
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
