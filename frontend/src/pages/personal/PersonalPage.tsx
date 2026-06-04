import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { personalApi } from "@/api/personal";
import { Badge } from "@/components/ui/Badge";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { PersonalForm } from "./PersonalForm";
import type { Personal } from "@/types/domain";

const TIPO_LABELS: Record<string, string> = {
  mensajero: "Mensajero",
  alistamiento: "Alistamiento",
  conductor: "Conductor",
  courier_externo: "Courier ext.",
  transportadora: "Transportadora",
};

export function PersonalPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Personal | null>(null);
  const [tipoFiltro, setTipoFiltro] = useState("");

  const { data: personal = [], isLoading } = useQuery({
    queryKey: ["personal", tipoFiltro],
    queryFn: () =>
      personalApi.list(tipoFiltro ? { tipo: tipoFiltro } : undefined).then((r) => r.data),
  });

  const toggleActivo = useMutation({
    mutationFn: (p: Personal) => personalApi.update(p.id, { activo: !p.activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["personal"] }),
  });

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Personal</h1>
          <p className="text-sm text-gray-500 mt-0.5">{personal.length} registros</p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={tipoFiltro}
            onChange={(e) => setTipoFiltro(e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
          >
            <option value="">Todos los tipos</option>
            {Object.entries(TIPO_LABELS).map(([val, lbl]) => (
              <option key={val} value={val}>{lbl}</option>
            ))}
          </select>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Nuevo
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Código", "Nombre", "Tipo", "Teléfono", "Precio local", "Precio nac.", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {personal.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.codigo}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{p.nombre_completo}</td>
                  <td className="px-4 py-3 text-gray-600">
                    <span className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full">
                      {TIPO_LABELS[p.tipo_personal] ?? p.tipo_personal}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{p.telefono ?? "—"}</td>
                  <td className="px-4 py-3"><CurrencyCell value={p.precio_local} /></td>
                  <td className="px-4 py-3"><CurrencyCell value={p.precio_nacional} /></td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleActivo.mutate(p)}>
                      <Badge active={p.activo} />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => { setEditing(p); setShowForm(true); }}
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

      {showForm && (
        <PersonalForm
          initial={editing}
          onClose={closeForm}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["personal"] });
            closeForm();
          }}
        />
      )}
    </div>
  );
}
