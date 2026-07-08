import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign, Pencil, Trash2, CheckCircle2, X, ChevronDown, ChevronRight, SlidersHorizontal } from "lucide-react";
import api from "@/api/client";
import { personalApi } from "@/api/personal";
import { CurrencyCell } from "@/components/ui/CurrencyCell";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const HOY = new Date();
const HOY_STR = HOY.toISOString().slice(0, 10);
const PRIMER_DIA = new Date(HOY.getFullYear(), HOY.getMonth(), 1).toISOString().slice(0, 10);

interface PlanillaCalculada {
  planilla: string;
  cod_mensajero: string;
  fecha_escaner: string | null;
  cantidad_local: number;
  cantidad_nacional: number;
  precio_local_promedio: number;
  precio_nac_promedio: number;
  valor_local: number;
  valor_nac: number;
  valor_total: number;
  ya_incluida: boolean;
  prefactura_id: number | null;
}

interface PrefacturaPlanilla {
  id: number;
  planilla: string;
  fecha_escaner: string | null;
  cantidad_local: number;
  cantidad_nacional: number;
  precio_local: number;
  precio_nac: number;
  valor_local: number;
  valor_nac: number;
  valor_total: number;
}

interface PrefacturaCourier {
  id: number;
  cod_mensajero: string;
  mensajero_nombre: string | null;
  fecha_generacion: string;
  periodo_desde: string | null;
  periodo_hasta: string | null;
  cantidad_planillas: number;
  cantidad_local: number;
  cantidad_nacional: number;
  valor_local: number;
  valor_nacional: number;
  valor_total: number;
  estado: "borrador" | "aprobada" | "facturada";
  notas: string | null;
  valor_ajustado: number | null;
  notas_ajuste: string | null;
  valor_a_pagar: number;
  created_at: string | null;
  planillas: PrefacturaPlanilla[];
}

interface FacturaCourierCxp {
  id: number;
  prefactura_id: number;
  cod_mensajero: string;
  mensajero_nombre: string | null;
  numero_factura: string;
  fecha_emision: string | null;
  fecha_vencimiento: string;
  valor_total: number;
  estado: "pendiente" | "pagada" | "vencida";
  notas: string | null;
  fecha_pago: string | null;
  created_at: string | null;
}

const pagosApi = {
  planillas: (params: { cod_mensajero: string; desde: string; hasta: string }) =>
    api.get<PlanillaCalculada[]>("/pagos-ciudades/planillas", { params }),
  crearPrefactura: (data: object) => api.post<PrefacturaCourier>("/pagos-ciudades/prefacturas", data),
  listarPrefacturas: (params?: object) => api.get<PrefacturaCourier[]>("/pagos-ciudades/prefacturas", { params }),
  aprobarPrefactura: (id: number) => api.post<PrefacturaCourier>(`/pagos-ciudades/prefacturas/${id}/aprobar`),
  ajustarMonto: (id: number, data: { valor_ajustado: number | null; notas_ajuste: string | null }) =>
    api.put<PrefacturaCourier>(`/pagos-ciudades/prefacturas/${id}/ajuste`, data),
  eliminarPrefactura: (id: number) => api.delete(`/pagos-ciudades/prefacturas/${id}`),
  registrarFactura: (id: number, data: object) =>
    api.post<FacturaCourierCxp>(`/pagos-ciudades/prefacturas/${id}/registrar-factura`, data),
  listarCxp: (params?: object) => api.get<FacturaCourierCxp[]>("/pagos-ciudades/cxp", { params }),
  pagarCxp: (id: number, data: object) => api.post<FacturaCourierCxp>(`/pagos-ciudades/cxp/${id}/pagar`, data),
  editarCxp: (id: number, data: object) => api.put<FacturaCourierCxp>(`/pagos-ciudades/cxp/${id}`, data),
};

const ESTADO_PREFACTURA_STYLE: Record<string, string> = {
  borrador: "bg-gray-100 text-gray-600",
  aprobada: "bg-blue-50 text-blue-700",
  facturada: "bg-green-50 text-green-700",
};

