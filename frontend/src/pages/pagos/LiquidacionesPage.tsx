import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, DollarSign, Trash2, Plus, Rows3 } from "lucide-react";
import { gestionesApi } from "@/api/gestiones";
import { laboresApi } from "@/api/labores";
import { liqApi, type Pendiente, type Liquidacion } from "@/api/liquidaciones";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { PlanillaResumen, ResumenLabores } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const METODOS = ["efectivo","transferencia","cheque","tarjeta","otros"];

const TIPO_LABEL: Record<string, string> = {
  mensajero: "Mensajero",
  alistamiento: "Alistamiento",
  conductor: "Conductor",
  courier_externo: "Courier Ext.",
  transportadora: "Transportadora",
};
const TIPO_BADGE: Record<string, string> = {
  alistamiento: "bg-indigo-100 text-indigo-800",
  conductor: "bg-sky-100 text-sky-800",
  courier_externo: "bg-purple-100 text-purple-800",
  transportadora: "bg-orange-100 text-orange-800",
};

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

// Rango de fechas del mes seleccionado, en YYYY-MM-DD, sin pasar por toISOString
// (evita el desfase de timezone al construir Date con new Date(anio, mes, 0)).
function rangoMes(mes: number, anio: number): { desde: string; hasta: string } {
  const ultimoDia = new Date(anio, mes, 0).getDate();
  return {
    desde: `${anio}-${pad2(mes)}-01`,
    hasta: `${anio}-${pad2(mes)}-${pad2(ultimoDia)}`,
  };
}

type Tab = "pendientes" | "liquidaciones";

const ESTADO_STYLE: Record<string, string> = {
  generada:  "bg-yellow-50 text-yellow-700",
  aprobada:  "bg-blue-50 text-blue-700",
  pagada:    "bg-green-50 text-green-700",
};

