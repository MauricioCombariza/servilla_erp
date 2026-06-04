import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { clientesApi } from "@/api/clientes";
import { Badge } from "@/components/ui/Badge";
import { useState } from "react";
import { Plus, Pencil, Eye } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ClienteForm } from "./ClienteForm";
import type { Cliente } from "@/types/domain";

export function ClientesPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Cliente | null>(null);
  const [soloActivos, setSoloActivos] = useState(true);

  const { data: clientes = [], isLoading } = useQuery({
    queryKey: ["clientes", soloActivos],
    queryFn: () => clientesApi.list(soloActivos).then((r) => r.data),
  });

  const toggleActivo = useMutation({
    mutationFn: (c: Cliente) => clientesApi.update(c.id, { activo: !c.activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clientes"] }),
  });

  function openEdit(c: Cliente) {
    setEditing(c);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Clientes</h1>
          <p className="text-sm text-gray-500 mt-0.5">{clientes.length} registros</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={soloActivos}
              onChange={(e) => setSoloActivos(e.target.checked)}
              className="rounded border-gray-300"
            />
            Solo activos
          </label>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Nuevo cliente
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : clientes.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No hay clientes registrados</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Empresa", "NIT", "Ciudad", "Plazo pago", "Contacto", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {clientes.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.nombre_empresa}</td>
                  <td className="px-4 py-3 text-gray-600 font-mono text-xs">{c.nit}</td>
                  <td className="px-4 py-3 text-gray-600">{c.ciudad ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{c.plazo_pago_dias}d</td>
                  <td className="px-4 py-3 text-gray-600">{c.contacto_nombre ?? "—"}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleActivo.mutate(c)}>
                      <Badge active={c.activo} />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(c)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Editar"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => navigate(`/clientes/${c.id}`)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Ver precios"
                      >
                        <Eye size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <ClienteForm
          initial={editing}
          onClose={closeForm}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["clientes"] });
            closeForm();
          }}
        />
      )}
    </div>
  );
}
