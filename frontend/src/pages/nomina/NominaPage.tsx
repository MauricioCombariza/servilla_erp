import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Calculator, ChevronDown, ChevronRight, X, UserPlus } from "lucide-react";
import { nominaApi } from "@/api/nomina";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import { Badge } from "@/components/ui/Badge";
import { LiquidacionesPanel } from "@/pages/pagos/LiquidacionesPage";
import type {
  EmpleadoResumen,
  NominaEmpleado,
  NominaParametro,
  NominaProvision,
  PeriodoHistorico,
  ResumenNominaDetallado,
  RosterEntry,
} from "@/types/domain";

const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
const MESES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"];
const HOY = new Date();

type Tab = "empleados" | "resumen" | "provisiones" | "parametros" | "pagos";

export function NominaPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("empleados");
  const [mes, setMes] = useState(HOY.getMonth() + 1);
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<NominaEmpleado | null>(null);
  const [calcResult, setCalcResult] = useState<string | null>(null);

  const { data: empleados = [], isLoading } = useQuery({
    queryKey: ["nomina-empleados"],
    queryFn: () => nominaApi.listEmpleados().then((r) => r.data),
  });

  const { data: resumen, isLoading: loadingResumen } = useQuery({
    queryKey: ["nomina-resumen"],
    queryFn: () => nominaApi.getResumen().then((r) => r.data),
    enabled: tab === "resumen",
  });

  const { data: provisiones = [], isLoading: loadingProv } = useQuery({
    queryKey: ["nomina-provisiones", mes, anio],
    queryFn: () => nominaApi.listProvisiones({ mes, anio }).then((r) => r.data),
    enabled: tab === "provisiones",
  });

  const { data: historico = [], isLoading: loadingHistorico } = useQuery({
    queryKey: ["nomina-historico"],
    queryFn: () => nominaApi.listHistorico().then((r) => r.data),
    enabled: tab === "provisiones",
  });

  const { data: parametros = [], isLoading: loadingParams } = useQuery({
    queryKey: ["nomina-parametros"],
    queryFn: () => nominaApi.listParametros().then((r) => r.data),
    enabled: tab === "parametros",
  });

  const calcular = useMutation({
    mutationFn: () => nominaApi.calcularProvisiones(mes, anio),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["nomina-provisiones"] });
      qc.invalidateQueries({ queryKey: ["nomina-historico"] });
      qc.invalidateQueries({ queryKey: ["nomina-resumen"] });
      setCalcResult(
        `${res.data.total_empleados} empleados — costo total: $${fmt.format(res.data.costo_total)}`
      );
    },
  });

  const borrarPeriodo = useMutation({
    mutationFn: () => nominaApi.deleteProvisiones(mes, anio),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["nomina-provisiones"] });
      qc.invalidateQueries({ queryKey: ["nomina-historico"] });
    },
  });

  const totalSalarios = empleados.filter((e) => e.activo).reduce((s, e) => s + e.salario_mensual, 0);

  const TAB_LABELS: Record<Tab, string> = {
    empleados: "Empleados",
    resumen: "Resumen nómina",
    provisiones: "Provisiones",
    parametros: "Parámetros",
    pagos: "Pagos mensajeros",
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Nómina</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {empleados.filter((e) => e.activo).length} empleados activos · Masa salarial:{" "}
            <span className="font-medium text-gray-800">${fmt.format(totalSalarios)}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(tab === "provisiones" || tab === "pagos") && (
            <>
              <select
                value={mes}
                onChange={(e) => setMes(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm"
              >
                {MESES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
              </select>
              <input
                type="number"
                value={anio}
                onChange={(e) => setAnio(+e.target.value)}
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm w-20"
              />
            </>
          )}
          {tab === "provisiones" && (
            <button
              onClick={() => calcular.mutate()}
              disabled={calcular.isPending}
              className="flex items-center gap-2 bg-amber-500 hover:bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-60"
            >
              <Calculator size={16} />
              {calcular.isPending ? "Calculando..." : "Calcular período"}
            </button>
          )}
          {tab === "empleados" && (
            <button
              onClick={() => { setEditing(null); setShowForm(true); }}
              className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Nuevo empleado
            </button>
          )}
        </div>
      </div>

      {calcResult && (
        <div className="bg-green-50 border border-green-200 text-green-800 text-sm px-4 py-3 rounded-lg mb-4">
          Provisiones calculadas: {calcResult}
          <button onClick={() => setCalcResult(null)} className="ml-3 text-green-600 hover:text-green-800">✕</button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-4">
        {(["empleados", "resumen", "provisiones", "parametros", "pagos"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === "empleados" && (
        <>
          {isLoading ? (
            <div className="text-center py-16 text-gray-500">Cargando...</div>
          ) : empleados.length === 0 ? (
            <div className="text-center py-16 text-gray-400">Sin empleados registrados</div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    {["Nombre", "Identificación", "Cargo", "Salario base", "Auxilio transp.", "Aux. no salarial", "Estado", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {empleados.map((e) => (
                    <tr key={e.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{e.nombre_completo}</td>
                      <td className="px-4 py-3 text-gray-600 font-mono text-xs">{e.identificacion ?? "—"}</td>
                      <td className="px-4 py-3 text-gray-600">{e.cargo ?? "—"}</td>
                      <td className="px-4 py-3 font-medium text-gray-900"><CurrencyCell value={e.salario_mensual} /></td>
                      <td className="px-4 py-3 text-center">
                        {e.tiene_auxilio_transporte ? (
                          <span className="text-green-600 text-xs font-medium">Sí</span>
                        ) : (
                          <span className="text-gray-400 text-xs">No</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-600"><CurrencyCell value={e.auxilio_no_salarial} /></td>
                      <td className="px-4 py-3">
                        <Badge active={e.activo} />
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => { setEditing(e); setShowForm(true); }}
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
        </>
      )}

      {tab === "resumen" && (
        <ResumenTab resumen={resumen} loading={loadingResumen} />
      )}

      {tab === "provisiones" && (
        <ProvisionesTab
          provisiones={provisiones}
          empleados={empleados}
          loading={loadingProv}
          historico={historico}
          loadingHistorico={loadingHistorico}
          onBorrarPeriodo={() => {
            if (confirm(`¿Borrar todas las provisiones de ${MESES[mes - 1]} ${anio}?`))
              borrarPeriodo.mutate();
          }}
          borrando={borrarPeriodo.isPending}
          mes={mes}
          anio={anio}
        />
      )}

      {tab === "parametros" && (
        <ParametrosTab parametros={parametros} loading={loadingParams} />
      )}

      {tab === "pagos" && (
        <LiquidacionesPanel mes={mes} anio={anio} soloSeriales />
      )}

      {showForm && (
        <EmpleadoForm
          initial={editing}
          onClose={() => { setShowForm(false); setEditing(null); }}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["nomina-empleados"] });
            qc.invalidateQueries({ queryKey: ["nomina-resumen"] });
            setShowForm(false);
            setEditing(null);
          }}
          onDeleted={() => {
            qc.invalidateQueries({ queryKey: ["nomina-empleados"] });
            qc.invalidateQueries({ queryKey: ["nomina-resumen"] });
            qc.invalidateQueries({ queryKey: ["nomina-historico"] });
            setShowForm(false);
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// ── Resumen Tab ───────────────────────────────────────────────────────────────

function ResumenTab({
  resumen,
  loading,
}: {
  resumen: ResumenNominaDetallado | undefined;
  loading: boolean;
}) {
  if (loading) return <div className="text-center py-16 text-gray-500">Cargando...</div>;
  if (!resumen || resumen.total_empleados === 0)
    return <div className="text-center py-16 text-gray-400">Sin empleados activos</div>;

  return (
    <div className="space-y-6">
      {/* Tabla por empleado */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {["Empleado", "Cargo", "Salario nominal", "Aux. no salarial", "Aux. transporte", "Costo total"].map((h) => (
                <th key={h} className="text-right first:text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {resumen.empleados.map((e: EmpleadoResumen) => (
              <tr key={e.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900 text-xs whitespace-nowrap">{e.nombre_completo}</td>
                <td className="px-4 py-3 text-gray-600 text-xs">{e.cargo ?? "—"}</td>
                <td className="px-4 py-3 text-right text-gray-700 text-xs">${fmt.format(e.salario_mensual)}</td>
                <td className="px-4 py-3 text-right text-gray-700 text-xs">${fmt.format(e.auxilio_no_salarial)}</td>
                <td className="px-4 py-3 text-right text-gray-700 text-xs">${fmt.format(e.auxilio_transporte)}</td>
                <td className="px-4 py-3 text-right font-semibold text-gray-900 text-xs">${fmt.format(e.costo_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Desglose en 3 columnas */}
      <div className="grid grid-cols-3 gap-4">
        {/* Nómina Base */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3">Nómina base</p>
          <div className="space-y-1.5 text-sm">
            {[
              ["Salarios", resumen.total_salarios],
              ["Aux. no salarial", resumen.total_aux_no_salarial],
              ["Aux. transporte", resumen.total_aux_transporte],
            ].map(([label, value]) => (
              <div key={label as string} className="flex justify-between text-xs text-gray-600">
                <span>{label as string}</span>
                <span>${fmt.format(value as number)}</span>
              </div>
            ))}
            <div className="border-t border-gray-200 mt-2 pt-2 flex justify-between text-xs font-semibold text-gray-900">
              <span>Subtotal</span>
              <span>${fmt.format(resumen.total_nomina_base)}</span>
            </div>
          </div>
        </div>

        {/* Seguridad Social */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3">Seguridad social</p>
          <div className="space-y-1.5 text-sm">
            {[
              ["ARL", resumen.total_arl],
              ["EPS", resumen.total_eps],
              ["AFP", resumen.total_afp],
              ["Caja compensación", resumen.total_caja],
            ].map(([label, value]) => (
              <div key={label as string} className="flex justify-between text-xs text-gray-600">
                <span>{label as string}</span>
                <span>${fmt.format(value as number)}</span>
              </div>
            ))}
            <div className="border-t border-gray-200 mt-2 pt-2 flex justify-between text-xs font-semibold text-gray-900">
              <span>Subtotal</span>
              <span>${fmt.format(resumen.total_seguridad_social)}</span>
            </div>
          </div>
        </div>

        {/* Provisiones */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-3">Provisiones</p>
          <div className="space-y-1.5 text-sm">
            {[
              ["Prima", resumen.total_prima],
              ["Cesantías", resumen.total_cesantias],
              ["Int. cesantías", resumen.total_int_cesantias],
              ["Vacaciones", resumen.total_vacaciones],
            ].map(([label, value]) => (
              <div key={label as string} className="flex justify-between text-xs text-gray-600">
                <span>{label as string}</span>
                <span>${fmt.format(value as number)}</span>
              </div>
            ))}
            <div className="border-t border-gray-200 mt-2 pt-2 flex justify-between text-xs font-semibold text-gray-900">
              <span>Subtotal</span>
              <span>${fmt.format(resumen.total_provisiones)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Métricas totales */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Salarios + auxilios</p>
          <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(resumen.total_nomina_base)}</p>
        </div>
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-500 uppercase tracking-wide">Seg. social + provisiones</p>
          <p className="text-xl font-semibold text-gray-900 mt-1">
            ${fmt.format(resumen.total_seguridad_social + resumen.total_provisiones)}
          </p>
        </div>
        <div className="bg-primary/5 rounded-xl border border-primary/20 p-4">
          <p className="text-xs text-primary/70 uppercase tracking-wide font-medium">Costo total mensual</p>
          <p className="text-xl font-bold text-primary mt-1">${fmt.format(resumen.costo_total)}</p>
        </div>
      </div>
    </div>
  );
}

// ── Provisiones Tab ───────────────────────────────────────────────────────────

function ProvisionesTab({
  provisiones,
  empleados,
  loading,
  historico,
  loadingHistorico,
  onBorrarPeriodo,
  borrando,
  mes,
  anio,
}: {
  provisiones: NominaProvision[];
  empleados: NominaEmpleado[];
  loading: boolean;
  historico: PeriodoHistorico[];
  loadingHistorico: boolean;
  onBorrarPeriodo: () => void;
  borrando: boolean;
  mes: number;
  anio: number;
}) {
  const qc = useQueryClient();
  const [showHistorico, setShowHistorico] = useState(false);
  const [selectedToAdd, setSelectedToAdd] = useState<number | "">("");
  const [rosterError, setRosterError] = useState<string | null>(null);

  const { data: roster = [], isLoading: loadingRoster } = useQuery({
    queryKey: ["nomina-roster", mes, anio],
    queryFn: () => nominaApi.getRoster(mes, anio).then((r) => r.data),
  });

  const invalidateRoster = () => qc.invalidateQueries({ queryKey: ["nomina-roster", mes, anio] });

  const inicializar = useMutation({
    mutationFn: () => nominaApi.inicializarRoster(mes, anio),
    onSuccess: invalidateRoster,
  });

  const copiarAnterior = useMutation({
    mutationFn: () => nominaApi.copiarMesAnterior(mes, anio),
    onSuccess: () => { invalidateRoster(); setRosterError(null); },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setRosterError(msg ?? "No hay roster definido en el mes anterior");
    },
  });

  const remover = useMutation({
    mutationFn: (entryId: number) => nominaApi.removeFromRoster(entryId),
    onSuccess: invalidateRoster,
  });

  const agregar = useMutation({
    mutationFn: (empleadoId: number) => nominaApi.addToRoster(empleadoId, mes, anio),
    onSuccess: () => { invalidateRoster(); setSelectedToAdd(""); },
  });

  const rosterIds = new Set(roster.map((r: RosterEntry) => r.empleado_id));
  const disponibles = empleados.filter((e) => e.activo && !rosterIds.has(e.id));

  if (loading) return <div className="text-center py-16 text-gray-500">Cargando...</div>;

  const empleadoMap = Object.fromEntries(empleados.map((e) => [e.id, e.nombre_completo]));

  const totales = provisiones.reduce(
    (acc, p) => ({
      salario: acc.salario + (p.salario_base ?? 0),
      ss: acc.ss + (p.arl ?? 0) + (p.eps ?? 0) + (p.afp ?? 0) + (p.caja_compensacion ?? 0),
      prov: acc.prov + (p.prima ?? 0) + (p.cesantias ?? 0) + (p.int_cesantias ?? 0) + (p.vacaciones ?? 0),
    }),
    { salario: 0, ss: 0, prov: 0 }
  );

  return (
    <>
      {/* ── Roster del período ── */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-blue-900">
            Personal en nómina — {MESES[mes - 1]} {anio}
            {!loadingRoster && (
              <span className="ml-2 font-normal text-blue-600 text-xs">
                ({roster.length} {roster.length === 1 ? "empleado" : "empleados"})
              </span>
            )}
          </h3>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setRosterError(null); copiarAnterior.mutate(); }}
              disabled={copiarAnterior.isPending}
              className="text-xs border border-blue-300 bg-white hover:bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg disabled:opacity-60 transition-colors"
            >
              {copiarAnterior.isPending ? "Copiando..." : "Copiar mes anterior"}
            </button>
            <button
              onClick={() => inicializar.mutate()}
              disabled={inicializar.isPending}
              className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg disabled:opacity-60 transition-colors"
            >
              {inicializar.isPending ? "Inicializando..." : "Inicializar todos los activos"}
            </button>
          </div>
        </div>

        {rosterError && (
          <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-3">
            {rosterError}
          </p>
        )}

        {loadingRoster ? (
          <div className="text-xs text-blue-600 py-2">Cargando roster...</div>
        ) : roster.length === 0 ? (
          <p className="text-xs text-blue-600 py-2">
            No hay personal en el roster de este período. Use "Inicializar" para agregar todos los empleados activos, o "Copiar mes anterior" para copiar el período previo.
          </p>
        ) : (
          <div className="rounded-lg border border-blue-200 bg-white overflow-hidden mb-3">
            <table className="w-full text-xs">
              <tbody className="divide-y divide-blue-100">
                {roster.map((r: RosterEntry) => (
                  <tr key={r.id} className="flex items-center justify-between px-3 py-2 hover:bg-blue-50">
                    <td className="font-medium text-gray-800 flex-1">{r.empleado.nombre_completo}</td>
                    <td className="text-gray-500 w-40">{r.empleado.cargo ?? "—"}</td>
                    <td>
                      <button
                        onClick={() => remover.mutate(r.id)}
                        disabled={remover.isPending}
                        className="text-red-400 hover:text-red-600 transition-colors disabled:opacity-40"
                        title="Quitar del período"
                      >
                        <X size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {disponibles.length > 0 && (
          <div className="flex items-center gap-2 mt-2">
            <select
              value={selectedToAdd}
              onChange={(e) => setSelectedToAdd(e.target.value ? +e.target.value : "")}
              className="flex-1 border border-blue-300 rounded-lg px-3 py-1.5 text-xs bg-white"
            >
              <option value="">Seleccionar empleado para agregar...</option>
              {disponibles.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nombre_completo}{e.cargo ? ` — ${e.cargo}` : ""}
                </option>
              ))}
            </select>
            <button
              onClick={() => selectedToAdd !== "" && agregar.mutate(+selectedToAdd)}
              disabled={selectedToAdd === "" || agregar.isPending}
              className="flex items-center gap-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg disabled:opacity-60 transition-colors whitespace-nowrap"
            >
              <UserPlus size={13} /> {agregar.isPending ? "Agregando..." : "Agregar al período"}
            </button>
          </div>
        )}
      </div>

      {/* ── Provisiones calculadas ── */}
      {provisiones.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          Sin provisiones para este período. Use "Calcular período" para generarlas.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-4">
            {[
              { label: "Total salarios", value: totales.salario },
              { label: "Seguridad social", value: totales.ss },
              { label: "Provisiones", value: totales.prov },
            ].map((m) => (
              <div key={m.label} className="bg-white rounded-xl border border-gray-200 p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">{m.label}</p>
                <p className="text-xl font-semibold text-gray-900 mt-1">${fmt.format(m.value)}</p>
              </div>
            ))}
          </div>
          <div className="flex justify-end mb-4">
            <button
              onClick={onBorrarPeriodo}
              disabled={borrando}
              className="flex items-center gap-1.5 text-xs text-red-600 hover:text-red-800 border border-red-200 hover:bg-red-50 px-3 py-1.5 rounded-lg disabled:opacity-60 transition-colors"
            >
              <Trash2 size={13} /> {borrando ? "Borrando..." : "Borrar período"}
            </button>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto mb-6">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {["Empleado", "Salario", "Aux. transp.", "ARL", "EPS", "AFP", "Caja", "Prima", "Cesantías", "Int. ces.", "Vacaciones"].map((h) => (
                    <th key={h} className="text-right first:text-left px-3 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {provisiones.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-3 py-3 text-gray-800 font-medium text-xs whitespace-nowrap">
                      {empleadoMap[p.empleado_id] ?? `#${p.empleado_id}`}
                    </td>
                    {[p.salario_base, p.auxilio_transporte, p.arl, p.eps, p.afp, p.caja_compensacion, p.prima, p.cesantias, p.int_cesantias, p.vacaciones].map((v, i) => (
                      <td key={i} className="px-3 py-3 text-right text-gray-700 text-xs">
                        {v != null ? `$${fmt.format(v)}` : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ── Historial ── */}
      <div className="bg-white rounded-xl border border-gray-200">
        <button
          onClick={() => setShowHistorico(!showHistorico)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <span>Historial últimos períodos</span>
          {showHistorico ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
        {showHistorico && (
          loadingHistorico ? (
            <div className="text-center py-6 text-gray-500 text-sm">Cargando historial...</div>
          ) : historico.length === 0 ? (
            <div className="text-center py-6 text-gray-400 text-sm">Sin períodos calculados</div>
          ) : (
            <table className="w-full text-sm border-t border-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  {["Período", "Empleados", "Costo total"].map((h) => (
                    <th key={h} className="text-right first:text-left px-4 py-2 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {historico.map((h: PeriodoHistorico) => (
                  <tr key={`${h.periodo_anio}-${h.periodo_mes}`} className="hover:bg-gray-50">
                    <td className="px-4 py-2 text-gray-700 text-xs">{MESES[h.periodo_mes - 1]} {h.periodo_anio}</td>
                    <td className="px-4 py-2 text-right text-gray-600 text-xs">{h.total_empleados}</td>
                    <td className="px-4 py-2 text-right font-medium text-gray-900 text-xs">${fmt.format(h.costo_total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </>
  );
}

// ── Parámetros Tab ────────────────────────────────────────────────────────────

function ParametrosTab({ parametros, loading }: { parametros: NominaParametro[]; loading: boolean }) {
  const qc = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editVal, setEditVal] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [newParam, setNewParam] = useState({
    parametro: "",
    valor: "",
    descripcion: "",
    vigencia_desde: HOY.toISOString().split("T")[0],
  });

  const update = useMutation({
    mutationFn: ({ id, valor }: { id: number; valor: number }) =>
      nominaApi.updateParametro(id, { valor }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["nomina-parametros"] });
      setEditingId(null);
    },
  });

  const create = useMutation({
    mutationFn: () =>
      nominaApi.createParametro({
        parametro: newParam.parametro,
        valor: parseFloat(newParam.valor),
        descripcion: newParam.descripcion || undefined,
        vigencia_desde: newParam.vigencia_desde,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["nomina-parametros"] });
      setShowAdd(false);
      setNewParam({ parametro: "", valor: "", descripcion: "", vigencia_desde: HOY.toISOString().split("T")[0] });
    },
  });

  if (loading) return <div className="text-center py-16 text-gray-500">Cargando...</div>;

  const isPercent = (p: string) =>
    ["arl", "eps", "afp", "caja", "prima", "cesantias", "int_cesantias", "vacaciones"].includes(p);

  function formatValor(p: NominaParametro) {
    if (isPercent(p.parametro)) return `${(p.valor * 100).toFixed(3)}%`;
    return `$${fmt.format(p.valor)}`;
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> Nuevo parámetro
        </button>
      </div>

      {showAdd && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-800 mb-4">Agregar parámetro</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Clave (ej: arl, smmlv)</label>
              <input
                value={newParam.parametro}
                onChange={(e) => setNewParam({ ...newParam, parametro: e.target.value })}
                placeholder="nombre_parametro"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Valor</label>
              <input
                type="number"
                step="any"
                value={newParam.valor}
                onChange={(e) => setNewParam({ ...newParam, valor: e.target.value })}
                placeholder="0"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Descripción</label>
              <input
                value={newParam.descripcion}
                onChange={(e) => setNewParam({ ...newParam, descripcion: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Vigencia desde</label>
              <input
                type="date"
                value={newParam.vigencia_desde}
                onChange={(e) => setNewParam({ ...newParam, vigencia_desde: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <button
              onClick={() => setShowAdd(false)}
              className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              Cancelar
            </button>
            <button
              onClick={() => create.mutate()}
              disabled={create.isPending || !newParam.parametro || !newParam.valor}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60"
            >
              {create.isPending ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </div>
      )}

      {parametros.length === 0 ? (
        <div className="text-center py-16 text-gray-400">Sin parámetros configurados</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Parámetro", "Descripción", "Valor actual", "Vigencia desde", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {parametros.map((p) => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.parametro}</td>
                  <td className="px-4 py-3 text-gray-600">{p.descripcion ?? "—"}</td>
                  <td className="px-4 py-3">
                    {editingId === p.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          step="any"
                          value={editVal}
                          onChange={(e) => setEditVal(e.target.value)}
                          className="border border-gray-300 rounded px-2 py-1 text-sm w-32"
                          autoFocus
                        />
                        <button
                          onClick={() => update.mutate({ id: p.id, valor: parseFloat(editVal) })}
                          disabled={update.isPending}
                          className="text-xs bg-primary text-white px-3 py-1 rounded disabled:opacity-60"
                        >
                          Guardar
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="text-xs text-gray-500 hover:text-gray-700"
                        >
                          Cancelar
                        </button>
                      </div>
                    ) : (
                      <span className="font-medium text-gray-900">{formatValor(p)}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{p.vigencia_desde}</td>
                  <td className="px-4 py-3">
                    {editingId !== p.id && (
                      <button
                        onClick={() => {
                          setEditingId(p.id);
                          setEditVal(String(p.valor));
                        }}
                        className="text-gray-400 hover:text-primary transition-colors"
                      >
                        <Pencil size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Formulario Empleado ───────────────────────────────────────────────────────

function EmpleadoForm({
  initial,
  onClose,
  onSaved,
  onDeleted,
}: {
  initial: NominaEmpleado | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted?: () => void;
}) {
  const [form, setForm] = useState({
    nombre_completo: initial?.nombre_completo ?? "",
    identificacion: initial?.identificacion ?? "",
    cargo: initial?.cargo ?? "",
    salario_mensual: initial?.salario_mensual ?? 0,
    tiene_auxilio_transporte: initial?.tiene_auxilio_transporte ?? false,
    auxilio_no_salarial: initial?.auxilio_no_salarial ?? 0,
    fecha_ingreso: initial?.fecha_ingreso ?? "",
    activo: initial?.activo ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        identificacion: form.identificacion || null,
        cargo: form.cargo || null,
        fecha_ingreso: form.fecha_ingreso || null,
      };
      if (initial) {
        await nominaApi.updateEmpleado(initial.id, payload);
      } else {
        await nominaApi.createEmpleado(payload);
      }
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!initial) return;
    if (!confirm(`¿Eliminar a ${initial.nombre_completo}? Se borrarán también todas sus provisiones.`)) return;
    setDeleting(true);
    try {
      await nominaApi.deleteEmpleado(initial.id);
      onDeleted?.();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-900">
            {initial ? "Editar empleado" : "Nuevo empleado"}
          </h2>
        </div>
        <form onSubmit={handleSubmit} className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Nombre completo *</label>
            <input
              required
              value={form.nombre_completo}
              onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Identificación</label>
              <input
                value={form.identificacion}
                onChange={(e) => setForm({ ...form, identificacion: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cargo</label>
              <input
                value={form.cargo}
                onChange={(e) => setForm({ ...form, cargo: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Salario mensual *</label>
              <input
                type="number"
                required
                min={0}
                value={form.salario_mensual}
                onChange={(e) => setForm({ ...form, salario_mensual: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Aux. no salarial</label>
              <input
                type="number"
                min={0}
                value={form.auxilio_no_salarial}
                onChange={(e) => setForm({ ...form, auxilio_no_salarial: +e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="aux_transp"
              checked={form.tiene_auxilio_transporte}
              onChange={(e) => setForm({ ...form, tiene_auxilio_transporte: e.target.checked })}
              className="rounded border-gray-300"
            />
            <label htmlFor="aux_transp" className="text-sm text-gray-700">
              Tiene auxilio de transporte
            </label>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha ingreso</label>
            <input
              type="date"
              value={form.fecha_ingreso}
              onChange={(e) => setForm({ ...form, fecha_ingreso: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          {initial && (
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="emp_activo"
                checked={form.activo}
                onChange={(e) => setForm({ ...form, activo: e.target.checked })}
                className="rounded border-gray-300"
              />
              <label htmlFor="emp_activo" className="text-sm text-gray-700">
                Empleado activo
              </label>
            </div>
          )}
          <div className="flex items-center justify-between pt-2">
            {initial ? (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="flex items-center gap-1.5 text-sm text-red-600 hover:text-red-800 disabled:opacity-60"
              >
                <Trash2 size={14} /> {deleting ? "Eliminando..." : "Eliminar empleado"}
              </button>
            ) : <span />}
            <div className="flex gap-3">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-lg">
                Cancelar
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg disabled:opacity-60"
              >
                {saving ? "Guardando..." : "Guardar"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
