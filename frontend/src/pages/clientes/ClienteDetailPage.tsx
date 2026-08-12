import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { ArrowLeft, Plus, Pencil, Trash2 } from "lucide-react";
import { clientesApi } from "@/api/clientes";
import { Badge } from "@/components/ui/Badge";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { PrecioClienteForm } from "./PrecioClienteForm";
import type { PrecioCliente } from "@/types/domain";

export function ClienteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const clienteId = Number(id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PrecioCliente | null>(null);

  const { data: cliente, isLoading } = useQuery({
    queryKey: ["cliente", clienteId],
    queryFn: () => clientesApi.get(clienteId).then((r) => r.data),
  });

  const deletePrecio = useMutation({
    mutationFn: (precioId: number) => clientesApi.deletePrecio(clienteId, precioId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cliente", clienteId] }),
  });

  function openNew() {
    setEditing(null);
    setShowForm(true);
  }

  function openEdit(p: PrecioCliente) {
    setEditing(p);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  if (isLoading) return <div className="text-center py-16 text-gray-500">Cargando...</div>;
  if (!cliente) return <div className="text-center py-16 text-gray-400">Cliente no encontrado</div>;

  return (
    <div>
      <button
        onClick={() => navigate("/clientes")}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft size={15} />
        Volver a clientes
      </button>

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">{cliente.nombre_empresa}</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            NIT {cliente.nit} · {cliente.ciudad ?? "—"} · Plazo pago {cliente.plazo_pago_dias}d
          </p>
        </div>
        <button
          onClick={openNew}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Nuevo precio
        </button>
      </div>

      {cliente.precios.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          Este cliente no tiene precios configurados
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[
                  "Servicio", "Ámbito", "Precio entrega", "Precio devolución",
                  "Costo mensajero entrega", "Costo mensajero devolución",
                  "Vigencia", "Estado", "",
                ].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cliente.precios.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-900 capitalize">{p.tipo_servicio}</td>
                  <td className="px-4 py-3 text-gray-600 capitalize">{p.ambito}</td>
                  <td className="px-4 py-3"><CurrencyCell value={p.precio_entrega} /></td>
                  <td className="px-4 py-3"><CurrencyCell value={p.precio_devolucion} /></td>
                  <td className="px-4 py-3"><CurrencyCell value={p.costo_mensajero_entrega} /></td>
                  <td className="px-4 py-3"><CurrencyCell value={p.costo_mensajero_devolucion} /></td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                    {p.vigencia_desde} → {p.vigencia_hasta ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge active={p.activo} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEdit(p)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Editar"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm("¿Desactivar este precio?")) deletePrecio.mutate(p.id);
                        }}
                        className="text-gray-400 hover:text-red-600 transition-colors"
                        title="Desactivar"
                      >
                        <Trash2 size={15} />
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
        <PrecioClienteForm
          clienteId={clienteId}
          initial={editing}
          onClose={closeForm}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["cliente", clienteId] });
            closeForm();
          }}
        />
      )}
    </div>
  );
}
