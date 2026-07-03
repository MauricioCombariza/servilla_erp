import { useState, useEffect, useRef, Fragment } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, CheckCircle, Trash2, X, FileDown, Pencil, ChevronDown, ChevronUp } from "lucide-react";
import { laboresApi } from "@/api/labores";
import { ordenesApi } from "@/api/ordenes";
import { liqApi, type Pendiente } from "@/api/liquidaciones";
import { GenerarLiquidacionModal } from "@/pages/pagos/LiquidacionesPage";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { generarPdfPegado } from "@/utils/pdfPegado";
import type { RegistroHoras, RegistroLabores, ResumenLabores } from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();
const HOY_STR = HOY.toISOString().slice(0, 10);

type Tab = "horas" | "labores" | "resumen";
type TipoLabor = "pegado_guia" | "transporte_completo" | "medio_transporte";

function hhmmToDecimal(v: string): number | null {
  const m = v.match(/^(\d+):([0-5]\d)$/);
  if (!m) return null;
  return parseInt(m[1]) + parseInt(m[2]) / 60;
}

function decimalToHhmm(v: number): string {
  const h = Math.floor(v);
  const m = Math.round((v - h) * 60);
  return m > 0 ? `${h} hr ${m} min` : `${h} hr`;
}

// ── Hook: carga tarifas al inicio ─────────────────────────────────────────────

function useTarifas() {
  const q1 = useQuery({
    queryKey: ["tarifa", "alistamiento_hora"],
    queryFn: () => laboresApi.getTarifa("alistamiento_hora").then(r => r.data.tarifa),
    staleTime: 60_000,
  });
  const q2 = useQuery({
    queryKey: ["tarifa", "pegado_guia"],
    queryFn: () => laboresApi.getTarifa("pegado_guia").then(r => r.data.tarifa),
    staleTime: 60_000,
  });
  const q3 = useQuery({
    queryKey: ["tarifa", "transporte_completo"],
    queryFn: () => laboresApi.getTarifa("transporte_completo").then(r => r.data.tarifa),
    staleTime: 60_000,
  });
  return {
    alistamiento: q1.data ?? 7960.9,
    pegado: q2.data ?? 11.54,
    transporte: q3.data ?? 8333,
  };
}

// ── Hook: personal lookup por código ─────────────────────────────────────────

function usePersonalLookup() {
  const [codigo, setCodigo] = useState("");
  const [info, setInfo] = useState<{ id: number; nombre_completo: string } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (codigo.length !== 4) {
      setInfo(null);
      setError(false);
      return;
    }
    laboresApi.lookupPersonalCodigo(codigo)
      .then(r => { setInfo(r.data); setError(false); })
      .catch(() => { setInfo(null); setError(true); });
  }, [codigo]);

  return { codigo, setCodigo, info, error, reset: () => { setCodigo(""); setInfo(null); setError(false); } };
}

// ── Página principal ─────────────────────────────────────────────────────────

