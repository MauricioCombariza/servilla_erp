import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Plus, Pencil, Ban } from "lucide-react";
import { ordenesApi } from "@/api/ordenes";
import { clientesApi } from "@/api/clientes";
import { Badge } from "@/components/ui/Badge";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { Orden } from "@/types/domain";
import { OrdenForm } from "./OrdenForm";

const ESTADO_COLORS: Record<string, string> = {
  activa: "bg-blue-50 text-blue-700",
  finalizada: "bg-green-50 text-green-700",
  anulada: "bg-red-50 text-red-500 line-through",
};

export function OrdenesPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Orden | null>(null);
  const [filtros, setFiltros] = useState({
    cliente_id: "",
    estado: "",
    facturado: "",
    fecha_desde: "",
    fecha_hasta: "",
  });

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes", true],
    queryFn: () => clientesApi.list(true).then((r) => r.data),
  });

  const params = Object.fromEntries(
    Object.entries(filtros).filter(([, v]) => v !== "")
  ) as Record<string, string>;
  if (params.facturado) params.facturado = params.facturado === "si" ? "true" : "false";

  const { data: ordenes = [], isLoading } = useQuery({
    queryKey: ["ordenes", filtros],
    queryFn: () => ordenesApi.list(params).then((r) => r.data),
  });

  const anular = useMutation({
    mutationFn: (id: number) => ordenesApi.anular(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ordenes"] }),
  });

  const finalizadas = ordenes.filter((o) => o.cantidad_entregados + o.cantidad_devolucion >= o.cantidad_total && o.cantidad_total > 0).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Órdenes</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {ordenes.length} órdenes · {finalizadas} finalizadas
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/ordenes/carga-masiva")}
            className="flex items-center gap-2 border border-gray-300 hover:bg-gray-50 px-3 py-2 rounded-lg text-sm text-gray-700 transition-colors"
          >
            <Upload size={15} />
            Carga masiva CSV
          </button>
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} />
            Nueva orden
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 grid grid-cols-2 md:grid-cols-5 gap-3">
        <select
          value={filtros.cliente_id}
          onChange={(e) => setFiltros((f) => ({ ...f, cliente_id: e.target.value }))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos los clientes</option>
          {clientes.map((c) => (
            <option key={c.id} value={String(c.id)}>{c.nombre_empresa}</option>
          ))}
        </select>
        <select
          value={filtros.estado}
          onChange={(e) => setFiltros((f) => ({ ...f, estado: e.target.value }))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos los estados</option>
          <option value="activa">Activa</option>
          <option value="finalizada">Finalizada</option>
          <option value="anulada">Anulada</option>
        </select>
        <select
          value={filtros.facturado}
          onChange={(e) => setFiltros((f) => ({ ...f, facturado: e.target.value }))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Facturado: todos</option>
          <option value="si">Facturado</option>
          <option value="no">Sin facturar</option>
        </select>
        <input type="date" value={filtros.fecha_desde}
          onChange={(e) => setFiltros((f) => ({ ...f, fecha_desde: e.target.value }))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          placeholder="Desde"
        />
        <input type="date" value={filtros.fecha_hasta}
          onChange={(e) => setFiltros((f) => ({ ...f, fecha_hasta: e.target.value }))}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          placeholder="Hasta"
        />
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[900px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Orden", "Cliente", "Fecha", "Tipo", "Total", "Entregados", "Dev.", "Valor", "Costo", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {ordenes.map((o) => {
                const pct = o.cantidad_total > 0
                  ? Math.round(((o.cantidad_entregados + o.cantidad_devolucion) / o.cantidad_total) * 100)
                  : 0;
                return (
                  <tr key={o.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-gray-700 whitespace-nowrap">{o.numero_orden}</td>
                    <td className="px-4 py-3 text-gray-900 font-medium max-w-[160px] truncate">{o.cliente.nombre_empresa}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{o.fecha_recepcion}</td>
                    <td className="px-4 py-3">
                      <span className="bg-purple-50 text-purple-700 text-xs px-2 py-0.5 rounded-full capitalize">
                        {o.tipo_servicio}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{o.cantidad_total}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-1.5 w-16">
                          <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-xs text-gray-500">{pct}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{o.cantidad_devolucion}</td>
                    <td className="px-4 py-3"><CurrencyCell value={o.valor_total} /></td>
                    <td className="px-4 py-3"><CurrencyCell value={o.costo_total} /></td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ESTADO_COLORS[o.estado] ?? ""}`}>
                        {o.estado}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button onClick={() => { setEditing(o); setShowForm(true); }}
                          className="text-gray-400 hover:text-primary transition-colors" title="Editar">
                          <Pencil size={14} />
                        </button>
                        {o.estado !== "anulada" && (
                          <button
                            onClick={() => {
                              if (confirm(`¿Anular orden ${o.numero_orden}?`)) anular.mutate(o.id);
                            }}
                            className="text-gray-400 hover:text-red-500 transition-colors" title="Anular"
                          >
                            <Ban size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {ordenes.length === 0 && (
            <div className="text-center py-12 text-gray-400">No hay órdenes con estos filtros</div>
          )}
        </div>
      )}

      {showForm && (
        <OrdenForm
          initial={editing}
          clientes={clientes}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["ordenes"] });
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}
