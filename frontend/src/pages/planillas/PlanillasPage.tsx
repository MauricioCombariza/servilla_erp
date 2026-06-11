import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Lock,
  Unlock,
  Pencil,
  List,
  AlertTriangle,
  CheckCircle,
  Circle,
  RefreshCw,
  Download,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { gestionesApi, type RecalcularResult, type BloquearRangoResult } from "@/api/gestiones";
import { personalApi } from "@/api/personal";
import { CurrencyCell } from "@/components/ui/CurrencyCell";
import type { PlanillaResumen } from "@/types/domain";
import { X } from "lucide-react";

// ── Modal de edición de planilla ──────────────────────────────────────────────
interface EditModalProps {
  planilla: PlanillaResumen;
  onClose: () => void;
  onSaved: () => void;
}

function EditModal({ planilla, onClose, onSaved }: EditModalProps) {
  const [codMen, setCodMen] = useState(planilla.cod_men);
  const [mensajeroId, setMensajeroId] = useState<number | undefined>(
    planilla.mensajero_id ?? undefined
  );
  const [precio, setPrecio] = useState(planilla.precio_promedio_mensajero);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const { data: personal = [] } = useQuery({
    queryKey: ["personal", true],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
  });

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      if (codMen !== planilla.cod_men) {
        await gestionesApi.cambiarMensajero(planilla.planilla, codMen, mensajeroId);
      }
      if (precio !== planilla.precio_promedio_mensajero) {
        await gestionesApi.cambiarPrecio(planilla.planilla, precio);
      }
      onSaved();
    } catch {
      setError("Error al guardar cambios");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div>
            <h2 className="font-semibold text-gray-900">Editar planilla</h2>
            <p className="text-xs text-gray-500 font-mono mt-0.5">{planilla.planilla}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Mensajero</label>
            <select
              value={codMen}
              onChange={(e) => {
                setCodMen(e.target.value);
                const p = personal.find((p) => p.codigo === e.target.value);
                setMensajeroId(p?.id);
              }}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none"
            >
              <option value="">— sin asignar —</option>
              {personal.map((p) => (
                <option key={p.id} value={p.codigo}>
                  {p.codigo} — {p.nombre_completo}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-400 mt-1">
              Solo actualiza seriales no bloqueados ({planilla.total_seriales} total)
            </p>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Precio mensajero ($/serial)
            </label>
            <input
              type="number"
              min={0}
              step={50}
              value={precio}
              onChange={(e) => setPrecio(Number(e.target.value))}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
            />
            <p className="text-xs text-gray-400 mt-1">
              Nuevo total ≈{" "}
              <span className="font-medium text-gray-700">
                ${(precio * planilla.total_seriales).toLocaleString("es-CO")}
              </span>
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
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

// ── Modal recalcular precios ──────────────────────────────────────────────────
interface RecalcularModalProps {
  filtros: { fecha_desde: string; fecha_hasta: string; cod_men: string; planilla: string };
  onClose: () => void;
  onDone: () => void;
}

function RecalcularModal({ filtros, onClose, onDone }: RecalcularModalProps) {
  const [soloPrecioCero, setSoloPrecioCero] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RecalcularResult | null>(null);
  const [error, setError] = useState("");

  async function handleRun() {
    setRunning(true);
    setError("");
    try {
      const req = {
        fecha_desde: filtros.fecha_desde || undefined,
        fecha_hasta: filtros.fecha_hasta || undefined,
        cod_men: filtros.cod_men || undefined,
        solo_precio_cero: soloPrecioCero,
      };
      const res = await gestionesApi.recalcular(req);
      setResult(res.data);
      onDone();
    } catch {
      setError("Error al recalcular precios");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-sm">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Recalcular precios</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <p className="text-sm text-gray-600">
            Recalcula <span className="font-medium">precio_mensajero</span> usando la tabla
            de precios vigente. Solo afecta seriales <em>no bloqueados</em>.
          </p>

          <div className="bg-gray-50 rounded-lg px-4 py-3 text-xs text-gray-600 space-y-1">
            {filtros.fecha_desde && <div>Desde: <span className="font-mono">{filtros.fecha_desde}</span></div>}
            {filtros.fecha_hasta && <div>Hasta: <span className="font-mono">{filtros.fecha_hasta}</span></div>}
            {filtros.cod_men && <div>Mensajero: <span className="font-mono">{filtros.cod_men}</span></div>}
            {filtros.planilla && <div>Planilla: <span className="font-mono">{filtros.planilla}</span></div>}
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={soloPrecioCero}
              onChange={(e) => setSoloPrecioCero(e.target.checked)}
              className="rounded"
            />
            Solo seriales con precio = $0
          </label>

          {result && (
            <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800">
              <p className="font-medium">Completado</p>
              <p>{result.seriales_actualizados} seriales actualizados · {result.seriales_sin_precio} sin precio</p>
            </div>
          )}

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              {result ? "Cerrar" : "Cancelar"}
            </button>
            {!result && (
              <button
                onClick={handleRun}
                disabled={running}
                className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-60 flex items-center gap-2"
              >
                {running && <RefreshCw size={14} className="animate-spin" />}
                {running ? "Recalculando..." : "Recalcular"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Panel bloqueo masivo ──────────────────────────────────────────────────────
interface BloqueoRangoPanelProps {
  filtros: { fecha_desde: string; fecha_hasta: string; cod_men: string };
  onDone: () => void;
}

function BloqueoRangoPanel({ filtros, onDone }: BloqueoRangoPanelProps) {
  const [fd, setFd] = useState(filtros.fecha_desde);
  const [fh, setFh] = useState(filtros.fecha_hasta);
  const [codMen, setCodMen] = useState(filtros.cod_men);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BloquearRangoResult | null>(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);

  async function handleBloquear() {
    if (!fd || !fh) return;
    setRunning(true);
    setError("");
    try {
      const res = await gestionesApi.bloquearRango({
        fecha_desde: fd,
        fecha_hasta: fh,
        cod_men: codMen || undefined,
      });
      setResult(res.data);
      setConfirm(false);
      onDone();
    } catch {
      setError("Error al bloquear seriales");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-amber-900 flex items-center gap-2">
        <ShieldCheck size={16} />
        Bloqueo masivo por rango de fechas
      </h3>
      <p className="text-xs text-amber-700">
        Marca todos los seriales del rango como <em>editado_manualmente = true</em> para
        protegerlos de recálculos automáticos.
      </p>

      <div className="grid grid-cols-3 gap-2">
        <div>
          <label className="block text-xs font-medium text-amber-800 mb-1">Desde</label>
          <input
            type="date"
            value={fd}
            onChange={(e) => { setFd(e.target.value); setResult(null); }}
            className="w-full border border-amber-300 rounded-lg px-2 py-1.5 text-sm bg-white"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-amber-800 mb-1">Hasta</label>
          <input
            type="date"
            value={fh}
            onChange={(e) => { setFh(e.target.value); setResult(null); }}
            className="w-full border border-amber-300 rounded-lg px-2 py-1.5 text-sm bg-white"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-amber-800 mb-1">Mensajero (opcional)</label>
          <input
            type="text"
            placeholder="Ej. MN01"
            value={codMen}
            onChange={(e) => { setCodMen(e.target.value); setResult(null); }}
            className="w-full border border-amber-300 rounded-lg px-2 py-1.5 text-sm bg-white"
          />
        </div>
      </div>

      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-sm text-green-800">
          {result.seriales_actualizados} seriales bloqueados en {result.planillas_afectadas} planillas.
        </div>
      )}

      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}

      {!confirm ? (
        <button
          onClick={() => setConfirm(true)}
          disabled={!fd || !fh}
          className="px-4 py-2 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium disabled:opacity-50"
        >
          Bloquear rango
        </button>
      ) : (
        <div className="flex items-center gap-3">
          <span className="text-sm text-amber-800 font-medium">¿Confirmar bloqueo masivo?</span>
          <button
            onClick={handleBloquear}
            disabled={running}
            className="px-3 py-1.5 text-sm bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium disabled:opacity-60"
          >
            {running ? "Bloqueando..." : "Sí, bloquear"}
          </button>
          <button
            onClick={() => setConfirm(false)}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancelar
          </button>
        </div>
      )}
    </div>
  );
}

// ── Buscador de planilla individual ──────────────────────────────────────────
function BuscarPlanillaSection() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [busqueda, setBusqueda] = useState("");

  const { data, isFetching, isError } = useQuery({
    queryKey: ["planilla-busqueda", busqueda],
    queryFn: () =>
      busqueda
        ? gestionesApi.planillasResumen({ planilla: busqueda }).then((r) => r.data)
        : Promise.resolve([]),
    enabled: !!busqueda,
  });

  const bloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.bloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planilla-busqueda", busqueda] }),
  });
  const desbloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.desbloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planilla-busqueda", busqueda] }),
  });
  const toggleRevisada = useMutation({
    mutationFn: ({ planilla, revisada }: { planilla: string; revisada: boolean }) =>
      revisada
        ? gestionesApi.desmarcarRevisada(planilla)
        : gestionesApi.marcarRevisada(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planilla-busqueda", busqueda] }),
  });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setBusqueda(input.trim());
  }

  const resultados = data ?? [];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4">
      <h2 className="text-sm font-semibold text-gray-800 mb-3">Buscar planilla</h2>
      <form onSubmit={handleSearch} className="flex gap-2 mb-3">
        <input
          type="text"
          placeholder="Número de planilla exacto"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-50"
        >
          Buscar
        </button>
        {busqueda && (
          <button
            type="button"
            onClick={() => { setBusqueda(""); setInput(""); }}
            className="px-3 py-2 text-sm border border-gray-300 rounded-lg text-gray-500 hover:bg-gray-50"
          >
            <X size={14} />
          </button>
        )}
      </form>

      {isFetching && (
        <p className="text-sm text-gray-400">Buscando…</p>
      )}

      {!isFetching && isError && (
        <p className="text-sm text-red-600">Error al buscar la planilla.</p>
      )}

      {!isFetching && busqueda && resultados.length === 0 && (
        <p className="text-sm text-gray-400">No se encontró la planilla <span className="font-mono">{busqueda}</span>.</p>
      )}

      {resultados.length > 0 && (
        <div className="space-y-2">
          {resultados.map((p) => {
            const totalCli = p.total_cliente;
            const totalMen = p.total_mensajero;
            return (
              <div
                key={`${p.planilla}-${p.cod_men}`}
                className={`border rounded-lg p-4 ${p.revisada ? "border-green-300 bg-green-50/40" : "border-gray-200"}`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <span className="font-mono text-sm font-semibold text-gray-900">{p.planilla}</span>
                    <span className="ml-2 text-xs text-gray-500">
                      {p.cod_men}{p.mensajero_nombre ? ` · ${p.mensajero_nombre}` : ""}
                    </span>
                    {p.fecha_escaner && (
                      <span className="ml-2 text-xs text-gray-400">{p.fecha_escaner}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {/* Revisada */}
                    <button
                      onClick={() => toggleRevisada.mutate({ planilla: p.planilla, revisada: p.revisada })}
                      title={p.revisada ? "Quitar revisión" : "Marcar revisada"}
                      className={`transition-colors ${p.revisada ? "text-green-600 hover:text-green-800" : "text-gray-300 hover:text-green-500"}`}
                    >
                      {p.revisada ? <CheckCircle size={16} /> : <Circle size={16} />}
                    </button>
                    {/* Bloquear / desbloquear */}
                    {p.bloqueada ? (
                      <button
                        onClick={() => desbloquear.mutate(p.planilla)}
                        className="text-gray-400 hover:text-amber-500 transition-colors"
                        title="Desbloquear"
                      >
                        <Unlock size={15} />
                      </button>
                    ) : (
                      <button
                        onClick={() => bloquear.mutate(p.planilla)}
                        className="text-gray-400 hover:text-green-600 transition-colors"
                        title="Bloquear"
                      >
                        <Lock size={15} />
                      </button>
                    )}
                    {/* Ver seriales */}
                    <button
                      onClick={() => navigate(`/gestiones?planilla=${encodeURIComponent(p.planilla)}`)}
                      className="text-gray-400 hover:text-primary transition-colors"
                      title="Ver seriales"
                    >
                      <List size={15} />
                    </button>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-5 gap-3 text-xs">
                  <div>
                    <p className="text-gray-400 uppercase tracking-wide">Entregas</p>
                    <p className="font-semibold text-gray-800">{p.entregas}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 uppercase tracking-wide">Devoluciones</p>
                    <p className="font-semibold text-gray-800">{p.devoluciones}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 uppercase tracking-wide">Total seriales</p>
                    <p className="font-semibold text-gray-800 flex items-center gap-1">
                      {p.total_seriales}
                      {p.con_precio_cero > 0 && (
                        <span title={`${p.con_precio_cero} sin precio`} className="text-amber-500">
                          <AlertTriangle size={11} className="inline" />
                        </span>
                      )}
                    </p>
                  </div>
                  <div>
                    <p className="text-gray-400 uppercase tracking-wide">Val. mensajero</p>
                    <p className="font-semibold text-gray-800">${totalMen.toLocaleString("es-CO")}</p>
                  </div>
                  <div>
                    <p className="text-gray-400 uppercase tracking-wide">Val. cliente</p>
                    <p className="font-semibold text-gray-800">${totalCli.toLocaleString("es-CO")}</p>
                  </div>
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    p.bloqueada ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
                  }`}>
                    {p.bloqueada ? "Bloqueada" : "Abierta"}
                  </span>
                  {p.revisada && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      <CheckCircle size={10} /> Revisada
                    </span>
                  )}
                  {p.con_precio_cero > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                      <AlertTriangle size={10} /> {p.con_precio_cero} sin precio
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Utilidad CSV ──────────────────────────────────────────────────────────────
function exportarCSV(planillas: PlanillaResumen[]) {
  const cols = [
    "Planilla", "Mensajero", "Nombre", "Fecha", "Entregas", "Devoluciones",
    "Total Seriales", "Valor Mensajero", "Valor Cliente", "Bloqueada", "Revisada",
  ];
  const rows = planillas.map((p) => [
    p.planilla,
    p.cod_men,
    p.mensajero_nombre ?? "",
    p.fecha_escaner ?? "",
    p.entregas,
    p.devoluciones,
    p.total_seriales,
    p.total_mensajero,
    p.total_cliente,
    p.bloqueada ? "Sí" : "No",
    p.revisada ? "Sí" : "No",
  ]);

  const csv = [cols, ...rows]
    .map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
    .join("\n");

  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `planillas_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Página principal ──────────────────────────────────────────────────────────
export function PlanillasPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState<PlanillaResumen | null>(null);
  const [showRecalcular, setShowRecalcular] = useState(false);
  const [showBloqueoRango, setShowBloqueoRango] = useState(false);
  const [filtros, setFiltros] = useState({
    fecha_desde: new Date(new Date().getFullYear(), new Date().getMonth(), 1)
      .toISOString()
      .split("T")[0],
    fecha_hasta: new Date().toISOString().split("T")[0],
    cod_men: "",
    planilla: "",
  });

  const params = Object.fromEntries(Object.entries(filtros).filter(([, v]) => v !== ""));

  const { data: planillas = [], isLoading } = useQuery({
    queryKey: ["planillas", filtros],
    queryFn: () => gestionesApi.planillasResumen(params).then((r) => r.data),
  });

  const bloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.bloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planillas"] }),
  });

  const desbloquear = useMutation({
    mutationFn: (planilla: string) => gestionesApi.desbloquear(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planillas"] }),
  });

  const toggleRevisada = useMutation({
    mutationFn: ({ planilla, revisada }: { planilla: string; revisada: boolean }) =>
      revisada
        ? gestionesApi.desmarcarRevisada(planilla)
        : gestionesApi.marcarRevisada(planilla),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["planillas"] }),
  });

  const totalSeriales = planillas.reduce((s, p) => s + p.total_seriales, 0);
  const totalMensajero = planillas.reduce((s, p) => s + p.total_mensajero, 0);
  const sinPrecio = planillas.reduce((s, p) => s + p.con_precio_cero, 0);
  const bloqueadas = planillas.filter((p) => p.bloqueada).length;
  const revisadas = planillas.filter((p) => p.revisada).length;

  return (
    <div>
      {/* Encabezado */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Planillas</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {planillas.length} planillas · {totalSeriales.toLocaleString()} seriales
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportarCSV(planillas)}
            disabled={planillas.length === 0}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-600 disabled:opacity-40"
            title="Exportar CSV"
          >
            <Download size={14} />
            CSV
          </button>
          <button
            onClick={() => setShowRecalcular(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-600"
            title="Recalcular precios"
          >
            <RefreshCw size={14} />
            Recalcular
          </button>
          <button
            onClick={() => setShowBloqueoRango((v) => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg text-gray-600 ${
              showBloqueoRango
                ? "border-amber-400 bg-amber-50 text-amber-700"
                : "border-gray-300 hover:bg-gray-50"
            }`}
            title="Bloqueo masivo"
          >
            <ShieldCheck size={14} />
            Bloqueo masivo
            {showBloqueoRango ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {/* Buscador de planilla individual */}
      <BuscarPlanillaSection />

      {/* Filtros */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 grid grid-cols-4 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Desde</label>
          <input
            type="date"
            value={filtros.fecha_desde}
            onChange={(e) => setFiltros((f) => ({ ...f, fecha_desde: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Hasta</label>
          <input
            type="date"
            value={filtros.fecha_hasta}
            onChange={(e) => setFiltros((f) => ({ ...f, fecha_hasta: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Mensajero</label>
          <input
            type="text"
            placeholder="Código ej. MN01"
            value={filtros.cod_men}
            onChange={(e) => setFiltros((f) => ({ ...f, cod_men: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Planilla</label>
          <input
            type="text"
            placeholder="Número de planilla"
            value={filtros.planilla}
            onChange={(e) => setFiltros((f) => ({ ...f, planilla: e.target.value }))}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />
        </div>
      </div>

      {/* Panel bloqueo masivo */}
      {showBloqueoRango && (
        <div className="mb-4">
          <BloqueoRangoPanel
            filtros={filtros}
            onDone={() => qc.invalidateQueries({ queryKey: ["planillas"] })}
          />
        </div>
      )}

      {/* Métricas */}
      <div className="grid grid-cols-5 gap-4 mb-4">
        {[
          { label: "Planillas", value: planillas.length },
          { label: "Total seriales", value: totalSeriales.toLocaleString() },
          { label: "Total mensajero", value: `$${totalMensajero.toLocaleString("es-CO")}` },
          { label: "Sin precio", value: sinPrecio, warn: sinPrecio > 0 },
          {
            label: "Revisadas / Total",
            value: `${revisadas} / ${planillas.length}`,
          },
        ].map(({ label, value, warn }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 px-5 py-4">
            <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
            <p className={`text-xl font-semibold mt-1 ${warn ? "text-amber-600" : "text-gray-900"}`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Tabla */}
      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm min-w-[1000px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {[
                  "Planilla",
                  "Mensajero",
                  "Fecha",
                  "Entregas",
                  "Dev.",
                  "Total",
                  "Val. Mensajero",
                  "Val. Cliente",
                  "Estado",
                  "Revisada",
                  "",
                ].map((h) => (
                  <th
                    key={h}
                    className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {planillas.map((p) => (
                <tr
                  key={`${p.planilla}-${p.cod_men}`}
                  className={`hover:bg-gray-50 transition-colors ${
                    p.revisada ? "bg-green-50/40" : ""
                  }`}
                >
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{p.planilla || "—"}</td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{p.cod_men}</span>
                    {p.mensajero_nombre && (
                      <span className="text-gray-400 text-xs ml-1">· {p.mensajero_nombre}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                    {p.fecha_escaner ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{p.entregas}</td>
                  <td className="px-4 py-3 text-gray-700">{p.devoluciones}</td>
                  <td className="px-4 py-3">
                    <span className="font-medium text-gray-900">{p.total_seriales}</span>
                    {p.con_precio_cero > 0 && (
                      <span
                        className="ml-1 text-amber-500"
                        title={`${p.con_precio_cero} sin precio`}
                      >
                        <AlertTriangle size={12} className="inline" />
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <CurrencyCell value={p.total_mensajero} />
                  </td>
                  <td className="px-4 py-3">
                    <CurrencyCell value={p.total_cliente} />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        p.bloqueada ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {p.bloqueada ? "Bloqueada" : "Abierta"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() =>
                        toggleRevisada.mutate({ planilla: p.planilla, revisada: p.revisada })
                      }
                      title={p.revisada ? "Marcar como no revisada" : "Marcar como revisada"}
                      className={`transition-colors ${
                        p.revisada
                          ? "text-green-600 hover:text-green-800"
                          : "text-gray-300 hover:text-green-500"
                      }`}
                    >
                      {p.revisada ? (
                        <CheckCircle size={16} />
                      ) : (
                        <Circle size={16} />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setEditing(p)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Editar mensajero / precio"
                      >
                        <Pencil size={14} />
                      </button>
                      {p.bloqueada ? (
                        <button
                          onClick={() => desbloquear.mutate(p.planilla)}
                          className="text-gray-400 hover:text-amber-500 transition-colors"
                          title="Desbloquear planilla"
                        >
                          <Unlock size={14} />
                        </button>
                      ) : (
                        <button
                          onClick={() => bloquear.mutate(p.planilla)}
                          className="text-gray-400 hover:text-green-600 transition-colors"
                          title="Bloquear planilla"
                        >
                          <Lock size={14} />
                        </button>
                      )}
                      <button
                        onClick={() =>
                          navigate(`/gestiones?planilla=${encodeURIComponent(p.planilla)}`)
                        }
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Ver seriales"
                      >
                        <List size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {planillas.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              No hay planillas con estos filtros
            </div>
          )}
          {planillas.length > 0 && (
            <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
              <span>{planillas.length} planillas · {totalSeriales.toLocaleString()} seriales</span>
              <span>
                {bloqueadas} bloqueadas · {revisadas} revisadas
              </span>
            </div>
          )}
        </div>
      )}

      {editing && (
        <EditModal
          planilla={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["planillas"] });
            setEditing(null);
          }}
        />
      )}

      {showRecalcular && (
        <RecalcularModal
          filtros={filtros}
          onClose={() => setShowRecalcular(false)}
          onDone={() => {
            qc.invalidateQueries({ queryKey: ["planillas"] });
          }}
        />
      )}
    </div>
  );
}