export function LaboresPage() {
  const qc = useQueryClient();
  const tarifas = useTarifas();
  const [tab, setTab] = useState<Tab>("horas");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showHoraForm, setShowHoraForm] = useState(false);
  const [showLaborForm, setShowLaborForm] = useState(false);
  const [tipoLaborActivo, setTipoLaborActivo] = useState<TipoLabor>("pegado_guia");
  const [showPdfMenu, setShowPdfMenu] = useState(false);
  const [vistaDiaria, setVistaDiaria] = useState(false);
  const [expandidoDiario, setExpandidoDiario] = useState<string | null>(null);
  const [generandoLiq, setGenerandoLiq] = useState<Pendiente | null>(null);
  const pdfMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (pdfMenuRef.current && !pdfMenuRef.current.contains(e.target as Node)) {
        setShowPdfMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtros = { mes, anio };

  const { data: horas = [], isLoading: loadH } = useQuery({
    queryKey: ["labores-horas", mes, anio],
    queryFn: () => laboresApi.listHoras(filtros).then(r => r.data),
    enabled: tab === "horas",
  });

  const { data: labores = [], isLoading: loadL } = useQuery({
    queryKey: ["labores-labores", mes, anio],
    queryFn: () => laboresApi.listLabores(filtros).then(r => r.data),
    enabled: tab === "labores",
  });

  const { data: resumen = [] } = useQuery({
    queryKey: ["labores-resumen", mes, anio],
    queryFn: () => laboresApi.resumen(filtros).then(r => r.data),
    enabled: tab === "resumen" && !vistaDiaria,
  });

  const { data: resumenDiario = [] } = useQuery({
    queryKey: ["labores-resumen-diario", mes, anio],
    queryFn: () => laboresApi.resumenDiario(filtros).then(r => r.data),
    enabled: tab === "resumen" && vistaDiaria,
  });

  const { data: liqPendientes = [] } = useQuery({
    queryKey: ["liq-pendientes", mes, anio],
    queryFn: () => liqApi.pendientes(mes, anio).then(r => r.data),
    enabled: tab === "resumen" && !vistaDiaria,
  });
  const pendientesPorPersona = new Map(liqPendientes.map(p => [p.personal_id, p]));

  const invalidarTodoElPeriodo = () => {
    qc.invalidateQueries({ queryKey: ["labores-horas", mes, anio] });
    qc.invalidateQueries({ queryKey: ["labores-labores", mes, anio] });
    qc.invalidateQueries({ queryKey: ["labores-resumen", mes, anio] });
    qc.invalidateQueries({ queryKey: ["labores-resumen-diario", mes, anio] });
    qc.invalidateQueries({ queryKey: ["liq-pendientes", mes, anio] });
  };

  const aprobarHora = useMutation({
    mutationFn: (id: number) => laboresApi.aprobarHora(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-horas"] }),
  });
  const aprobarHorasLote = useMutation({
    mutationFn: () => laboresApi.aprobarHorasLote({ mes, anio }),
    onSuccess: invalidarTodoElPeriodo,
  });
  const aprobarLaboresLote = useMutation({
    mutationFn: () => laboresApi.aprobarLaboresLote({ mes, anio }),
    onSuccess: invalidarTodoElPeriodo,
  });
  const deleteHora = useMutation({
    mutationFn: (id: number) => laboresApi.deleteHora(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-horas"] }),
  });
  const aprobarLabor = useMutation({
    mutationFn: (id: number) => laboresApi.aprobarLabor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-labores"] }),
  });
  const deleteLabor = useMutation({
    mutationFn: (id: number) => laboresApi.deleteLabor(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labores-labores"] }),
  });

  const totalHoras = horas.reduce((s, h) => s + h.horas_trabajadas, 0);
  const totalHorasMonto = horas.reduce((s, h) => s + (h.total ?? h.horas_trabajadas * h.tarifa_hora), 0);
  const totalHorasDisplay = (() => {
    const h = Math.floor(totalHoras);
    const m = Math.round((totalHoras - h) * 60);
    return m > 0 ? `${h} hr ${m} min` : `${h} hr`;
  })();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Registro de Labores</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {MESES[mes - 1]} {anio} · {horas.length} horas · {labores.length} labores
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={mes} onChange={e => setMes(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm">
            {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <input type="number" value={anio} onChange={e => setAnio(+e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20" />
          {tab === "horas" && (
            <>
              {horas.some(h => !h.aprobado) && (
                <button
                  onClick={() => {
                    const pendientes = horas.filter(h => !h.aprobado).length;
                    if (confirm(`¿Aprobar ${pendientes} registro(s) de horas pendientes de ${MESES[mes - 1]} ${anio}?`)) {
                      aprobarHorasLote.mutate();
                    }
                  }}
                  disabled={aprobarHorasLote.isPending}
                  className="flex items-center gap-2 border border-green-300 text-green-700 hover:bg-green-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60">
                  <CheckCircle size={16} /> {aprobarHorasLote.isPending ? "Aprobando..." : "Aprobar todo"}
                </button>
              )}
              <button onClick={() => setShowHoraForm(true)}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                <Plus size={16} /> Registrar horas
              </button>
            </>
          )}
          {tab === "labores" && (
            <>
              {labores.some(l => l.tipo_labor === "pegado_guia") && (
                <div className="relative" ref={pdfMenuRef}>
                  <button
                    onClick={() => setShowPdfMenu(v => !v)}
                    className="flex items-center gap-2 border border-gray-300 text-gray-700 hover:bg-gray-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                    <FileDown size={16} /> PDF Pegado ▾
                  </button>
                  {showPdfMenu && (
                    <div className="absolute right-0 top-full mt-1 z-20 bg-white border border-gray-200 rounded-xl shadow-lg py-1 min-w-[180px]">
                      {[...new Set(
                        labores.filter(l => l.tipo_labor === "pegado_guia").map(l => l.fecha)
                      )].sort().map(fecha => (
                        <button
                          key={fecha}
                          onClick={() => {
                            const pegado = labores
                              .filter(l => l.tipo_labor === "pegado_guia" && l.fecha === fecha)
                              .map(l => ({
                                fecha: l.fecha,
                                personal_nombre: (l as RegistroLabores & { personal_nombre?: string }).personal_nombre ?? String(l.personal_id),
                                cantidad: l.cantidad,
                                tarifa_unitaria: tarifas.pegado,
                                total: l.cantidad * tarifas.pegado,
                              }));
                            generarPdfPegado(pegado, fecha);
                            setShowPdfMenu(false);
                          }}
                          className="flex items-center gap-2 w-full px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors">
                          <FileDown size={13} className="text-gray-400" /> {fecha}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {labores.some(l => !l.aprobado) && (
                <button
                  onClick={() => {
                    const pendientes = labores.filter(l => !l.aprobado).length;
                    if (confirm(`¿Aprobar ${pendientes} registro(s) de labores pendientes de ${MESES[mes - 1]} ${anio}?`)) {
                      aprobarLaboresLote.mutate();
                    }
                  }}
                  disabled={aprobarLaboresLote.isPending}
                  className="flex items-center gap-2 border border-green-300 text-green-700 hover:bg-green-50 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60">
                  <CheckCircle size={16} /> {aprobarLaboresLote.isPending ? "Aprobando..." : "Aprobar todo"}
                </button>
              )}
              <button onClick={() => setShowLaborForm(true)}
                className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                <Plus size={16} /> Registrar labor
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        {(["horas", "labores", "resumen"] as Tab[]).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"
            }`}>
            {t === "horas" ? "Registro Horas" : t === "labores" ? "Registro Labores" : "Resumen"}
          </button>
        ))}
      </div>

      {/* ── Tab Horas ── */}
      {tab === "horas" && (
        <>
          {horas.length > 0 && (
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total horas</p>
                <p className="text-xl font-semibold text-gray-900 mt-1">{totalHorasDisplay}</p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total a pagar</p>
                <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(totalHorasMonto)}</p>
              </div>
            </div>
          )}
          {loadH ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : horas.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin registros en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Personal", "Orden", "Tipo trabajo", "Horas", "Tarifa/h", "Total", "Estado", ""].map(h => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {horas.map(r => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.fecha}</td>
                      <td className="px-4 py-3 text-gray-800 text-xs">
                        {(r as RegistroHoras & { personal_nombre?: string }).personal_nombre ?? r.personal_id}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">
                        {(r as RegistroHoras & { orden_numero?: string }).orden_numero ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded text-xs">
                          {r.tipo_trabajo.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900">{r.horas_trabajadas}h</td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={r.tarifa_hora} /></td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <CurrencyCell value={r.total ?? r.horas_trabajadas * r.tarifa_hora} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          r.aprobado ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}>
                          {r.aprobado ? "Aprobado" : "Pendiente"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {!r.aprobado && (
                            <button onClick={() => aprobarHora.mutate(r.id)}
                              className="text-gray-400 hover:text-green-600 transition-colors" title="Aprobar">
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {!r.liquidado && (
                            <button onClick={() => { if (confirm("¿Eliminar este registro?")) deleteHora.mutate(r.id); }}
                              className="text-gray-400 hover:text-red-500 transition-colors">
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

      {/* ── Tab Labores ── */}
      {tab === "labores" && (
        <>
          {loadL ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : labores.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin registros en este período</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Fecha", "Personal", "Orden", "Tipo labor", "Cantidad", "Tarifa", "Total", "Estado", ""].map(h => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {labores.map(r => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.fecha}</td>
                      <td className="px-4 py-3 text-gray-800 text-xs">
                        {(r as RegistroLabores & { personal_nombre?: string }).personal_nombre ?? r.personal_id}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">
                        {(r as RegistroLabores & { orden_numero?: string }).orden_numero ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded text-xs">
                          {r.tipo_labor.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-900">{r.cantidad}</td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={r.tarifa_unitaria} /></td>
                      <td className="px-4 py-3 font-medium text-gray-900">
                        <CurrencyCell value={r.total ?? r.cantidad * r.tarifa_unitaria} />
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          r.aprobado ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                        }`}>
                          {r.aprobado ? "Aprobado" : "Pendiente"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {!r.aprobado && (
                            <button onClick={() => aprobarLabor.mutate(r.id)}
                              className="text-gray-400 hover:text-green-600 transition-colors" title="Aprobar">
                              <CheckCircle size={15} />
                            </button>
                          )}
                          {!r.liquidado && (
                            <button onClick={() => { if (confirm("¿Eliminar este registro?")) deleteLabor.mutate(r.id); }}
                              className="text-gray-400 hover:text-red-500 transition-colors">
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

      {/* ── Tab Resumen ── */}
      {tab === "resumen" && (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm text-gray-600">Vista:</span>
            <button
              onClick={() => setVistaDiaria(false)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${!vistaDiaria ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
              Mes
            </button>
            <button
              onClick={() => setVistaDiaria(true)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${vistaDiaria ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}>
              Diario
            </button>
          </div>

          {!vistaDiaria && (
            resumen.length === 0 ? (
              <div className="text-center py-16 text-gray-400">Sin datos en este período</div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      {["Personal", "Horas", "Monto horas", "Labores", "Monto labores", "Subsidio transp.", "Total", "", ""].map((h, i) => (
                        <th key={i} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {resumen.map(r => (
                      <PersonaMesRow
                        key={r.personal_id}
                        r={r}
                        mes={mes}
                        anio={anio}
                        pendiente={pendientesPorPersona.get(r.personal_id)}
                        onLiquidar={setGenerandoLiq}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {vistaDiaria && (
            resumenDiario.length === 0 ? (
              <div className="text-center py-16 text-gray-400">Sin datos en este período</div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      {["Fecha", "Personal", "Horas", "Monto horas", "Labores", "Monto labores", "Subsidio transp.", "Total", ""].map(h => (
                        <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {resumenDiario.map((r, i) => {
                      const key = `${r.personal_id}-${r.fecha}`;
                      const expandido = expandidoDiario === key;
                      return (
                        <Fragment key={`${key}-${i}`}>
                          <tr className={`border-b border-gray-100 hover:bg-gray-50 ${expandido ? "bg-blue-50/40" : ""}`}>
                            <td className="px-4 py-3 font-mono text-xs text-gray-500">{r.fecha}</td>
                            <td className="px-4 py-3 font-medium text-gray-900">{r.nombre_completo}</td>
                            <td className="px-4 py-3 text-gray-600">{decimalToHhmm(r.total_horas)}</td>
                            <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_horas_monto} /></td>
                            <td className="px-4 py-3 text-gray-600">{r.total_labores}</td>
                            <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_labores_monto} /></td>
                            <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_subsidio} /></td>
                            <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={r.total_general} /></td>
                            <td className="px-4 py-3">
                              <button
                                onClick={() => setExpandidoDiario(expandido ? null : key)}
                                className="text-gray-400 hover:text-primary transition-colors"
                                title="Ver y editar registros"
                              >
                                {expandido ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                              </button>
                            </td>
                          </tr>
                          {expandido && (
                            <tr>
                              <td colSpan={9} className="bg-gray-50 px-6 py-4 border-b border-gray-200">
                                <DetalleFilaDiaria
                                  personalId={r.personal_id}
                                  fecha={r.fecha}
                                  mes={mes}
                                  anio={anio}
                                  onSaved={() => qc.invalidateQueries({ queryKey: ["labores-resumen-diario"] })}
                                />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          )}
        </>
      )}

      {/* Modales */}
      {showHoraForm && (
        <RegistroHoraForm
          onClose={() => setShowHoraForm(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["labores-horas"] }); setShowHoraForm(false); }}
        />
      )}
      {showLaborForm && (
        <RegistroLaborForm
          tipoInicial={tipoLaborActivo}
          onTipoChange={setTipoLaborActivo}
          onClose={() => setShowLaborForm(false)}
          onSaved={() => { qc.invalidateQueries({ queryKey: ["labores-labores"] }); setShowLaborForm(false); }}
        />
      )}
      {generandoLiq && (
        <GenerarLiquidacionModal
          pendiente={generandoLiq} mes={mes} anio={anio}
          onClose={() => setGenerandoLiq(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["labores-resumen", mes, anio] });
            qc.invalidateQueries({ queryKey: ["liq-pendientes", mes, anio] });
            setGenerandoLiq(null);
          }}
        />
      )}
    </div>
  );
}

// ── Fila expandible de Resumen "Mes" (desglose diario por persona) ───────────

function PersonaMesRow({ r, mes, anio, pendiente, onLiquidar }: {
  r: ResumenLabores; mes: number; anio: number;
  pendiente: Pendiente | undefined; onLiquidar: (p: Pendiente) => void;
}) {
  const qc = useQueryClient();
  const [expandido, setExpandido] = useState(false);
  const [expandidoFecha, setExpandidoFecha] = useState<string | null>(null);

  const { data: diario = [], isLoading } = useQuery({
    queryKey: ["labores-resumen-diario-persona", r.personal_id, mes, anio],
    queryFn: () => laboresApi.resumenDiario({ personal_id: r.personal_id, mes, anio }).then(res => res.data),
    enabled: expandido,
  });

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-4 py-3">
          <p className="font-medium text-gray-900">{r.nombre_completo}</p>
          <p className="text-xs text-gray-400 font-mono">{r.codigo}</p>
        </td>
        <td className="px-4 py-3 text-gray-600">{decimalToHhmm(r.total_horas)}</td>
        <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_horas_monto} /></td>
        <td className="px-4 py-3 text-gray-600">{r.total_labores}</td>
        <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_labores_monto} /></td>
        <td className="px-4 py-3 text-gray-700"><CurrencyCell value={r.total_subsidio} /></td>
        <td className="px-4 py-3 font-semibold text-gray-900"><CurrencyCell value={r.total_general} /></td>
        <td className="px-4 py-3">
          {pendiente?.ya_liquidado ? (
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">Liquidado</span>
          ) : pendiente && pendiente.total_pendiente > 0 ? (
            <button onClick={() => onLiquidar(pendiente)}
              className="flex items-center gap-1 text-xs bg-primary hover:bg-primary-hover text-white px-2 py-1 rounded whitespace-nowrap">
              <Plus size={12} /> Liquidar mes
            </button>
          ) : null}
        </td>
        <td className="px-4 py-3">
          <button
            onClick={() => setExpandido(v => !v)}
            className="text-gray-400 hover:text-primary transition-colors"
            title="Ver desglose diario"
          >
            {expandido ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </td>
      </tr>
      {expandido && (
        <tr>
          <td colSpan={9} className="bg-gray-50 px-6 py-4 border-b border-gray-200">
            {isLoading ? (
              <p className="text-xs text-gray-400">Cargando…</p>
            ) : diario.length === 0 ? (
              <p className="text-xs text-gray-400">Sin registros en este período.</p>
            ) : (
              <table className="w-full text-xs bg-white border border-gray-200 rounded-lg overflow-hidden">
                <thead className="bg-gray-100">
                  <tr>
                    {["Fecha", "Horas", "Monto horas", "Labores", "Monto labores", "Subsidio transp.", "Total", ""].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-medium text-gray-600">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {diario.map(d => {
                    const exp = expandidoFecha === d.fecha;
                    return (
                      <Fragment key={d.fecha}>
                        <tr className="border-t border-gray-100 hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono text-gray-500">{d.fecha}</td>
                          <td className="px-3 py-2">{decimalToHhmm(d.total_horas)}</td>
                          <td className="px-3 py-2"><CurrencyCell value={d.total_horas_monto} /></td>
                          <td className="px-3 py-2">{d.total_labores}</td>
                          <td className="px-3 py-2"><CurrencyCell value={d.total_labores_monto} /></td>
                          <td className="px-3 py-2"><CurrencyCell value={d.total_subsidio} /></td>
                          <td className="px-3 py-2 font-semibold"><CurrencyCell value={d.total_general} /></td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => setExpandidoFecha(exp ? null : d.fecha)}
                              className="text-gray-400 hover:text-primary transition-colors"
                              title="Ver y editar registros"
                            >
                              {exp ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                            </button>
                          </td>
                        </tr>
                        {exp && (
                          <tr>
                            <td colSpan={8} className="bg-gray-50/60 px-4 py-3">
                              <DetalleFilaDiaria
                                personalId={r.personal_id}
                                fecha={d.fecha}
                                mes={mes}
                                anio={anio}
                                onSaved={() => qc.invalidateQueries({ queryKey: ["labores-resumen-diario-persona", r.personal_id, mes, anio] })}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ── Detalle expandible fila diaria ───────────────────────────────────────────

function DetalleFilaDiaria({
  personalId, fecha, mes, anio, onSaved,
}: {
  personalId: number; fecha: string; mes: number; anio: number; onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [editHora, setEditHora] = useState<RegistroHoras | null>(null);
  const [editLabor, setEditLabor] = useState<RegistroLabores | null>(null);

  const { data: todasHoras = [], isLoading: lH } = useQuery({
    queryKey: ["labores-horas", mes, anio, personalId],
    queryFn: () => laboresApi.listHoras({ personal_id: personalId, mes, anio }).then(r => r.data),
    staleTime: 30_000,
  });

  const { data: todasLabores = [], isLoading: lL } = useQuery({
    queryKey: ["labores-labores", mes, anio, personalId],
    queryFn: () => laboresApi.listLabores({ personal_id: personalId, mes, anio }).then(r => r.data),
    staleTime: 30_000,
  });

  const horas = todasHoras.filter(h => h.fecha === fecha);
  const labores = todasLabores.filter(l => l.fecha === fecha);

  const deleteHora = useMutation({
    mutationFn: (id: number) => laboresApi.deleteHora(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["labores-horas", mes, anio, personalId] });
      onSaved();
    },
  });
  const deleteLabor = useMutation({
    mutationFn: (id: number) => laboresApi.deleteLabor(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["labores-labores", mes, anio, personalId] });
      onSaved();
    },
  });

  if (lH || lL) return <p className="text-xs text-gray-400 py-2">Cargando…</p>;
  if (!horas.length && !labores.length) return <p className="text-xs text-gray-400 py-2">Sin registros para esta fecha.</p>;

  return (
    <div className="space-y-4">
      {horas.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Horas trabajadas</p>
          <table className="w-full text-xs border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-gray-100">
              <tr>
                {["Horas", "Tarifa", "Total", "Tipo", "Estado", ""].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {horas.map(h => (
                <tr key={h.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2">{decimalToHhmm(h.horas_trabajadas)}</td>
                  <td className="px-3 py-2"><CurrencyCell value={h.tarifa_hora} /></td>
                  <td className="px-3 py-2 font-medium"><CurrencyCell value={h.total ?? h.horas_trabajadas * h.tarifa_hora} /></td>
                  <td className="px-3 py-2 text-gray-500">{h.tipo_trabajo}</td>
                  <td className="px-3 py-2">
                    {h.liquidado
                      ? <span className="text-purple-600 font-medium">Liquidado</span>
                      : h.aprobado
                        ? <span className="text-green-600 font-medium">Aprobado</span>
                        : <span className="text-yellow-600">Pendiente</span>
                    }
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => setEditHora(h)}
                        disabled={h.aprobado || h.liquidado}
                        className="text-blue-500 hover:text-blue-700 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Editar"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => { if (confirm("¿Eliminar este registro de horas?")) deleteHora.mutate(h.id); }}
                        disabled={h.aprobado || h.liquidado}
                        className="text-red-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Eliminar"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {labores.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Labores</p>
          <table className="w-full text-xs border border-gray-200 rounded-lg overflow-hidden">
            <thead className="bg-gray-100">
              <tr>
                {["Tipo", "Cantidad", "Tarifa", "Total", "Estado", ""].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labores.map(l => (
                <tr key={l.id} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2 text-gray-500">{l.tipo_labor}</td>
                  <td className="px-3 py-2">{l.cantidad}</td>
                  <td className="px-3 py-2"><CurrencyCell value={l.tarifa_unitaria} /></td>
                  <td className="px-3 py-2 font-medium"><CurrencyCell value={l.total ?? l.cantidad * l.tarifa_unitaria} /></td>
                  <td className="px-3 py-2">
                    {l.liquidado
                      ? <span className="text-purple-600 font-medium">Liquidado</span>
                      : l.aprobado
                        ? <span className="text-green-600 font-medium">Aprobado</span>
                        : <span className="text-yellow-600">Pendiente</span>
                    }
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => setEditLabor(l)}
                        disabled={l.aprobado || l.liquidado}
                        className="text-blue-500 hover:text-blue-700 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Editar"
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={() => { if (confirm("¿Eliminar este registro de labor?")) deleteLabor.mutate(l.id); }}
                        disabled={l.aprobado || l.liquidado}
                        className="text-red-400 hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed"
                        title="Eliminar"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editHora && (
        <EditHoraModal
          hora={editHora}
          onClose={() => setEditHora(null)}
          onSaved={() => {
            setEditHora(null);
            qc.invalidateQueries({ queryKey: ["labores-horas", mes, anio, personalId] });
            onSaved();
          }}
        />
      )}
      {editLabor && (
        <EditLaborModal
          labor={editLabor}
          onClose={() => setEditLabor(null)}
          onSaved={() => {
            setEditLabor(null);
            qc.invalidateQueries({ queryKey: ["labores-labores", mes, anio, personalId] });
            onSaved();
          }}
        />
      )}
    </div>
  );
}

// ── Modal edición Hora ────────────────────────────────────────────────────────

function EditHoraModal({ hora, onClose, onSaved }: { hora: RegistroHoras; onClose: () => void; onSaved: () => void }) {
  const [fecha, setFecha] = useState(hora.fecha);
  const [horasInput, setHorasInput] = useState(() => {
    const h = Math.floor(hora.horas_trabajadas);
    const m = Math.round((hora.horas_trabajadas - h) * 60);
    return `${h}:${String(m).padStart(2, "0")}`;
  });
  const [tarifa, setTarifa] = useState(String(hora.tarifa_hora));
  const [tipoTrabajo, setTipoTrabajo] = useState(hora.tipo_trabajo);
  const [obs, setObs] = useState(hora.observaciones ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const disabled = hora.aprobado || hora.liquidado;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const decimal = hhmmToDecimal(horasInput);
    if (!decimal) { setErr("Formato horas inválido (use HH:MM)"); return; }
    setSaving(true);
    try {
      await laboresApi.updateHora(hora.id, {
        fecha,
        horas_trabajadas: decimal,
        tarifa_hora: parseFloat(tarifa),
        tipo_trabajo: tipoTrabajo,
        observaciones: obs || null,
      });
      onSaved();
    } catch {
      setErr("Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="font-semibold text-gray-900">Editar horas</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        {disabled && (
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            Registro {hora.liquidado ? "liquidado" : "aprobado"} — no se puede editar.
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Fecha</label>
            <input type="date" value={fecha} onChange={e => setFecha(e.target.value)} disabled={disabled}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Horas (HH:MM)</label>
              <input value={horasInput} onChange={e => setHorasInput(e.target.value)} disabled={disabled}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Tarifa / hora</label>
              <input type="number" value={tarifa} onChange={e => setTarifa(e.target.value)} disabled={disabled}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Tipo de trabajo</label>
            <input value={tipoTrabajo} onChange={e => setTipoTrabajo(e.target.value)} disabled={disabled}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Observaciones</label>
            <textarea value={obs} onChange={e => setObs(e.target.value)} disabled={disabled} rows={2}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none disabled:bg-gray-50" />
          </div>
          {err && <p className="text-xs text-red-600">{err}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
              Cancelar
            </button>
            <button type="submit" disabled={disabled || saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando…" : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Modal edición Labor ───────────────────────────────────────────────────────

function EditLaborModal({ labor, onClose, onSaved }: { labor: RegistroLabores; onClose: () => void; onSaved: () => void }) {
  const [fecha, setFecha] = useState(labor.fecha);
  const [cantidad, setCantidad] = useState(String(labor.cantidad));
  const [tarifa, setTarifa] = useState(String(labor.tarifa_unitaria));
  const [tipoLabor, setTipoLabor] = useState(labor.tipo_labor);
  const [obs, setObs] = useState(labor.observaciones ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const disabled = labor.aprobado || labor.liquidado;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await laboresApi.updateLabor(labor.id, {
        fecha,
        cantidad: parseFloat(cantidad),
        tarifa_unitaria: parseFloat(tarifa),
        tipo_labor: tipoLabor,
        observaciones: obs || null,
      });
      onSaved();
    } catch {
      setErr("Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="font-semibold text-gray-900">Editar labor</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        {disabled && (
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            Registro {labor.liquidado ? "liquidado" : "aprobado"} — no se puede editar.
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Fecha</label>
            <input type="date" value={fecha} onChange={e => setFecha(e.target.value)} disabled={disabled}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Cantidad</label>
              <input type="number" value={cantidad} onChange={e => setCantidad(e.target.value)} disabled={disabled}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">Tarifa unitaria</label>
              <input type="number" value={tarifa} onChange={e => setTarifa(e.target.value)} disabled={disabled}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Tipo de labor</label>
            <input value={tipoLabor} onChange={e => setTipoLabor(e.target.value)} disabled={disabled}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm disabled:bg-gray-50" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Observaciones</label>
            <textarea value={obs} onChange={e => setObs(e.target.value)} disabled={disabled} rows={2}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none disabled:bg-gray-50" />
          </div>
          {err && <p className="text-xs text-red-600">{err}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50">
              Cancelar
            </button>
            <button type="submit" disabled={disabled || saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando…" : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Formulario Registro Horas (multi-orden) ───────────────────────────────────

interface OrdenOption { id: number; label: string }
interface FilaHora { uid: number; orden_id: number | null; horasInput: string; tarifa: number }

function RegistroHoraForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const tarifas = useTarifas();
  const personal = usePersonalLookup();
  const [fecha, setFecha] = useState(HOY_STR);
  const [tipoTrabajo, setTipoTrabajo] = useState("alistamiento_sobres");
  const [numOrdenes, setNumOrdenes] = useState(1);
  const [filas, setFilas] = useState<FilaHora[]>([{ uid: 0, orden_id: null, horasInput: "0:00", tarifa: tarifas.alistamiento }]);
  const [saving, setSaving] = useState(false);
  const [subsidioInfo, setSubsidioInfo] = useState<string | null>(null);
  const uidRef = useRef(1);

  const { data: ordenes = [] } = useQuery({
    queryKey: ["ordenes-activas"],
    queryFn: () => ordenesApi.list({ estado: "activa", limit: 500 }).then(r =>
      r.data.map(o => ({ id: o.id, label: `${o.numero_orden}` }))
    ),
    staleTime: 60_000,
  });

  useEffect(() => {
    const n = Math.max(1, Math.min(5, numOrdenes));
    setFilas(prev => {
      if (n > prev.length) {
        const extra: FilaHora[] = Array.from({ length: n - prev.length }, () => ({
          uid: uidRef.current++,
          orden_id: ordenes[0]?.id ?? null,
          horasInput: "0:00",
          tarifa: tarifas.alistamiento,
        }));
        return [...prev, ...extra];
      }
      return prev.slice(0, n);
    });
  }, [numOrdenes]);

  useEffect(() => {
    if (ordenes.length > 0) {
      setFilas(prev => prev.map(f => ({ ...f, orden_id: f.orden_id ?? ordenes[0].id })));
    }
  }, [ordenes.length]);

  function updateFila(uid: number, patch: Partial<FilaHora>) {
    setFilas(prev => prev.map(f => f.uid === uid ? { ...f, ...patch } : f));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!personal.info) return;
    const items = filas
      .map(f => ({ orden_id: f.orden_id!, horas_trabajadas: hhmmToDecimal(f.horasInput) ?? 0, tarifa_hora: f.tarifa }))
      .filter(i => i.horas_trabajadas > 0 && i.orden_id);
    if (!items.length) return;
    setSaving(true);
    try {
      await laboresApi.createHorasBulk({
        personal_id: personal.info.id,
        fecha,
        tipo_trabajo: tipoTrabajo,
        items,
      });
      const totalH = items.reduce((s, i) => s + i.horas_trabajadas, 0);
      const tipo = totalH >= 5 ? "Transporte Completo" : "Medio Transporte";
      setSubsidioInfo(`${decimalToHhmm(totalH)} h totales → subsidio: ${tipo}`);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Registrar horas de alistamiento</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          {/* Personal lookup */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Código del personal (4 dígitos) *</label>
            <div className="flex items-center gap-3">
              <input
                type="text"
                maxLength={4}
                value={personal.codigo}
                onChange={e => personal.setCodigo(e.target.value)}
                placeholder="0011"
                className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
              />
              {personal.info && (
                <span className="text-sm text-green-700 font-medium">✓ {personal.info.nombre_completo}</span>
              )}
              {personal.error && (
                <span className="text-sm text-red-600">❌ No encontrado</span>
              )}
              {personal.info && (
                <button type="button" onClick={personal.reset}
                  className="text-xs text-gray-500 hover:text-gray-700 underline">
                  Nuevo personal
                </button>
              )}
            </div>
          </div>

          {personal.info && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
                  <input type="date" required value={fecha} onChange={e => setFecha(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Tipo de trabajo *</label>
                  <select value={tipoTrabajo} onChange={e => setTipoTrabajo(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                    <option value="alistamiento_sobres">Alistamiento de Sobres</option>
                    <option value="alistamiento_paquetes">Alistamiento de Paquetes</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  ¿Cuántas órdenes trabajó? (1–5)
                </label>
                <input type="number" min={1} max={5} value={numOrdenes}
                  onChange={e => setNumOrdenes(+e.target.value)}
                  className="w-20 border border-gray-300 rounded-lg px-3 py-2 text-sm" />
              </div>

              {/* Tabla de filas */}
              <div>
                <div className="grid grid-cols-[2fr_1fr_1fr] gap-2 mb-1">
                  <span className="text-xs font-medium text-gray-600">Orden</span>
                  <span className="text-xs font-medium text-gray-600">Horas (HH:MM)</span>
                  <span className="text-xs font-medium text-gray-600">Valor</span>
                </div>
                {filas.map(f => {
                  const decimal = hhmmToDecimal(f.horasInput);
                  const valor = decimal ? decimal * f.tarifa : 0;
                  const valid = decimal !== null && decimal > 0;
                  return (
                    <div key={f.uid} className="grid grid-cols-[2fr_1fr_1fr] gap-2 mb-2">
                      <select
                        value={f.orden_id ?? ""}
                        onChange={e => updateFila(f.uid, { orden_id: +e.target.value })}
                        className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
                        required
                      >
                        <option value="">— Seleccionar —</option>
                        {ordenes.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
                      </select>
                      <input
                        type="text"
                        value={f.horasInput}
                        onChange={e => updateFila(f.uid, { horasInput: e.target.value })}
                        placeholder="2:30"
                        className={`border rounded-lg px-2 py-1.5 text-sm font-mono ${
                          f.horasInput === "0:00" || valid ? "border-gray-300" : "border-red-400"
                        }`}
                      />
                      <span className={`text-sm py-1.5 ${valid ? "text-gray-700" : "text-gray-400"}`}>
                        ${fmt.format(valor)}
                      </span>
                    </div>
                  );
                })}
                <p className="text-xs text-gray-400 mt-1">
                  Tarifa: ${fmt.format(tarifas.alistamiento)}/h (desde tarifas_servicios)
                </p>
              </div>

              {subsidioInfo && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-sm text-blue-700">
                  {subsidioInfo}
                </div>
              )}
            </>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
              Cancelar
            </button>
            <button type="submit" disabled={saving || !personal.info}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Formulario Registro Labores ───────────────────────────────────────────────

function RegistroLaborForm({
  tipoInicial, onTipoChange, onClose, onSaved,
}: {
  tipoInicial: TipoLabor;
  onTipoChange: (t: TipoLabor) => void;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [tipo, setTipo] = useState<TipoLabor>(tipoInicial);

  function handleTipo(t: TipoLabor) {
    setTipo(t);
    onTipoChange(t);
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Registrar labor</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {/* Selector tipo */}
        <div className="px-6 pt-4 flex gap-2">
          {(["pegado_guia", "transporte_completo", "medio_transporte"] as TipoLabor[]).map(t => (
            <button key={t} type="button"
              onClick={() => handleTipo(t)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tipo === t
                  ? "bg-primary text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}>
              {t === "pegado_guia" ? "📌 Pegado de guías"
                : t === "transporte_completo" ? "🚌 Transporte completo"
                : "🚐 Medio transporte"}
            </button>
          ))}
        </div>

        <div className="px-6 py-4">
          {tipo === "pegado_guia" ? (
            <PegadoGuiasForm onClose={onClose} onSaved={onSaved} />
          ) : (
            <TransporteForm tipo={tipo} onClose={onClose} onSaved={onSaved} />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Formulario Pegado de Guías ────────────────────────────────────────────────

interface FilaPegado { uid: number; codigo: string; personalId: number | null; nombre: string | null; inicial: number; final: number }

function PegadoGuiasForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const tarifas = useTarifas();
  const [fecha, setFecha] = useState(HOY_STR);
  const [ordenId, setOrdenId] = useState<number | null>(null);
  const [filas, setFilas] = useState<FilaPegado[]>([]);
  const [saving, setSaving] = useState(false);
  const uidRef = useRef(0);

  const { data: ordenes = [] } = useQuery({
    queryKey: ["ordenes-activas"],
    queryFn: () => ordenesApi.list({ estado: "activa", limit: 500 }).then(r =>
      r.data.map(o => ({ id: o.id, label: o.numero_orden }))
    ),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (ordenes.length > 0 && !ordenId) setOrdenId(ordenes[0].id);
  }, [ordenes.length]);

  function agregarFila() {
    const lastFinal = filas.length > 0 ? filas[filas.length - 1].final : 0;
    const sugerido = lastFinal + 1;
    setFilas(prev => [...prev, { uid: uidRef.current++, codigo: "", personalId: null, nombre: null, inicial: sugerido, final: sugerido }]);
  }

  function updateFila(uid: number, patch: Partial<FilaPegado>) {
    setFilas(prev => prev.map(f => f.uid === uid ? { ...f, ...patch } : f));
  }

  function removeFila(uid: number) {
    setFilas(prev => prev.filter(f => f.uid !== uid));
  }

  async function onCodigoChange(uid: number, codigo: string) {
    updateFila(uid, { codigo, personalId: null, nombre: null });
    if (codigo.length === 4) {
      try {
        const r = await laboresApi.lookupPersonalCodigo(codigo);
        updateFila(uid, { personalId: r.data.id, nombre: r.data.nombre_completo });
      } catch {
        updateFila(uid, { personalId: null, nombre: null });
      }
    }
  }

  const filasValidas = filas.filter(f => f.personalId && f.final >= f.inicial);
  const totalGuias = filasValidas.reduce((s, f) => s + (f.final - f.inicial + 1), 0);

  async function handleSubmit() {
    if (!ordenId || !filasValidas.length) return;
    setSaving(true);
    try {
      const payload = filasValidas.map(f => ({
        personal_id: f.personalId!,
        orden_id: ordenId,
        fecha,
        tipo_labor: "pegado_guia" as const,
        cantidad: f.final - f.inicial + 1,
        tarifa_unitaria: tarifas.pegado,
        observaciones: null,
      }));
      await laboresApi.createLaboresBulk(payload);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
          <input type="date" value={fecha} onChange={e => setFecha(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-medium text-gray-700 mb-1">Orden *</label>
          <select value={ordenId ?? ""} onChange={e => setOrdenId(+e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
            {ordenes.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <span>Tarifa por guía:</span>
        <span className="font-medium text-gray-700">${tarifas.pegado.toFixed(4)}</span>
      </div>

      {/* Tabla */}
      {filas.length > 0 && (
        <div>
          <div className="grid grid-cols-[1fr_2fr_1fr_1fr_1fr_auto] gap-2 mb-1 text-xs font-medium text-gray-600">
            <span>Código</span><span>Nombre</span><span>Inicial</span><span>Final</span><span>Cantidad</span><span></span>
          </div>
          {filas.map(f => {
            const cant = f.final >= f.inicial ? f.final - f.inicial + 1 : 0;
            return (
              <div key={f.uid} className="grid grid-cols-[1fr_2fr_1fr_1fr_1fr_auto] gap-2 mb-2 items-center">
                <input type="text" maxLength={4} value={f.codigo}
                  onChange={e => onCodigoChange(f.uid, e.target.value)}
                  placeholder="0011"
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm font-mono" />
                <span className={`text-xs py-1 ${f.nombre ? "text-green-700" : f.codigo.length === 4 ? "text-red-500" : "text-gray-400"}`}>
                  {f.nombre ?? (f.codigo.length === 4 ? "❌ No encontrado" : "—")}
                </span>
                <input type="number" min={1} value={f.inicial}
                  onChange={e => updateFila(f.uid, { inicial: +e.target.value })}
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm" />
                <input type="number" min={1} value={f.final}
                  onChange={e => updateFila(f.uid, { final: +e.target.value })}
                  className="border border-gray-300 rounded px-2 py-1.5 text-sm" />
                <span className={`text-sm font-medium py-1.5 ${cant > 0 ? "text-gray-900" : "text-orange-500"}`}>
                  {cant > 0 ? fmt.format(cant) : "⚠"}
                </span>
                <button type="button" onClick={() => removeFila(f.uid)}
                  className="text-gray-400 hover:text-red-500">
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <button type="button" onClick={agregarFila}
        className="flex items-center gap-1 text-sm text-primary hover:underline">
        <Plus size={14} /> Agregar fila
      </button>

      {filas.length > 0 && (
        <div className="grid grid-cols-3 gap-4 bg-gray-50 rounded-lg p-3 text-sm">
          <div><p className="text-xs text-gray-500">Filas válidas</p><p className="font-semibold">{filasValidas.length} / {filas.length}</p></div>
          <div><p className="text-xs text-gray-500">Total guías</p><p className="font-semibold">{fmt.format(totalGuias)}</p></div>
          <div><p className="text-xs text-gray-500">Valor total</p><p className="font-semibold">${fmt.format(totalGuias * tarifas.pegado)}</p></div>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button type="button" onClick={onClose}
          className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
          Cancelar
        </button>
        <button type="button" onClick={handleSubmit}
          disabled={saving || !filasValidas.length || !ordenId}
          className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
          {saving ? "Guardando..." : `Guardar ${filasValidas.length} registro(s)`}
        </button>
      </div>
    </div>
  );
}

// ── Formulario Transporte ─────────────────────────────────────────────────────

interface FilaTransporte { uid: number; fecha: string; ordenId: number | null; tarifa: number }

function TransporteForm({
  tipo, onClose, onSaved,
}: {
  tipo: "transporte_completo" | "medio_transporte";
  onClose: () => void;
  onSaved: () => void;
}) {
  const tarifas = useTarifas();
  const personal = usePersonalLookup();
  const [filas, setFilas] = useState<FilaTransporte[]>([]);
  const [saving, setSaving] = useState(false);
  const uidRef = useRef(0);

  const { data: ordenes = [] } = useQuery({
    queryKey: ["ordenes-activas"],
    queryFn: () => ordenesApi.list({ estado: "activa", limit: 500 }).then(r =>
      r.data.map(o => ({ id: o.id, label: o.numero_orden }))
    ),
    staleTime: 60_000,
  });

  function agregarFila() {
    setFilas(prev => [...prev, {
      uid: uidRef.current++,
      fecha: HOY_STR,
      ordenId: ordenes[0]?.id ?? null,
      tarifa: tarifas.transporte,
    }]);
  }

  function updateFila(uid: number, patch: Partial<FilaTransporte>) {
    setFilas(prev => prev.map(f => f.uid === uid ? { ...f, ...patch } : f));
  }

  function removeFila(uid: number) {
    setFilas(prev => prev.filter(f => f.uid !== uid));
  }

  const filasValidas = filas.filter(f => f.ordenId && f.tarifa > 0);
  const total = filasValidas.reduce((s, f) => s + f.tarifa, 0);

  async function handleSubmit() {
    if (!personal.info || !filasValidas.length) return;
    setSaving(true);
    try {
      const payload = filasValidas.map(f => ({
        personal_id: personal.info!.id,
        orden_id: f.ordenId!,
        fecha: f.fecha,
        tipo_labor: tipo,
        cantidad: 1,
        tarifa_unitaria: f.tarifa,
        observaciones: null,
      }));
      await laboresApi.createLaboresBulk(payload);
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Personal */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">Código del mensajero (4 dígitos) *</label>
        <div className="flex items-center gap-3">
          <input type="text" maxLength={4} value={personal.codigo}
            onChange={e => personal.setCodigo(e.target.value)}
            placeholder="0011"
            className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono" />
          {personal.info && (
            <span className="text-sm text-green-700 font-medium">✓ {personal.info.nombre_completo}</span>
          )}
          {personal.error && <span className="text-sm text-red-600">❌ No encontrado</span>}
          {personal.info && (
            <button type="button" onClick={() => { personal.reset(); setFilas([]); }}
              className="text-xs text-gray-500 hover:text-gray-700 underline">
              Nuevo mensajero
            </button>
          )}
        </div>
      </div>

      {personal.info && (
        <>
          {/* Tabla filas */}
          {filas.length > 0 && (
            <div>
              <div className="grid grid-cols-[1.5fr_2fr_1.5fr_1fr_auto] gap-2 mb-1 text-xs font-medium text-gray-600">
                <span>Fecha</span><span>Orden</span><span>Tarifa ($)</span><span>Valor</span><span></span>
              </div>
              {filas.map(f => (
                <div key={f.uid} className="grid grid-cols-[1.5fr_2fr_1.5fr_1fr_auto] gap-2 mb-2 items-center">
                  <input type="date" value={f.fecha}
                    onChange={e => updateFila(f.uid, { fecha: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1.5 text-sm" />
                  <select value={f.ordenId ?? ""}
                    onChange={e => updateFila(f.uid, { ordenId: +e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1.5 text-sm">
                    {ordenes.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                  <input type="number" min={0} step={1000} value={f.tarifa}
                    onChange={e => updateFila(f.uid, { tarifa: +e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1.5 text-sm" />
                  <span className="text-sm font-medium text-gray-700 py-1.5">${fmt.format(f.tarifa)}</span>
                  <button type="button" onClick={() => removeFila(f.uid)}
                    className="text-gray-400 hover:text-red-500">
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <button type="button" onClick={agregarFila}
            className="flex items-center gap-1 text-sm text-primary hover:underline">
            <Plus size={14} /> Agregar fila
          </button>

          {filas.length > 0 && (
            <div className="grid grid-cols-2 gap-4 bg-gray-50 rounded-lg p-3 text-sm">
              <div><p className="text-xs text-gray-500">Filas</p><p className="font-semibold">{filasValidas.length}</p></div>
              <div><p className="text-xs text-gray-500">Total a pagar</p><p className="font-semibold">${fmt.format(total)}</p></div>
            </div>
          )}
        </>
      )}

      <div className="flex justify-end gap-3 pt-2">
        <button type="button" onClick={onClose}
          className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
          Cancelar
        </button>
        <button type="button" onClick={handleSubmit}
          disabled={saving || !personal.info || !filasValidas.length}
          className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60">
          {saving ? "Guardando..." : `Guardar ${filasValidas.length} registro(s)`}
        </button>
      </div>
    </div>
  );
}
