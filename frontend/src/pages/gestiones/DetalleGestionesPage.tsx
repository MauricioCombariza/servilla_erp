import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Pencil, Lock, X } from "lucide-react";
import { gestionesApi } from "@/api/gestiones";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { Badge } from "@/components/ui/Badge";
import type { SerialGestion } from "@/types/domain";

const ESTADO_COLORS: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  liquidado: "bg-blue-50 text-blue-700",
  facturado: "bg-green-50 text-green-700",
  anulado: "bg-red-50 text-red-500",
  en_revision: "bg-purple-50 text-purple-700",
};

// ── Modal de edición de serial ────────────────────────────────────────────────
interface EditSerialModalProps {
  serial: SerialGestion;
  onClose: () => void;
  onSaved: () => void;
}

function EditSerialModal({ serial, onClose, onSaved }: EditSerialModalProps) {
  const [estado, setEstado] = useState(serial.estado);
  const [precioMen, setPrecioMen] = useState(serial.precio_mensajero);
  const [precioCli, setPrecioCli] = useState(serial.precio_cliente);
  const [obs, setObs] = useState(serial.observaciones ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const patch = useMutation({ mutationFn: (d: Partial<SerialGestion>) => gestionesApi.patch(serial.id, d) });

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      await patch.mutateAsync({
        estado,
        precio_mensajero: precioMen,
        precio_cliente: precioCli,
        observaciones: obs || undefined,
      });
      onSaved();
    } catch {
      setError("Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-sm">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="font-semibold text-gray-900">Editar serial</h2>
            <p className="text-xs font-mono text-gray-500 mt-0.5">{serial.serial}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Estado</label>
            <select
              value={estado}
              onChange={(e) => setEstado(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none"
            >
              {["pendiente", "liquidado", "facturado", "anulado", "en_revision"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Precio mensajero
              </label>
              <input
                type="number"
                min={0}
                step={50}
                value={precioMen}
                onChange={(e) => setPrecioMen(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Precio cliente
              </label>
              <input
                type="number"
                min={0}
                step={50}
                value={precioCli}
                onChange={(e) => setPrecioCli(Number(e.target.value))}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
            <textarea
              value={obs}
              onChange={(e) => setObs(e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none resize-none"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-1">
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
export function DetalleGestionesPage() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [editing, setEditing] = useState<SerialGestion | null>(null);
  const [filtros, setFiltros] = useState({
    planilla: searchParams.get("planilla") ?? "",
    cod_men: "",
    estado: "",
    fecha_desde: "",
    fecha_hasta: "",
  });

  const params = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== ""));

  const { data: seriales = [], isLoading } = useQuery({
    queryKey: ["gestiones", filtros],
    queryFn: () => gestionesApi.list(params).then((r) => r.data),
  });

  function updateFiltro(key: string, value: string) {
    const next = { ...filtros, [key]: value };
    setFiltros(next);
    if (key === "planilla") {
      const sp = new URLSearchParams(searchParams);
      if (value) sp.set("planilla", value);
      else sp.delete("planilla");
      setSearchParams(sp, { replace: true });
    }
  }

  const totalMen = seriales.reduce((s, g) => s + g.precio_mensajero, 0);
  const totalCli = seriales.reduce((s, g) => s + g.precio_cliente, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Detalle Gestiones</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {seriales.length} seriales · mensajero{" "}
            <span className="font-medium">${totalMen.toLocaleString("es-CO")}</span> · cliente{" "}
            <span className="font-medium">${totalCli.toLocaleString("es-CO")}</span>
          </p>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 grid grid-cols-2 md:grid-cols-5 gap-3">
        <input
          placeholder="Planilla"
          value={filtros.planilla}
          onChange={(e) => updateFiltro("planilla", e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
        />
        <input
          placeholder="Mensajero (cód.)"
          value={filtros.cod_men}
          onChange={(e) => updateFiltro("cod_men", e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
        />
        <select
          value={filtros.estado}
          onChange={(e) => updateFiltro("estado", e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos los estados</option>
          {["pendiente", "liquidado", "facturado", "anulado", "en_revision"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          type="date"
          value={filtros.fecha_desde}
          onChange={(e) => updateFiltro("fecha_desde", e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
        />
        <input
          type="date"
          value={filtros.fecha_hasta}
          onChange={(e) => updateFiltro("fecha_hasta", e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
        />
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[1000px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[
                  "Serial",
                  "Planilla",
                  "F.Esc",
                  "Mensajero",
                  "Cliente",
                  "Tipo",
                  "Ámbito",
                  "P.Mensajero",
                  "P.Cliente",
                  "Estado",
                  "",
                ].map((h) => (
                  <th
                    key={h}
                    className="text-left px-3 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {seriales.map((sg) => (
                <tr
                  key={sg.id}
                  className={`hover:bg-gray-50 transition-colors ${sg.editado_manualmente ? "bg-amber-50/30" : ""}`}
                >
                  <td className="px-3 py-2.5 font-mono text-xs text-gray-700 whitespace-nowrap">
                    {sg.serial}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-xs text-gray-500">{sg.planilla || "—"}</td>
                  <td className="px-3 py-2.5 text-gray-600 whitespace-nowrap">{sg.f_esc}</td>
                  <td className="px-3 py-2.5">
                    <span className="font-medium text-gray-900">{sg.cod_men || "—"}</span>
                    {sg.mensajero && (
                      <span className="text-gray-400 text-xs ml-1 hidden xl:inline">
                        · {sg.mensajero.nombre_completo}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-gray-700 max-w-[120px] truncate">
                    {sg.cliente?.nombre_empresa ?? "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        sg.tipo_gestion === "Entrega"
                          ? "bg-green-50 text-green-700"
                          : "bg-orange-50 text-orange-700"
                      }`}
                    >
                      {sg.tipo_gestion}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="text-xs text-gray-500 capitalize">{sg.ambito}</span>
                  </td>
                  <td className="px-3 py-2.5">
                    <CurrencyCell value={sg.precio_mensajero} />
                  </td>
                  <td className="px-3 py-2.5">
                    <CurrencyCell value={sg.precio_cliente} />
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        ESTADO_COLORS[sg.estado] ?? "bg-gray-50 text-gray-600"
                      }`}
                    >
                      {sg.estado}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => setEditing(sg)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Editar"
                      >
                        <Pencil size={13} />
                      </button>
                      {sg.editado_manualmente && (
                        <Lock size={11} className="text-amber-400" title="Bloqueado manualmente" />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {seriales.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              No hay seriales con estos filtros
            </div>
          )}
        </div>
      )}

      {editing && (
        <EditSerialModal
          serial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["gestiones"] });
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
