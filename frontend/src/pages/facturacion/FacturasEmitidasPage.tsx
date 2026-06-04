import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Pencil, Ban, DollarSign, Eye } from "lucide-react";
import { facturacionApi, type FacturaEmitida } from "@/api/facturacion";
import { clientesApi } from "@/api/clientes";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { FacturaEmitidaForm } from "./FacturaEmitidaForm";
import { PagoModal } from "./PagoModal";

const ESTADO_STYLE: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  parcial: "bg-blue-50 text-blue-700",
  pagada: "bg-green-50 text-green-700",
  vencida: "bg-red-50 text-red-600",
  anulada: "bg-gray-100 text-gray-400 line-through",
};

export function FacturasEmitidasPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [showPago, setShowPago] = useState<FacturaEmitida | null>(null);
  const [clienteFiltro, setClienteFiltro] = useState("");
  const [estadoFiltro, setEstadoFiltro] = useState("");

  const { data: clientes = [] } = useQuery({
    queryKey: ["clientes", true],
    queryFn: () => clientesApi.list(true).then((r) => r.data),
  });

  const params: Record<string, string | number> = {};
  if (clienteFiltro) params.cliente_id = Number(clienteFiltro);
  if (estadoFiltro) params.estado = estadoFiltro;

  const { data: facturas = [], isLoading } = useQuery({
    queryKey: ["facturas-emitidas", clienteFiltro, estadoFiltro],
    queryFn: () => facturacionApi.listEmitidas(params).then((r) => r.data),
  });

  const anular = useMutation({
    mutationFn: (id: number) => facturacionApi.anularEmitida(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["facturas-emitidas"] }),
  });

  const totalPendiente = facturas
    .filter((f) => !["pagada", "anulada"].includes(f.estado))
    .reduce((s, f) => s + f.saldo_pendiente, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Facturas Emitidas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {facturas.length} facturas · Por cobrar: <span className="font-medium text-blue-700">
              ${new Intl.NumberFormat("es-CO").format(totalPendiente)}
            </span>
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Nueva factura
        </button>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 mb-4">
        <select
          value={clienteFiltro}
          onChange={(e) => setClienteFiltro(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos los clientes</option>
          {clientes.map((c) => (
            <option key={c.id} value={String(c.id)}>{c.nombre_empresa}</option>
          ))}
        </select>
        <select
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
        >
          <option value="">Todos los estados</option>
          {["pendiente", "parcial", "pagada", "vencida", "anulada"].map((e) => (
            <option key={e} value={e}>{e.charAt(0).toUpperCase() + e.slice(1)}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[800px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Número", "Cliente", "Período", "Vencimiento", "Total", "Saldo", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {facturas.map((f) => (
                <tr key={f.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{f.numero_factura}</td>
                  <td className="px-4 py-3 font-medium text-gray-900 max-w-[160px] truncate">{f.cliente.nombre_empresa}</td>
                  <td className="px-4 py-3 text-gray-600">{f.periodo_mes}/{f.periodo_anio}</td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{f.fecha_vencimiento}</td>
                  <td className="px-4 py-3"><CurrencyCell value={f.total} /></td>
                  <td className="px-4 py-3 font-medium">
                    <span className={f.saldo_pendiente > 0 ? "text-orange-600" : "text-green-600"}>
                      <CurrencyCell value={f.saldo_pendiente} />
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ESTADO_STYLE[f.estado] ?? ""}`}>
                      {f.estado}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {f.estado !== "anulada" && f.estado !== "pagada" && (
                        <button
                          onClick={() => setShowPago(f)}
                          className="text-gray-400 hover:text-green-600 transition-colors" title="Registrar pago"
                        >
                          <DollarSign size={14} />
                        </button>
                      )}
                      {f.estado !== "anulada" && (
                        <button
                          onClick={() => { if (confirm(`¿Anular factura ${f.numero_factura}?`)) anular.mutate(f.id); }}
                          className="text-gray-400 hover:text-red-500 transition-colors" title="Anular"
                        >
                          <Ban size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {facturas.length === 0 && (
            <div className="text-center py-12 text-gray-400">No hay facturas con estos filtros</div>
          )}
        </div>
      )}

      {showForm && (
        <FacturaEmitidaForm
          clientes={clientes}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["facturas-emitidas"] });
            qc.invalidateQueries({ queryKey: ["facturacion-resumen"] });
            setShowForm(false);
          }}
        />
      )}

      {showPago && (
        <PagoModal
          titulo={`Registrar pago — ${showPago.numero_factura}`}
          saldoMaximo={showPago.saldo_pendiente}
          onClose={() => setShowPago(null)}
          onSave={async (pago) => {
            await facturacionApi.registrarPagoEmitida(showPago.id, {
              ...pago, observaciones: pago.observaciones ?? null, referencia: pago.referencia ?? null,
            });
            qc.invalidateQueries({ queryKey: ["facturas-emitidas"] });
            qc.invalidateQueries({ queryKey: ["facturacion-resumen"] });
            setShowPago(null);
          }}
        />
      )}
    </div>
  );
}