export function LiquidacionesPage() {
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Gestión de Pagos — Personal Operativo</h1>
          <p className="text-sm text-gray-500 mt-0.5">{MESES[mes - 1]} {anio}</p>
        </div>
        <div className="flex items-center gap-2">
          <select value={mes} onChange={(e) => setMes(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
            {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <input type="number" value={anio} onChange={(e) => setAnio(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20" />
        </div>
      </div>

      <LiquidacionesPanel mes={mes} anio={anio} />
    </div>
  );
}

export function LiquidacionesPanel({ mes, anio, soloSeriales = false }: { mes: number; anio: number; soloSeriales?: boolean }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("pendientes");
  const [generando, setGenerando] = useState<Pendiente | null>(null);
  const [pagando, setPagando] = useState<Liquidacion | null>(null);

  const { data: pendientes = [], isLoading: loadPend } = useQuery({
    queryKey: ["liq-pendientes", mes, anio],
    queryFn: () => liqApi.pendientes(mes, anio).then((r) => r.data),
    enabled: tab === "pendientes",
  });

  const { data: liquidaciones = [], isLoading: loadLiq } = useQuery({
    queryKey: ["liquidaciones", mes, anio],
    queryFn: () => liqApi.list({ mes, anio }).then((r) => r.data),
    enabled: tab === "liquidaciones",
  });

  const aprobar = useMutation({
    mutationFn: (id: number) => liqApi.aprobar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["liquidaciones"] }),
  });
  const eliminar = useMutation({
    mutationFn: (id: number) => liqApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["liquidaciones"] });
      qc.invalidateQueries({ queryKey: ["liq-pendientes"] });
    },
  });

  const totalPendiente = pendientes.filter((p) => !p.ya_liquidado).reduce((s, p) => s + p.total_pendiente, 0);
  const totalGenerado = liquidaciones.reduce((s, l) => s + l.total_a_pagar, 0);

  return (
    <div>
      {tab === "pendientes" && (
        <p className="text-sm text-gray-500 mb-2">
          Pendiente total: <span className="font-medium text-gray-800">${fmt.format(totalPendiente)}</span>
        </p>
      )}
      {tab === "liquidaciones" && (
        <p className="text-sm text-gray-500 mb-2">
          Total generado: <span className="font-medium text-gray-800">${fmt.format(totalGenerado)}</span>
        </p>
      )}
      <div className="flex border-b border-gray-200 mb-4">
        {(["pendientes", "liquidaciones"] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t === "pendientes" ? "Pendientes de liquidar" : "Liquidaciones generadas"}
          </button>
        ))}
      </div>

      {tab === "pendientes" && (
        <>
          {loadPend ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : pendientes.length === 0 ? <div className="text-center py-16 text-gray-400">Sin seriales pendientes en este período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {(soloSeriales
                      ? ["Personal","Seriales","Monto seriales","Total","Estado","",""]
                      : ["Personal","Seriales","Monto seriales","Horas","Labores","Total","Estado","",""]
                    ).map((h, i) => (
                      <th key={i} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pendientes.map((p) => (
                    <PendienteRow key={p.personal_id} p={p} mes={mes} anio={anio} soloSeriales={soloSeriales} onGenerar={() => setGenerando(p)} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === "liquidaciones" && (
        <>
          {loadLiq ? <div className="text-center py-16 text-gray-500">Cargando...</div>
          : liquidaciones.length === 0 ? <div className="text-center py-16 text-gray-400">Sin liquidaciones en este período</div>
          : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {(soloSeriales
                      ? ["N° Liquidación","Período","Entregas","Bonif./Desc.","Total","Estado","Pago prog.",""]
                      : ["N° Liquidación","Período","Entregas","Horas","Bonif./Desc.","Total","Estado","Pago prog.",""]
                    ).map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {liquidaciones.map((l) => (
                    <tr key={l.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{l.numero_liquidacion}</td>
                      <td className="px-4 py-3 text-gray-600">{MESES[l.periodo_mes - 1]} {l.periodo_anio}</td>
                      <td className="px-4 py-3 text-gray-600">{l.cantidad_entregas} · <CurrencyCell value={l.total_entregas} /></td>
                      {!soloSeriales && (
                        <td className="px-4 py-3 text-gray-600"><CurrencyCell value={l.total_horas} /></td>
                      )}
                      <td className="px-4 py-3 text-gray-600">+<CurrencyCell value={l.bonificaciones} /> -<CurrencyCell value={l.descuentos} /></td>
                      <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={l.total_a_pagar} /></td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${ESTADO_STYLE[l.estado] ?? ""}`}>{l.estado}</span>
                      </td>
                      <td className="px-4 py-3 text-gray-600 text-xs">
                        {l.fecha_pago_real ?? l.fecha_pago_programada}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {l.estado === "generada" && (
                            <button onClick={() => aprobar.mutate(l.id)}
                              className="text-gray-400 hover:text-blue-600" title="Aprobar">
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {l.estado !== "pagada" && (
                            <button onClick={() => setPagando(l)}
                              className="text-gray-400 hover:text-green-600" title="Pagar">
                              <DollarSign size={15} />
                            </button>
                          )}
                          {l.estado !== "pagada" && (
                            <button onClick={() => { if (confirm("¿Eliminar liquidación? Se revierten los seriales a pendiente.")) eliminar.mutate(l.id); }}
                              className="text-gray-400 hover:text-red-500">
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

      {generando && (
        <GenerarLiquidacionModal
          pendiente={generando} mes={mes} anio={anio}
          onClose={() => setGenerando(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["liq-pendientes"] });
            qc.invalidateQueries({ queryKey: ["liquidaciones"] });
            setGenerando(null);
            setTab("liquidaciones");
          }}
        />
      )}
      {pagando && (
        <PagarLiquidacionModal
          liquidacion={pagando}
          onClose={() => setPagando(null)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["liquidaciones"] }); setPagando(null); }}
        />
      )}
    </div>
  );
}

// ── Fila expandible de pendiente ────────────────────────────────────────────────

function PendienteRow({ p, mes, anio, soloSeriales, onGenerar }: {
  p: Pendiente; mes: number; anio: number; soloSeriales: boolean; onGenerar: () => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const esMensajero = p.tipo_personal === "mensajero";
  const { desde, hasta } = rangoMes(mes, anio);

  const { data: planillas = [], isLoading: cargandoPlanillas } = useQuery({
    queryKey: ["pago-planillas", p.codigo, mes, anio],
    queryFn: () => gestionesApi.planillasResumen({ cod_men: p.codigo, fecha_desde: desde, fecha_hasta: hasta }).then((r) => r.data),
    enabled: expandido && esMensajero,
  });

  const { data: diario = [], isLoading: cargandoDiario } = useQuery({
    queryKey: ["pago-diario", p.personal_id, mes, anio],
    queryFn: () => laboresApi.resumenDiario({ personal_id: p.personal_id, mes, anio, aprobado: true, liquidado: false }).then((r) => r.data),
    enabled: expandido && !esMensajero,
  });

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-4 py-3">
          <p className="font-medium text-gray-900">{p.nombre_completo}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <p className="text-xs text-gray-400">{p.codigo}</p>
            {!esMensajero && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${TIPO_BADGE[p.tipo_personal] ?? "bg-gray-100 text-gray-600"}`}>
                {TIPO_LABEL[p.tipo_personal] ?? p.tipo_personal}
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-gray-600">{p.total_seriales}</td>
        <td className="px-4 py-3 text-gray-700"><CurrencyCell value={p.total_mensajero} /></td>
        {!soloSeriales && (
          <>
            <td className="px-4 py-3 text-gray-600">{fmt.format(p.total_horas)}h · <CurrencyCell value={p.total_horas_monto} /></td>
            <td className="px-4 py-3 text-gray-600">{p.total_labores} · <CurrencyCell value={p.total_labores_monto} /></td>
          </>
        )}
        <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={p.total_pendiente} /></td>
        <td className="px-4 py-3">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${p.ya_liquidado ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
            {p.ya_liquidado ? "Liquidado" : "Pendiente"}
          </span>
        </td>
        <td className="px-4 py-3">
          <button
            onClick={() => setExpandido((v) => !v)}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors ${expandido ? "border-primary text-primary bg-blue-50" : "border-gray-300 text-gray-500 hover:bg-gray-50"}`}
            title="Ver registros detallados"
          >
            <Rows3 size={13} />
            {expandido ? "Ocultar" : "Registros"}
          </button>
        </td>
        <td className="px-4 py-3">
          {!p.ya_liquidado && (
            <button onClick={onGenerar}
              className="flex items-center gap-1 text-xs bg-primary hover:bg-primary-hover text-white px-2 py-1 rounded">
              <Plus size={12} /> Generar
            </button>
          )}
        </td>
      </tr>

      {expandido && (
        <tr>
          <td colSpan={soloSeriales ? 7 : 9} className="bg-gray-50/60 border-t border-gray-100 px-4 py-3">
            {esMensajero ? (
              cargandoPlanillas ? (
                <p className="text-xs text-gray-400">Cargando planillas…</p>
              ) : planillas.length === 0 ? (
                <p className="text-xs text-gray-400">Sin planillas en este período.</p>
              ) : (
                <PlanillasDetalle planillas={planillas} />
              )
            ) : (
              cargandoDiario ? (
                <p className="text-xs text-gray-400">Cargando registros diarios…</p>
              ) : diario.length === 0 ? (
                <p className="text-xs text-gray-400">Sin horas/labores aprobadas pendientes en este período.</p>
              ) : (
                <DiarioDetalle diario={diario} />
              )
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function PlanillasDetalle({ planillas }: { planillas: PlanillaResumen[] }) {
  return (
    <table className="w-full text-xs bg-white border border-gray-200 rounded-lg overflow-hidden">
      <thead className="bg-gray-50 border-b border-gray-100">
        <tr>
          <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Fecha</th>
          <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Planilla</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Seriales</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Valor pagado</th>
          <th className="px-3 py-1.5 text-center text-gray-500 font-medium">Estado</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {planillas.map((pl) => (
          <tr key={pl.planilla}>
            <td className="px-3 py-1.5 text-gray-700">{pl.fecha_escaner ?? "—"}</td>
            <td className="px-3 py-1.5 font-mono text-gray-700">{pl.planilla}</td>
            <td className="px-3 py-1.5 text-right text-gray-700">{pl.total_seriales}</td>
            <td className="px-3 py-1.5 text-right text-gray-700">${fmt.format(pl.total_mensajero)}</td>
            <td className="px-3 py-1.5 text-center">
              <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${pl.bloqueada ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
                {pl.bloqueada ? "Cerrada" : "Abierta"}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DiarioDetalle({ diario }: { diario: (ResumenLabores & { fecha: string })[] }) {
  return (
    <table className="w-full text-xs bg-white border border-gray-200 rounded-lg overflow-hidden">
      <thead className="bg-gray-50 border-b border-gray-100">
        <tr>
          <th className="px-3 py-1.5 text-left text-gray-500 font-medium">Fecha</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Horas</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Monto horas</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Labores</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Monto labores</th>
          <th className="px-3 py-1.5 text-right text-gray-500 font-medium">Total</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-50">
        {diario.map((d) => (
          <tr key={d.fecha}>
            <td className="px-3 py-1.5 text-gray-700">{d.fecha}</td>
            <td className="px-3 py-1.5 text-right text-gray-700">{fmt.format(d.total_horas)}h</td>
            <td className="px-3 py-1.5 text-right text-gray-700">${fmt.format(d.total_horas_monto)}</td>
            <td className="px-3 py-1.5 text-right text-gray-700">{d.total_labores}</td>
            <td className="px-3 py-1.5 text-right text-gray-700">${fmt.format(d.total_labores_monto)}</td>
            <td className="px-3 py-1.5 text-right font-semibold text-gray-800">${fmt.format(d.total_general)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Modal generar liquidación ──────────────────────────────────────────────────

export function GenerarLiquidacionModal({ pendiente, mes, anio, onClose, onSaved }: {
  pendiente: Pendiente; mes: number; anio: number; onClose: () => void; onSaved: () => void;
}) {
  const hoy = new Date();
  const diasPago = new Date(hoy.getFullYear(), hoy.getMonth(), 8).toISOString().slice(0, 10);
  const [form, setForm] = useState({ fecha_pago_programada: diasPago, bonificaciones: 0, descuentos: 0, observaciones: "" });
  const [saving, setSaving] = useState(false);
  const total = pendiente.total_pendiente + form.bonificaciones - form.descuentos;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await liqApi.generar({
        personal_id: pendiente.personal_id,
        periodo_mes: mes, periodo_anio: anio,
        ...form, observaciones: form.observaciones || null,
      });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Generar liquidación</h2>
          <p className="text-xs text-gray-500 mt-0.5">{pendiente.nombre_completo} · {MESES[mes - 1]} {anio}</p>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
            <div className="flex justify-between"><span className="text-gray-600">Seriales ({pendiente.total_seriales})</span><span className="font-medium">${fmt.format(pendiente.total_mensajero)}</span></div>
            <div className="flex justify-between"><span className="text-gray-600">Horas</span><span>${fmt.format(pendiente.total_horas_monto)}</span></div>
            <div className="flex justify-between"><span className="text-gray-600">Labores</span><span>${fmt.format(pendiente.total_labores_monto)}</span></div>
            <div className="flex justify-between"><span className="text-gray-600">Subsidio transporte</span><span>${fmt.format(pendiente.total_subsidio ?? 0)}</span></div>
            <div className="flex justify-between border-t pt-1 mt-1 font-semibold"><span>Subtotal</span><span>${fmt.format(pendiente.total_pendiente)}</span></div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Bonificación</label>
              <input type="number" min={0} value={form.bonificaciones}
                onChange={(e) => setForm({ ...form, bonificaciones: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Descuento</label>
              <input type="number" min={0} value={form.descuentos}
                onChange={(e) => setForm({ ...form, descuentos: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha de pago programada *</label>
            <input type="date" required value={form.fecha_pago_programada}
              onChange={(e) => setForm({ ...form, fecha_pago_programada: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <p className="text-sm font-semibold text-gray-900">
            Total a pagar: <span className="text-primary">${fmt.format(total)}</span>
          </p>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Generando..." : "Generar liquidación"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal pagar liquidación ────────────────────────────────────────────────────

function PagarLiquidacionModal({ liquidacion, onClose, onSaved }: {
  liquidacion: Liquidacion; onClose: () => void; onSaved: () => void;
}) {
  const HOY = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({ fecha_pago_real: HOY, metodo_pago: "transferencia", referencia_pago: "", observaciones: "" });
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await liqApi.pagar(liquidacion.id, { ...form, referencia_pago: form.referencia_pago || null, observaciones: form.observaciones || null });
      onSaved();
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="px-6 py-4 border-b">
          <h2 className="text-base font-semibold">Registrar pago</h2>
          <p className="text-xs text-gray-500 mt-0.5">{liquidacion.numero_liquidacion} · Total: ${fmt.format(liquidacion.total_a_pagar)}</p>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha de pago *</label>
              <input type="date" required value={form.fecha_pago_real}
                onChange={(e) => setForm({ ...form, fecha_pago_real: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Método *</label>
              <select required value={form.metodo_pago}
                onChange={(e) => setForm({ ...form, metodo_pago: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {METODOS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Referencia</label>
            <input value={form.referencia_pago} onChange={(e) => setForm({ ...form, referencia_pago: e.target.value })}
              placeholder="N° transferencia, cheque, etc."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">Cancelar</button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Registrar pago"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