const ESTADO_CXP_STYLE: Record<string, string> = {
  pendiente: "bg-yellow-50 text-yellow-700",
  vencida: "bg-red-50 text-red-700",
  pagada: "bg-green-50 text-green-700",
};

type Tab = "planillas" | "prefacturas" | "cxp";

export function PagosCiudadesPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("planillas");

  const tabs: { key: Tab; label: string }[] = [
    { key: "planillas", label: "Seleccionar Planillas" },
    { key: "prefacturas", label: "Prefacturas" },
    { key: "cxp", label: "Cuentas por Pagar" },
  ];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Pagos Ciudades — Couriers Externos</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Facturación por ciudades a proveedores de transporte externos
        </p>
      </div>

      <div className="flex border-b border-gray-200 mb-4">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "planillas" && <PlanillasTab qc={qc} onCreated={() => setTab("prefacturas")} />}
      {tab === "prefacturas" && <PrefacturasTab qc={qc} />}
      {tab === "cxp" && <CxpTab qc={qc} />}
    </div>
  );
}

// ── Tab: Seleccionar Planillas ────────────────────────────────────────────────

function PlanillasTab({ qc, onCreated }: { qc: ReturnType<typeof useQueryClient>; onCreated: () => void }) {
  const [codMensajero, setCodMensajero] = useState("");
  const [desde, setDesde] = useState(PRIMER_DIA);
  const [hasta, setHasta] = useState(HOY_STR);
  const [seleccionadas, setSeleccionadas] = useState<Set<string>>(new Set());
  const [showConfirm, setShowConfirm] = useState(false);

  const { data: couriers = [] } = useQuery({
    queryKey: ["personal-couriers-externos"],
    queryFn: () => personalApi.list({ activo: true }).then((r) =>
      r.data.filter((p) => p.tipo_personal === "courier_externo" || p.tipo_personal === "transportadora")
    ),
  });

  const { data: planillas = [], isLoading, refetch } = useQuery({
    queryKey: ["pc-planillas", codMensajero, desde, hasta],
    queryFn: () => pagosApi.planillas({ cod_mensajero: codMensajero, desde, hasta }).then((r) => r.data),
    enabled: !!codMensajero,
  });

  const crear = useMutation({
    mutationFn: (data: object) => pagosApi.crearPrefactura(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pc-planillas"] });
      qc.invalidateQueries({ queryKey: ["pc-prefacturas"] });
      setSeleccionadas(new Set());
      setShowConfirm(false);
      onCreated();
    },
    onError: () => {
      refetch();
    },
  });

  function toggle(planilla: string) {
    setSeleccionadas((prev) => {
      const next = new Set(prev);
      if (next.has(planilla)) next.delete(planilla);
      else next.add(planilla);
      return next;
    });
  }

  const filas = planillas.filter((p) => seleccionadas.has(p.planilla));
  const totalLocal = filas.reduce((s, p) => s + p.cantidad_local, 0);
  const totalNacional = filas.reduce((s, p) => s + p.cantidad_nacional, 0);
  const totalValor = filas.reduce((s, p) => s + p.valor_total, 0);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={codMensajero} onChange={(e) => { setCodMensajero(e.target.value); setSeleccionadas(new Set()); }}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-64">
          <option value="">Seleccione un courier...</option>
          {couriers.map((c) => (
            <option key={c.id} value={c.codigo}>{c.nombre_completo} ({c.codigo})</option>
          ))}
        </select>
        <label className="text-xs text-gray-500">Desde</label>
        <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" />
        <label className="text-xs text-gray-500">Hasta</label>
        <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm" />
      </div>

      {!codMensajero ? (
        <div className="text-center py-16 text-gray-400">Seleccione un courier para ver sus planillas</div>
      ) : isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : planillas.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin planillas en este período</div>
      ) : (
        <>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {["", "Planilla", "Fecha", "Local", "Nacional", "P. local prom.", "P. nac. prom.", "Valor total", "Estado"].map((h) => (
                    <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {planillas.map((p) => (
                  <tr key={p.planilla} className={`hover:bg-gray-50 ${p.ya_incluida ? "opacity-50" : ""}`}>
                    <td className="px-4 py-3">
                      <input type="checkbox" disabled={p.ya_incluida}
                        checked={seleccionadas.has(p.planilla)}
                        onChange={() => toggle(p.planilla)} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.planilla}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{p.fecha_escaner ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-600">{p.cantidad_local}</td>
                    <td className="px-4 py-3 text-gray-600">{p.cantidad_nacional}</td>
                    <td className="px-4 py-3 text-gray-600"><CurrencyCell value={p.precio_local_promedio} /></td>
                    <td className="px-4 py-3 text-gray-600"><CurrencyCell value={p.precio_nac_promedio} /></td>
                    <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={p.valor_total} /></td>
                    <td className="px-4 py-3">
                      {p.ya_incluida
                        ? <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500">En prefactura #{p.prefactura_id}</span>
                        : <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700">Disponible</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-4 bg-white rounded-xl border border-gray-200 px-4 py-3">
            <div className="text-sm text-gray-600">
              {seleccionadas.size} planilla(s) seleccionada(s) · Local: {totalLocal} · Nacional: {totalNacional}
              {" · "}Total: <span className="font-semibold text-gray-900">${fmt.format(totalValor)}</span>
            </div>
            <button
              disabled={seleccionadas.size === 0}
              onClick={() => setShowConfirm(true)}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
            >
              <CheckCircle2 size={16} /> Generar prefactura
            </button>
          </div>
        </>
      )}

      {showConfirm && (
        <ConfirmarPrefacturaModal
          codMensajero={codMensajero}
          desde={desde}
          hasta={hasta}
          planillas={Array.from(seleccionadas)}
          totalValor={totalValor}
          saving={crear.isPending}
          error={crear.isError ? (crear.error as any)?.response?.data?.detail ?? "Error al crear la prefactura" : null}
          onClose={() => setShowConfirm(false)}
          onConfirm={(notas, montoAjustado, notasAjuste) => crear.mutate({
            cod_mensajero: codMensajero,
            periodo_desde: desde,
            periodo_hasta: hasta,
            planillas: Array.from(seleccionadas),
            notas: notas || null,
            valor_ajustado: montoAjustado,
            notas_ajuste: notasAjuste,
          })}
        />
      )}
    </div>
  );
}

function ConfirmarPrefacturaModal({
  codMensajero, planillas, totalValor, saving, error, onClose, onConfirm,
}: {
  codMensajero: string; desde: string; hasta: string; planillas: string[]; totalValor: number;
  saving: boolean; error: string | null; onClose: () => void;
  onConfirm: (notas: string, montoAjustado: number | null, notasAjuste: string | null) => void;
}) {
  const [notas, setNotas] = useState("");
  const [montoPagar, setMontoPagar] = useState(String(totalValor));
  const [notasAjuste, setNotasAjuste] = useState("");

  const montoNum = montoPagar === "" ? totalValor : +montoPagar;
  const ajustado = montoNum !== totalValor;

  function handleConfirm() {
    onConfirm(notas, ajustado ? montoNum : null, ajustado ? (notasAjuste || null) : null);
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Generar prefactura</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Courier {codMensajero} · {planillas.length} planilla(s) · Calculado: ${fmt.format(totalValor)}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <div className="px-6 py-4 space-y-4">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Monto a pagar</label>
            <input type="number" min={0} value={montoPagar}
              onChange={(e) => setMontoPagar(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            {ajustado && (
              <p className="text-xs text-amber-600 mt-1">Ajustado respecto al calculado (${fmt.format(totalValor)})</p>
            )}
          </div>
          {ajustado && (
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Motivo del ajuste</label>
              <input value={notasAjuste} onChange={(e) => setNotasAjuste(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                placeholder="Opcional" />
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas (opcional)</label>
            <textarea value={notas} onChange={(e) => setNotas(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3} />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="button" disabled={saving} onClick={handleConfirm}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Generar prefactura"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tab: Prefacturas ──────────────────────────────────────────────────────────

function PrefacturasTab({ qc }: { qc: ReturnType<typeof useQueryClient> }) {
  const [estado, setEstado] = useState<string>("");
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [facturando, setFacturando] = useState<PrefacturaCourier | null>(null);
  const [ajustando, setAjustando] = useState<PrefacturaCourier | null>(null);

  const { data: prefacturas = [], isLoading } = useQuery({
    queryKey: ["pc-prefacturas", estado],
    queryFn: () => pagosApi.listarPrefacturas(estado ? { estado } : undefined).then((r) => r.data),
  });

  const aprobar = useMutation({
    mutationFn: (id: number) => pagosApi.aprobarPrefactura(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pc-prefacturas"] }),
  });

  const eliminar = useMutation({
    mutationFn: (id: number) => pagosApi.eliminarPrefactura(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pc-prefacturas"] }),
  });

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <select value={estado} onChange={(e) => setEstado(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
          <option value="">Todas</option>
          <option value="borrador">Borrador</option>
          <option value="aprobada">Aprobada</option>
          <option value="facturada">Facturada</option>
        </select>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : prefacturas.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin prefacturas</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["", "Courier", "Generada", "Período", "Planillas", "Valor calculado", "Monto a pagar", "Estado", ""].map((h, i) => (
                  <th key={i} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {prefacturas.map((p) => (
                <>
                  <tr key={p.id} className={`border-b border-gray-100 hover:bg-gray-50 ${expandedId === p.id ? "bg-blue-50" : ""}`}>
                    <td className="px-4 py-3 w-6">
                      <button onClick={() => setExpandedId(expandedId === p.id ? null : p.id)} className="text-gray-400 hover:text-gray-700">
                        {expandedId === p.id ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-900">{p.mensajero_nombre ?? p.cod_mensajero}</p>
                      <p className="text-xs text-gray-400">{p.cod_mensajero}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{p.fecha_generacion}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{p.periodo_desde} — {p.periodo_hasta}</td>
                    <td className="px-4 py-3 text-gray-600">{p.cantidad_planillas}</td>
                    <td className="px-4 py-3 text-gray-500">
                      <span className={p.valor_ajustado != null ? "line-through" : ""}><CurrencyCell value={p.valor_total} /></span>
                    </td>
                    <td className="px-4 py-3 font-semibold text-gray-900">
                      <CurrencyCell value={p.valor_a_pagar} />
                      {p.valor_ajustado != null && (
                        <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 align-middle">ajustado</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_PREFACTURA_STYLE[p.estado]}`}>{p.estado}</span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {p.estado === "borrador" && (
                          <>
                            <button onClick={() => setAjustando(p)} className="text-gray-400 hover:text-amber-600" title="Ajustar monto">
                              <SlidersHorizontal size={14} />
                            </button>
                            <button onClick={() => aprobar.mutate(p.id)} className="text-gray-400 hover:text-blue-600" title="Aprobar">
                              <CheckCircle2 size={14} />
                            </button>
                            <button onClick={() => { if (confirm("¿Eliminar prefactura?")) eliminar.mutate(p.id); }}
                              className="text-gray-400 hover:text-red-500" title="Eliminar">
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                        {p.estado === "aprobada" && (
                          <button onClick={() => setFacturando(p)} className="text-gray-400 hover:text-green-600" title="Registrar factura">
                            <DollarSign size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                  {expandedId === p.id && (
                    <tr key={`det-${p.id}`}>
                      <td colSpan={9} className="bg-blue-50 px-6 py-4 border-b border-gray-200">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-gray-500">
                              {["Planilla", "Fecha", "Local", "Nacional", "P. local", "P. nac.", "Valor total"].map((h) => (
                                <th key={h} className="text-left py-1 font-medium uppercase tracking-wide">{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {p.planillas.map((pl) => (
                              <tr key={pl.id}>
                                <td className="py-1 font-mono">{pl.planilla}</td>
                                <td className="py-1">{pl.fecha_escaner ?? "—"}</td>
                                <td className="py-1">{pl.cantidad_local}</td>
                                <td className="py-1">{pl.cantidad_nacional}</td>
                                <td className="py-1"><CurrencyCell value={pl.precio_local} /></td>
                                <td className="py-1"><CurrencyCell value={pl.precio_nac} /></td>
                                <td className="py-1 font-medium"><CurrencyCell value={pl.valor_total} /></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {facturando && (
        <RegistrarFacturaModal
          prefactura={facturando}
          onClose={() => setFacturando(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["pc-prefacturas"] });
            qc.invalidateQueries({ queryKey: ["pc-cxp"] });
            setFacturando(null);
          }}
        />
      )}
      {ajustando && (
        <AjustarMontoModal
          prefactura={ajustando}
          onClose={() => setAjustando(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["pc-prefacturas"] });
            setAjustando(null);
          }}
        />
      )}
    </div>
  );
}

function AjustarMontoModal({
  prefactura, onClose, onSaved,
}: {
  prefactura: PrefacturaCourier; onClose: () => void; onSaved: () => void;
}) {
  const [valorAjustado, setValorAjustado] = useState<string>(
    prefactura.valor_ajustado != null ? String(prefactura.valor_ajustado) : String(prefactura.valor_total)
  );
  const [notasAjuste, setNotasAjuste] = useState(prefactura.notas_ajuste ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await pagosApi.ajustarMonto(prefactura.id, {
        valor_ajustado: valorAjustado === "" ? null : +valorAjustado,
        notas_ajuste: notasAjuste || null,
      });
      onSaved();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Error al ajustar el monto");
    } finally {
      setSaving(false);
    }
  }

  async function handleRevertir() {
    setSaving(true);
    setError("");
    try {
      await pagosApi.ajustarMonto(prefactura.id, { valor_ajustado: null, notas_ajuste: null });
      onSaved();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Error al revertir el ajuste");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Ajustar monto a pagar</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {prefactura.mensajero_nombre ?? prefactura.cod_mensajero} · Calculado: ${fmt.format(prefactura.valor_total)}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Monto real a pagar *</label>
            <input type="number" required min={0} value={valorAjustado}
              onChange={(e) => setValorAjustado(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas del ajuste</label>
            <textarea value={notasAjuste} onChange={(e) => setNotasAjuste(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" rows={3}
              placeholder="Motivo del ajuste (opcional)" />
          </div>
          <div className="flex justify-between gap-3 pt-2">
            {prefactura.valor_ajustado != null ? (
              <button type="button" disabled={saving} onClick={handleRevertir}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg disabled:opacity-60">
                Revertir a calculado
              </button>
            ) : <span />}
            <div className="flex gap-3">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
              <button type="submit" disabled={saving}
                className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
                {saving ? "Guardando..." : "Guardar ajuste"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function RegistrarFacturaModal({
  prefactura, onClose, onSaved,
}: {
  prefactura: PrefacturaCourier; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState({
    numero_factura: "",
    fecha_emision: HOY_STR,
    fecha_vencimiento: new Date(HOY.getTime() + 30 * 86400000).toISOString().slice(0, 10),
    valor_total: prefactura.valor_a_pagar,
    notas: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await pagosApi.registrarFactura(prefactura.id, {
        ...form,
        notas: form.notas || null,
      });
      onSaved();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Error al registrar la factura");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Registrar factura del proveedor</h2>
            <p className="text-xs text-gray-500 mt-0.5">{prefactura.mensajero_nombre ?? prefactura.cod_mensajero}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Número de factura *</label>
            <input required value={form.numero_factura}
              onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha emisión</label>
              <input type="date" value={form.fecha_emision}
                onChange={(e) => setForm({ ...form, fecha_emision: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento *</label>
              <input type="date" required value={form.fecha_vencimiento}
                onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Valor factura *</label>
            <input type="number" required min={1} value={form.valor_total}
              onChange={(e) => setForm({ ...form, valor_total: +e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas</label>
            <input value={form.notas} onChange={(e) => setForm({ ...form, notas: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Registrar factura CxP"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Tab: Cuentas por Pagar ────────────────────────────────────────────────────

function CxpTab({ qc }: { qc: ReturnType<typeof useQueryClient> }) {
  const [estado, setEstado] = useState<string>("");
  const [pagando, setPagando] = useState<FacturaCourierCxp | null>(null);
  const [editando, setEditando] = useState<FacturaCourierCxp | null>(null);

  const { data: cxp = [], isLoading } = useQuery({
    queryKey: ["pc-cxp", estado],
    queryFn: () => pagosApi.listarCxp(estado ? { estado } : undefined).then((r) => r.data),
  });

  const totalPendiente = cxp.filter((c) => c.estado !== "pagada").reduce((s, c) => s + c.valor_total, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <select value={estado} onChange={(e) => setEstado(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
          <option value="">Todas</option>
          <option value="pendiente">Pendiente</option>
          <option value="vencida">Vencida</option>
          <option value="pagada">Pagada</option>
        </select>
        <p className="text-sm text-gray-500">Saldo pendiente: <span className="font-semibold text-gray-900">${fmt.format(totalPendiente)}</span></p>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : cxp.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin cuentas por pagar</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["N° Factura", "Courier", "Emisión", "Vencimiento", "Valor", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cxp.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.numero_factura}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium text-gray-900">{c.mensajero_nombre ?? c.cod_mensajero}</p>
                  </td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{c.fecha_emision ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600 text-xs">{c.fecha_vencimiento}</td>
                  <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={c.valor_total} /></td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_CXP_STYLE[c.estado]}`}>{c.estado}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button onClick={() => setEditando(c)} className="text-gray-400 hover:text-blue-600" title="Editar">
                        <Pencil size={14} />
                      </button>
                      {c.estado !== "pagada" && (
                        <button onClick={() => setPagando(c)} className="text-gray-400 hover:text-green-600" title="Marcar pagada">
                          <DollarSign size={14} />
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

      {pagando && (
        <PagarCxpModal
          cxp={pagando}
          onClose={() => setPagando(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["pc-cxp"] }); setPagando(null); }}
        />
      )}
      {editando && (
        <EditarCxpModal
          cxp={editando}
          onClose={() => setEditando(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["pc-cxp"] }); setEditando(null); }}
        />
      )}
    </div>
  );
}

function PagarCxpModal({ cxp, onClose, onSaved }: { cxp: FacturaCourierCxp; onClose: () => void; onSaved: () => void }) {
  const [fechaPago, setFechaPago] = useState(HOY_STR);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await pagosApi.pagarCxp(cxp.id, { fecha_pago: fechaPago });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold">Marcar como pagada</h2>
            <p className="text-xs text-gray-500 mt-0.5">{cxp.numero_factura} · ${fmt.format(cxp.valor_total)}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha de pago *</label>
            <input type="date" required value={fechaPago} onChange={(e) => setFechaPago(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Marcar pagada"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditarCxpModal({ cxp, onClose, onSaved }: { cxp: FacturaCourierCxp; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    numero_factura: cxp.numero_factura,
    fecha_emision: cxp.fecha_emision ?? "",
    fecha_vencimiento: cxp.fecha_vencimiento,
    valor_total: cxp.valor_total,
    estado: cxp.estado,
    notas: cxp.notas ?? "",
  });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await pagosApi.editarCxp(cxp.id, form);
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h2 className="text-base font-semibold">Editar cuenta por pagar</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={16} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Número de factura</label>
            <input value={form.numero_factura} onChange={(e) => setForm({ ...form, numero_factura: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha emisión</label>
              <input type="date" value={form.fecha_emision} onChange={(e) => setForm({ ...form, fecha_emision: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento</label>
              <input type="date" value={form.fecha_vencimiento} onChange={(e) => setForm({ ...form, fecha_vencimiento: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Valor total</label>
            <input type="number" value={form.valor_total} onChange={(e) => setForm({ ...form, valor_total: +e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Estado</label>
            <select value={form.estado} onChange={(e) => setForm({ ...form, estado: e.target.value as any })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option value="pendiente">Pendiente</option>
              <option value="vencida">Vencida</option>
              <option value="pagada">Pagada</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas</label>
            <input value={form.notas} onChange={(e) => setForm({ ...form, notas: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Guardar cambios"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
