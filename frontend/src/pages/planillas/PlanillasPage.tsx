import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lock, Unlock, Pencil, List, AlertTriangle } from "lucide-react";
import { gestionesApi } from "@/api/gestiones";
import { personalApi } from "@/api/personal";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { Badge } from "@/components/ui/Badge";
import type { PlanillaResumen } from "@/types/domain";
import { X } from "lucide-react";

// ── Modal de edición de planilla ──────────────────────────────────────────────
interface EditModalProps {
  planilla: PlanillaResumen;
  onClose: () => void;
  onSaved: () => void;
}

function EditModal({ planilla, onClose, onSaved }: EditModalProps) {
  const [codMen, setCodMen] = useState(planilla.cod_men);
  const [mensajeroId, setMensajeroId] = useState<number | undefined>(
    planilla.mensajero_id ?? undefined
  );
  const [precio, setPrecio] = useState(planilla.precio_promedio_mensajero);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { data: personal = [] } = useQuery({
    queryKey: ["personal", true],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
  });

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      if (codMen !== planilla.cod_men) {
        await gestionesApi.cambiarMensajero(planilla.planilla, codMen, mensajeroId);
      }
      if (precio !== planilla.precio_promedio_mensajero) {
        await gestionesApi.cambiarPrecio(planilla.planilla, precio);
      }
      onSaved();
    } catch {
      setError("Error al guardar cambios");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="font-semibold text-gray-900">Editar planilla</h2>
            <p className="text-xs text-gray-500 font-mono mt-0.5">{planilla.planilla}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Mensajero</label>
            <select
              value={codMen}
              onChange={(e) => {
                setCodMen(e.target.value);
                const p = personal.find((p) => p.codigo === e.target.value);
                setMensajeroId(p?.id);
              }}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none"
            >
              <option value="">— sin asignar —</option>
              {personal.map((p) => (
                <option key={p.id} value={p.codigo}>
                  {p.codigo} — {p.nombre_completo}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              Solo actualiza seriales no bloqueados ({planilla.total_seriales} total)
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Precio mensajero ($/serial)
            </label>
            <input
              type="number"
              min={0}
              step={50}
              value={precio}
              onChange={(e) => setPrecio(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
            />
            <p className="text-xs text-gray-400 mt-1">
              Nuevo total ≈{" "}
              <span className="font-medium text-gray-700">
                ${(precio * planilla.total_seriales).toLocaleString("es-CO")}
              </span>
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-60"
            >
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────
export function PlanillasPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<PlanillaResumen | null>(null);
  const [filtros, setFiltros] = useState({
    fecha_desde: new Date(new Date().getFullYear(), new Date().getMonth(), 1)
      .toISOString()
      .split("T")[0],
    fecha_hasta: new Date().toISOString().split("T")[0],
    cod_men: "",
  });

  const params = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== ""));

  const { data: planillas = [], isLoading } = useQuery({
    queryKey: ["planillas", filtros],
    queryFn: () => gestionesApi.planillasResumen(params).then((r) => r.data),
  });

  const bloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.bloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planillas"] }),
  });

  const desbloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.desbloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planillas"] }),
  });

  const totalSeriales = planillas.reduce((s, p) => s + p.total_seriales, 0);
  const totalMensajero = planillas.reduce((s, p) => s + p.total_mensajero, 0);
  const sinPrecio = planillas.reduce((s, p) => s + p.con_precio_cero, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Planillas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {planillas.length} planillas · {totalSeriales.toLocaleString()} seriales
          </p>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Desde</label>
          <input
            type="date"
            value={filtros.fecha_desde}
            onChange={(e) => setFiltros((f) => ({ ...f, fecha_desde: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Hasta</label>
          <input
            type="date"
            value={filtros.fecha_hasta}
            onChange={(e) => setFiltros((f) => ({ ...f, fecha_hasta: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Mensajero</label>
          <input
            type="text"
            placeholder="Código ej. MN01"
            value={filtros.cod_men}
            onChange={(e) => setFiltros((f) => ({ ...f, cod_men: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {[
          { label: "Total mensajero", value: `$${totalMensajero.toLocaleString("es-CO")}` },
          { label: "Sin precio", value: sinPrecio, warn: sinPrecio > 0 },
          {
            label: "Bloqueadas",
            value: `${planillas.filter((p) => p.bloqueada).length} / ${planillas.length}`,
          },
        ].map(({ label, value, warn }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 px-5 py-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
            <p className={`text-xl font-semibold mt-1 ${warn ? "text-amber-600" : "text-gray-900"}`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Tabla */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[
                  "Planilla",
                  "Mensajero",
                  "Fecha",
                  "Entregas",
                  "Dev.",
                  "Total",
                  "Val. Mensajero",
                  "Val. Cliente",
                  "Estado",
                  "",
                ].map((h) => (
                  <th
                    key={h}
                    className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {planillas.map((p) => (
                <tr key={`${p.planilla}-${p.cod_men}`} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.planilla || "—"}</td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{p.cod_men}</span>
                    {p.mensajero_nombre && (
                      <span className="text-gray-400 text-xs ml-1">· {p.mensajero_nombre}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                    {p.fecha_escaner ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{p.entregas}</td>
                  <td className="px-4 py-3 text-gray-700">{p.devoluciones}</td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{p.total_seriales}</span>
                    {p.con_precio_cero > 0 && (
                      <span
                        className="ml-1 text-amber-500"
                        title={`${p.con_precio_cero} sin precio`}
                      >
                        <AlertTriangle size={12} className="inline" />
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <CurrencyCell value={p.total_mensajero} />
                  </td>
                  <td className="px-4 py-3">
                    <CurrencyCell value={p.total_cliente} />
                  </td>
                  <td className="px-4 py-3">
                    {p.bloqueada ? (
                      <Badge color="green">Bloqueada</Badge>
                    ) : (
                      <Badge color="gray">Abierta</Badge>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setEditing(p)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Editar mensajero / precio"
                      >
                        <Pencil size={14} />
                      </button>
                      {p.bloqueada ? (
                        <button
                          onClick={() => desbloquear.mutate(p.planilla)}
                          className="text-gray-400 hover:text-amber-500 transition-colors"
                          title="Desbloquear planilla"
                        >
                          <Unlock size={14} />
                        </button>
                      ) : (
                        <button
                          onClick={() => bloquear.mutate(p.planilla)}
                          className="text-gray-400 hover:text-green-600 transition-colors"
                          title="Bloquear planilla"
                        >
                          <Lock size={14} />
                        </button>
                      )}
                      <button
                        onClick={() =>
                          navigate(`/gestiones?planilla=${encodeURIComponent(p.planilla)}`)
                        }
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Ver seriales"
                      >
                        <List size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {planillas.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              No hay planillas con estos filtros
            </div>
          )}
        </div>
      )}

      {editing && (
        <EditModal
          planilla={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["planillas"] });
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
