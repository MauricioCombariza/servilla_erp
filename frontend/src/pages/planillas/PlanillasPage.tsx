import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef, useEffect } from "react";
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
  Rows3,
  LayoutList,
} from "lucide-react";
import { gestionesApi, type RecalcularResult, type BloquearRangoResult, type BulkPatchItem, type PrecioCourierResult } from "@/api/gestiones";
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

// ── Panel de ajuste de precio para courier externo ────────────────────────────
interface CourierPrecioPanelProps {
  planilla: string;
  serialesBogota: number;
  serialesNacional: number;
  precioLocalDefault: number;
  precioNacionalDefault: number;
  onSaved: () => void;
}

function CourierPrecioPanel({
  planilla,
  serialesBogota,
  serialesNacional,
  precioLocalDefault,
  precioNacionalDefault,
  onSaved,
}: CourierPrecioPanelProps) {
  const [precioLocal, setPrecioLocal] = useState(precioLocalDefault);
  const [precioNacional, setPrecioNacional] = useState(precioNacionalDefault);
  const [guardando, setGuardando] = useState(false);
  const [resultado, setResultado] = useState<PrecioCourierResult | null>(null);
  const [error, setError] = useState("");

  const totalEstimado =
    serialesBogota * precioLocal + serialesNacional * precioNacional;

  async function aplicar() {
    setGuardando(true);
    setError("");
    setResultado(null);
    try {
      const res = await gestionesApi.precioCourier(planilla, {
        precio_local: precioLocal,
        precio_nacional: precioNacional,
      });
      setResultado(res.data);
      onSaved();
    } catch {
      setError("Error al aplicar precios");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="mx-4 my-3 bg-blue-50 border border-blue-200 rounded-xl p-4 space-y-3">
      <h4 className="text-xs font-semibold text-blue-800 uppercase tracking-wide">
        Ajuste de precio por ámbito — Courier Externo
      </h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Tarifa Local (Bogotá) $/serial
          </label>
          <input
            type="number"
            min={0}
            step={50}
            value={precioLocal}
            onChange={(e) => { setPrecioLocal(Number(e.target.value)); setResultado(null); }}
            className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs w-full focus:ring-1 focus:ring-blue-400 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">
            Tarifa Nacional $/serial
          </label>
          <input
            type="number"
            min={0}
            step={50}
            value={precioNacional}
            onChange={(e) => { setPrecioNacional(Number(e.target.value)); setResultado(null); }}
            className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs w-full focus:ring-1 focus:ring-blue-400 outline-none"
          />
        </div>
      </div>
      <div className="text-xs text-gray-700 bg-white border border-gray-100 rounded-lg px-3 py-2 space-y-1">
        <div className="flex justify-between">
          <span className="text-gray-500">Bogotá (local):</span>
          <span>
            {serialesBogota.toLocaleString()} × ${precioLocal.toLocaleString("es-CO")} ={" "}
            <span className="font-medium">${(serialesBogota * precioLocal).toLocaleString("es-CO")}</span>
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Nacional:</span>
          <span>
            {serialesNacional.toLocaleString()} × ${precioNacional.toLocaleString("es-CO")} ={" "}
            <span className="font-medium">${(serialesNacional * precioNacional).toLocaleString("es-CO")}</span>
          </span>
        </div>
        <div className="flex justify-between border-t border-gray-100 pt-1 font-semibold text-gray-800">
          <span>Total planilla:</span>
          <span>${totalEstimado.toLocaleString("es-CO")}</span>
        </div>
      </div>
      {resultado && (
        <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1">
          {resultado.seriales_actualizados} seriales actualizados — Bogotá: {resultado.bogota} · Nacional: {resultado.nacional}
        </p>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
      <button
        onClick={aplicar}
        disabled={guardando}
        className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium disabled:opacity-50 flex items-center gap-1.5"
      >
        {guardando && <RefreshCw size={11} className="animate-spin" />}
        {guardando ? "Aplicando…" : "Aplicar precios por ámbito"}
      </button>
    </div>
  );
}

// ── Tarjeta de planilla con detalle expandible ────────────────────────────────
interface PlanillaCardProps {
  p: PlanillaResumen;
  busqueda: string;
}

function PlanillaCard({ p, busqueda }: PlanillaCardProps) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [editando, setEditando] = useState(false);
  const [expandido, setExpandido] = useState(false);
  const [vistaOrden, setVistaOrden] = useState(false);
  const [seleccion, setSeleccion] = useState<Set<number>>(new Set());
  const [editPrecio, setEditPrecio] = useState<number>(0);
  const [editPrecioCliente, setEditPrecioCliente] = useState<number>(0);
  const [editCodMen, setEditCodMen] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorGuardar, setErrorGuardar] = useState("");

  const invalidar = () => {
    qc.invalidateQueries({ queryKey: ["planilla-busqueda", busqueda] });
    qc.invalidateQueries({ queryKey: ["planilla-detalle", p.planilla] });
  };

  const { data: seriales = [], isFetching: cargandoDetalle } = useQuery({
    queryKey: ["planilla-detalle", p.planilla],
    queryFn: () => gestionesApi.list({ planilla: p.planilla, limit: 500 }).then((r) => r.data),
    enabled: expandido,
  });

  const { data: personal = [] } = useQuery({
    queryKey: ["personal", true],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
    enabled: expandido,
  });

  const bloquear = useMutation({
    mutationFn: (id: string) => gestionesApi.bloquear(id),
    onSuccess: invalidar,
  });
  const desbloquear = useMutation({
    mutationFn: (id: string) => gestionesApi.desbloquear(id),
    onSuccess: invalidar,
  });
  const toggleRevisada = useMutation({
    mutationFn: ({ planilla, revisada }: { planilla: string; revisada: boolean }) =>
      revisada ? gestionesApi.desmarcarRevisada(planilla) : gestionesApi.marcarRevisada(planilla),
    onSuccess: invalidar,
  });
  const toggleLockSerial = useMutation({
    mutationFn: ({ id, val }: { id: number; val: boolean }) =>
      gestionesApi.patch(id, { editado_manualmente: val }),
    onSuccess: invalidar,
  });

  // Agrupar seriales por (cod_men, precio_mensajero)
  type Grupo = {
    key: string;
    cod_men: string;
    mensajero_nombre: string;
    precio: number;
    ids: number[];
    bloqueados: number;
  };
  const grupos: Grupo[] = Object.values(
    seriales.reduce<Record<string, Grupo>>((acc, s) => {
      const key = `${s.cod_men}||${s.precio_mensajero}`;
      if (!acc[key]) {
        acc[key] = {
          key,
          cod_men: s.cod_men,
          mensajero_nombre: s.mensajero?.nombre_completo ?? s.cod_men,
          precio: s.precio_mensajero,
          ids: [],
          bloqueados: 0,
        };
      }
      acc[key].ids.push(s.id);
      if (s.editado_manualmente) acc[key].bloqueados++;
      return acc;
    }, {})
  );

  // Agrupar por orden (para vista "por orden")
  type GrupoOrden = {
    key: string;
    orden: string | null;
    cliente_nombre: string;
    ids: number[];
    bloqueados: number;
    valor_total: number;
    valor_cliente: number;
  };
  const gruposOrden: GrupoOrden[] = Object.values(
    seriales.reduce<Record<string, GrupoOrden>>((acc, s) => {
      const key = s.orden ?? "__sin_orden__";
      if (!acc[key]) {
        acc[key] = {
          key,
          orden: s.orden,
          cliente_nombre: s.cliente?.nombre_empresa ?? "—",
          ids: [],
          bloqueados: 0,
          valor_total: 0,
          valor_cliente: 0,
        };
      }
      acc[key].ids.push(s.id);
      if (s.editado_manualmente) acc[key].bloqueados++;
      acc[key].valor_total += Number(s.precio_mensajero);
      acc[key].valor_cliente += Number(s.precio_cliente);
      return acc;
    }, {})
  );

  // Courier externo
  const isCourierExterno =
    p.tipo_personal === "courier_externo" ||
    (seriales.length > 0 && seriales[0].mensajero?.tipo_personal === "courier_externo");
  const serialesBogota = seriales.filter((s) => s.ambito === "bogota").length;
  const serialesNacional = seriales.length - serialesBogota;
  const precioLocalDefecto =
    seriales[0]?.mensajero?.precio_local ?? p.precio_promedio_mensajero;
  const precioNacionalDefecto =
    seriales[0]?.mensajero?.precio_nacional ?? p.precio_promedio_mensajero;

  const preciosUnicos = [...new Set(seriales.map((s) => s.precio_mensajero))];
  const preciosMixtos = preciosUnicos.length > 1;

  const selIds = [...seleccion];
  const selSeriales = seriales.filter((s) => seleccion.has(s.id));
  const totalSelValMen = selSeriales.reduce((a, s) => a + s.precio_mensajero, 0);
  const totalSelValCli = selSeriales.reduce((a, s) => a + s.precio_cliente, 0);
  const nuevoTotalMen = editPrecio > 0 ? selIds.length * editPrecio : totalSelValMen;
  const nuevoTotalCli = editPrecioCliente > 0 ? selIds.length * editPrecioCliente : totalSelValCli;
  const diffMen = nuevoTotalMen - totalSelValMen;
  const diffCli = nuevoTotalCli - totalSelValCli;

  function toggleIds(ids: number[]) {
    setSeleccion((prev) => {
      const next = new Set(prev);
      const todosEnSel = ids.every((id) => next.has(id));
      if (todosEnSel) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  }

  function toggleGrupo(g: Grupo) {
    toggleIds(g.ids);
  }

  async function guardarSeleccion() {
    if (selIds.length === 0) return;
    setGuardando(true);
    setErrorGuardar("");
    try {
      const items: BulkPatchItem[] = selIds.map((id) => ({
        id,
        ...(editPrecio > 0 ? { precio_mensajero: editPrecio } : {}),
        ...(editPrecioCliente > 0 ? { precio_cliente: editPrecioCliente } : {}),
        ...(editCodMen ? { cod_men: editCodMen } : {}),
      }));
      await gestionesApi.bulkPatch(items);
      setSeleccion(new Set());
      setEditPrecio(0);
      setEditPrecioCliente(0);
      setEditCodMen("");
      invalidar();
    } catch {
      setErrorGuardar("Error al guardar. Intente de nuevo.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <>
      {editando && (
        <EditModal
          planilla={p}
          onClose={() => setEditando(false)}
          onSaved={() => { invalidar(); setEditando(false); }}
        />
      )}

      <div className={`border rounded-lg ${p.revisada ? "border-green-300 bg-green-50/30" : "border-gray-200"}`}>
        {/* Cabecera */}
        <div className="p-4">
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
              <button onClick={() => setEditando(true)} className="text-gray-400 hover:text-primary transition-colors" title="Editar mensajero / precio">
                <Pencil size={15} />
              </button>
              <button
                onClick={() => toggleRevisada.mutate({ planilla: p.planilla, revisada: p.revisada })}
                title={p.revisada ? "Quitar revisión" : "Marcar revisada"}
                className={`transition-colors ${p.revisada ? "text-green-600 hover:text-green-800" : "text-gray-300 hover:text-green-500"}`}
              >
                {p.revisada ? <CheckCircle size={16} /> : <Circle size={16} />}
              </button>
              {p.bloqueada ? (
                <button onClick={() => desbloquear.mutate(p.planilla)} className="text-gray-400 hover:text-amber-500 transition-colors" title="Desbloquear">
                  <Unlock size={15} />
                </button>
              ) : (
                <button onClick={() => bloquear.mutate(p.planilla)} className="text-gray-400 hover:text-green-600 transition-colors" title="Bloquear">
                  <Lock size={15} />
                </button>
              )}
              <button onClick={() => navigate(`/gestiones?planilla=${encodeURIComponent(p.planilla)}`)} className="text-gray-400 hover:text-primary transition-colors" title="Ver seriales">
                <List size={15} />
              </button>
              <button
                onClick={() => setExpandido((v) => !v)}
                className={`flex items-center gap-1 text-xs px-2 py-1 rounded border transition-colors ${expandido ? "border-primary text-primary bg-blue-50" : "border-gray-300 text-gray-500 hover:bg-gray-50"}`}
                title="Ver registros detallados"
              >
                <Rows3 size={13} />
                {expandido ? "Ocultar" : "Registros"}
              </button>
            </div>
          </div>

          {/* Métricas */}
          <div className="mt-3 grid grid-cols-5 gap-3 text-xs">
            {[
              { label: "Entregas", val: p.entregas },
              { label: "Devoluciones", val: p.devoluciones },
              { label: "Total seriales", val: p.total_seriales, warn: p.con_precio_cero > 0, warnTxt: `${p.con_precio_cero} sin precio` },
              { label: "Val. mensajero", val: `$${p.total_mensajero.toLocaleString("es-CO")}` },
              { label: "Val. cliente", val: `$${p.total_cliente.toLocaleString("es-CO")}` },
            ].map(({ label, val, warn, warnTxt }) => (
              <div key={label}>
                <p className="text-gray-400 uppercase tracking-wide">{label}</p>
                <p className="font-semibold text-gray-800 flex items-center gap-1">
                  {val}
                  {warn && <span title={warnTxt} className="text-amber-500"><AlertTriangle size={11} /></span>}
                </p>
              </div>
            ))}
          </div>

          {/* Badges */}
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${p.bloqueada ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"}`}>
              {p.bloqueada ? "Bloqueada" : "Abierta"}
            </span>
            {p.revisada && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <CheckCircle size={10} /> Revisada
              </span>
            )}
            {preciosMixtos && expandido && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                <AlertTriangle size={10} /> Precios mixtos ({preciosUnicos.length} tarifas)
              </span>
            )}
            {p.con_precio_cero > 0 && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                <AlertTriangle size={10} /> {p.con_precio_cero} sin precio
              </span>
            )}
          </div>
        </div>

        {/* Tabla de detalle expandible */}
        {expandido && (
          <div className="border-t border-gray-100">
            {cargandoDetalle ? (
              <p className="text-sm text-gray-400 px-4 py-3">Cargando registros…</p>
            ) : seriales.length === 0 ? (
              <p className="text-sm text-gray-400 px-4 py-3">Sin registros.</p>
            ) : (
              <>
                {/* Panel courier externo */}
                {isCourierExterno && (
                  <CourierPrecioPanel
                    planilla={p.planilla}
                    serialesBogota={serialesBogota}
                    serialesNacional={serialesNacional}
                    precioLocalDefault={precioLocalDefecto}
                    precioNacionalDefault={precioNacionalDefecto}
                    onSaved={invalidar}
                  />
                )}

                {/* Barra de control */}
                <div className="px-4 pt-3 pb-1 flex items-center gap-3 flex-wrap">
                  <span className="text-xs font-medium text-gray-600">
                    {vistaOrden
                      ? `${gruposOrden.length} orden${gruposOrden.length !== 1 ? "es" : ""}`
                      : `${grupos.length} grupo${grupos.length !== 1 ? "s" : ""}`
                    }{" "}· {seriales.length} seriales
                  </span>

                  {/* Toggle de vista */}
                  <div className="flex border border-gray-200 rounded-lg overflow-hidden text-xs">
                    <button
                      onClick={() => setVistaOrden(false)}
                      className={`flex items-center gap-1 px-2 py-1 ${!vistaOrden ? "bg-primary text-white" : "text-gray-500 hover:bg-gray-50"}`}
                      title="Agrupar por tarifa"
                    >
                      <Rows3 size={11} /> Por tarifa
                    </button>
                    <button
                      onClick={() => setVistaOrden(true)}
                      className={`flex items-center gap-1 px-2 py-1 ${vistaOrden ? "bg-primary text-white" : "text-gray-500 hover:bg-gray-50"}`}
                      title="Agrupar por orden"
                    >
                      <LayoutList size={11} /> Por orden
                    </button>
                  </div>

                  {seleccion.size > 0 && (
                    <button onClick={() => setSeleccion(new Set())} className="text-xs text-gray-400 hover:text-gray-600 underline">
                      Limpiar selección ({seleccion.size})
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (seleccion.size === seriales.length) setSeleccion(new Set());
                      else setSeleccion(new Set(seriales.map((s) => s.id)));
                    }}
                    className="text-xs text-gray-400 hover:text-gray-600 underline"
                  >
                    {seleccion.size === seriales.length ? "Deseleccionar todos" : "Seleccionar todos"}
                  </button>
                </div>

                <div className="overflow-x-auto">
                  {!vistaOrden ? (
                    // ── Vista por tarifa (grupos) ──────────────────────────
                    <table className="w-full text-xs min-w-[600px]">
                      <thead className="bg-gray-50 border-y border-gray-100">
                        <tr>
                          <th className="px-3 py-2 w-8"></th>
                          <th className="px-3 py-2 text-left text-gray-500 font-medium">Mensajero</th>
                          <th className="px-3 py-2 text-left text-gray-500 font-medium">Precio</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">Seriales</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">Valor</th>
                          <th className="px-3 py-2 text-center text-gray-500 font-medium">🔒</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {grupos.map((g) => {
                          const todosEnSel = g.ids.every((id) => seleccion.has(id));
                          const algunEnSel = g.ids.some((id) => seleccion.has(id));
                          const todosBloq = g.bloqueados === g.ids.length;
                          return (
                            <tr
                              key={g.key}
                              className={`cursor-pointer ${todosEnSel ? "bg-blue-50" : algunEnSel ? "bg-blue-50/40" : "hover:bg-gray-50"}`}
                              onClick={() => toggleGrupo(g)}
                            >
                              <td className="px-3 py-2">
                                <input type="checkbox" checked={todosEnSel} readOnly className="rounded" />
                              </td>
                              <td className="px-3 py-2 font-medium text-gray-800">
                                {g.cod_men}
                                <span className="ml-1 text-gray-400 font-normal">
                                  {g.mensajero_nombre !== g.cod_men ? `· ${g.mensajero_nombre}` : ""}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-gray-700">${g.precio.toLocaleString("es-CO")}</td>
                              <td className="px-3 py-2 text-right text-gray-700">{g.ids.length}</td>
                              <td className="px-3 py-2 text-right text-gray-700">
                                ${(g.precio * g.ids.length).toLocaleString("es-CO")}
                              </td>
                              <td className="px-3 py-2 text-center" onClick={(e) => e.stopPropagation()}>
                                <button
                                  onClick={() => {
                                    g.ids.forEach((id) => {
                                      const s = seriales.find((s) => s.id === id);
                                      if (s) toggleLockSerial.mutate({ id, val: !s.editado_manualmente });
                                    });
                                  }}
                                  title={todosBloq ? "Desbloquear grupo" : "Bloquear grupo"}
                                  className={`transition-colors ${todosBloq ? "text-green-600 hover:text-green-800" : "text-gray-300 hover:text-green-500"}`}
                                >
                                  {todosBloq ? <Lock size={13} /> : <Unlock size={13} />}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    // ── Vista por orden ────────────────────────────────────
                    <table className="w-full text-xs min-w-[720px]">
                      <thead className="bg-gray-50 border-y border-gray-100">
                        <tr>
                          <th className="px-3 py-2 w-8"></th>
                          <th className="px-3 py-2 text-left text-gray-500 font-medium">Orden</th>
                          <th className="px-3 py-2 text-left text-gray-500 font-medium">Cliente</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">Seriales</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">$/Men.</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">Val. Men.</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">$/Cli.</th>
                          <th className="px-3 py-2 text-right text-gray-500 font-medium">Val. Cliente</th>
                          <th className="px-3 py-2 text-center text-gray-500 font-medium">🔒</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {gruposOrden.map((g) => {
                          const todosEnSel = g.ids.every((id) => seleccion.has(id));
                          const algunEnSel = g.ids.some((id) => seleccion.has(id));
                          const todosBloq = g.bloqueados === g.ids.length;
                          const precioMenProm = g.ids.length > 0 ? g.valor_total / g.ids.length : 0;
                          const precioCliProm = g.ids.length > 0 ? g.valor_cliente / g.ids.length : 0;
                          return (
                            <tr
                              key={g.key}
                              className={`cursor-pointer ${todosEnSel ? "bg-blue-50" : algunEnSel ? "bg-blue-50/40" : "hover:bg-gray-50"}`}
                              onClick={() => toggleIds(g.ids)}
                            >
                              <td className="px-3 py-2">
                                <input type="checkbox" checked={todosEnSel} readOnly className="rounded" />
                              </td>
                              <td className="px-3 py-2 font-mono text-gray-700">{g.orden ?? "—"}</td>
                              <td className="px-3 py-2 text-gray-600 truncate max-w-[140px]">{g.cliente_nombre}</td>
                              <td className="px-3 py-2 text-right text-gray-700">{g.ids.length}</td>
                              <td className="px-3 py-2 text-right text-gray-500">
                                ${precioMenProm.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-700">
                                ${g.valor_total.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                              </td>
                              <td className="px-3 py-2 text-right text-gray-500">
                                ${precioCliProm.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                              </td>
                              <td className="px-3 py-2 text-right font-medium text-gray-700">
                                ${g.valor_cliente.toLocaleString("es-CO", { maximumFractionDigits: 0 })}
                              </td>
                              <td className="px-3 py-2 text-center" onClick={(e) => e.stopPropagation()}>
                                <button
                                  onClick={() => {
                                    g.ids.forEach((id) => {
                                      const s = seriales.find((s) => s.id === id);
                                      if (s) toggleLockSerial.mutate({ id, val: !s.editado_manualmente });
                                    });
                                  }}
                                  title={todosBloq ? "Desbloquear orden" : "Bloquear orden"}
                                  className={`transition-colors ${todosBloq ? "text-green-600 hover:text-green-800" : "text-gray-300 hover:text-green-500"}`}
                                >
                                  {todosBloq ? <Lock size={13} /> : <Unlock size={13} />}
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Panel de edición de seleccionados */}
                {seleccion.size > 0 && (
                  <div className="border-t border-blue-100 bg-blue-50/60 px-4 py-3 space-y-3">
                    <p className="text-xs font-semibold text-blue-800">
                      {seleccion.size} serial{seleccion.size !== 1 ? "es" : ""} seleccionado{seleccion.size !== 1 ? "s" : ""}
                      {" · "}Mensajero actual: ${totalSelValMen.toLocaleString("es-CO")}
                      {" · "}Cliente actual: ${totalSelValCli.toLocaleString("es-CO")}
                    </p>
                    <div className="flex flex-wrap gap-3 items-end">
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">Mensajero (opcional)</label>
                        <select
                          value={editCodMen}
                          onChange={(e) => setEditCodMen(e.target.value)}
                          className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs bg-white"
                        >
                          <option value="">— sin cambio —</option>
                          {personal.map((per) => (
                            <option key={per.id} value={per.codigo}>
                              {per.codigo} · {per.nombre_completo}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">Precio mensajero/serial (0 = sin cambio)</label>
                        <input
                          type="number"
                          min={0}
                          step={50}
                          value={editPrecio}
                          onChange={(e) => setEditPrecio(Number(e.target.value))}
                          className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs w-32"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">Precio cliente/serial (0 = sin cambio)</label>
                        <input
                          type="number"
                          min={0}
                          step={50}
                          value={editPrecioCliente}
                          onChange={(e) => setEditPrecioCliente(Number(e.target.value))}
                          className="border border-gray-300 rounded-lg px-2 py-1.5 text-xs w-32"
                        />
                      </div>
                      {(editPrecio > 0 || editPrecioCliente > 0) && (
                        <div className="text-xs text-gray-600 space-y-0.5">
                          {editPrecio > 0 && (
                            <div>
                              Mensajero nuevo: <span className="font-semibold">${nuevoTotalMen.toLocaleString("es-CO")}</span>
                              <span className={`ml-1 ${diffMen >= 0 ? "text-green-700" : "text-red-600"}`}>
                                ({diffMen >= 0 ? "+" : ""}{diffMen.toLocaleString("es-CO")})
                              </span>
                            </div>
                          )}
                          {editPrecioCliente > 0 && (
                            <div>
                              Cliente nuevo: <span className="font-semibold">${nuevoTotalCli.toLocaleString("es-CO")}</span>
                              <span className={`ml-1 ${diffCli >= 0 ? "text-green-700" : "text-red-600"}`}>
                                ({diffCli >= 0 ? "+" : ""}{diffCli.toLocaleString("es-CO")})
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {errorGuardar && <p className="text-xs text-red-600">{errorGuardar}</p>}
                    <div className="flex gap-2">
                      <button
                        onClick={guardarSeleccion}
                        disabled={guardando || (editPrecio === 0 && editPrecioCliente === 0 && !editCodMen)}
                        className="px-3 py-1.5 text-xs bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-50"
                      >
                        {guardando ? "Guardando…" : "Guardar cambios"}
                      </button>
                      <button
                        onClick={() => { setSeleccion(new Set()); setEditPrecio(0); setEditPrecioCliente(0); setEditCodMen(""); }}
                        className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-gray-50"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// ── Combobox de mensajero con búsqueda ───────────────────────────────────────
function MensajeroCombobox({
  value,
  onChange,
}: {
  value: string;
  onChange: (cod: string) => void;
}) {
  const { data: personal = [] } = useQuery({
    queryKey: ["personal-activos"],
    queryFn: () => personalApi.list({ activo: true }).then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const [texto, setTexto] = useState(value);
  const [abierto, setAbierto] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Sincronizar cuando el valor externo cambia (ej. reset)
  useEffect(() => {
    if (!value) setTexto("");
  }, [value]);

  // Cerrar al hacer click fuera
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const q = texto.toLowerCase();
  const opciones = personal.filter(
    (p) =>
      p.codigo.toLowerCase().includes(q) ||
      p.nombre_completo.toLowerCase().includes(q)
  );

  function seleccionar(p: (typeof personal)[0]) {
    setTexto(`${p.codigo} · ${p.nombre_completo}`);
    onChange(p.codigo);
    setAbierto(false);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setTexto(e.target.value);
    setAbierto(true);
    if (!e.target.value) onChange("");
  }

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        placeholder="Código o nombre"
        value={texto}
        onChange={handleChange}
        onFocus={() => setAbierto(true)}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
      />
      {abierto && opciones.length > 0 && (
        <ul className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto text-sm">
          {opciones.map((p) => (
            <li
              key={p.codigo}
              onMouseDown={() => seleccionar(p)}
              className="px-3 py-2 cursor-pointer hover:bg-primary/10 flex gap-2"
            >
              <span className="font-mono text-xs text-gray-500 shrink-0 pt-0.5">{p.codigo}</span>
              <span className="text-gray-800">{p.nombre_completo}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── Buscador de planilla individual ──────────────────────────────────────────
function BuscarPlanillaSection() {
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

      {isFetching && <p className="text-sm text-gray-400">Buscando…</p>}
      {!isFetching && isError && <p className="text-sm text-red-600">Error al buscar la planilla.</p>}
      {!isFetching && busqueda && resultados.length === 0 && (
        <p className="text-sm text-gray-400">No se encontró la planilla <span className="font-mono">{busqueda}</span>.</p>
      )}

      {resultados.length > 0 && (
        <div className="space-y-2">
          {resultados.map((p) => (
            <PlanillaCard key={`${p.planilla}-${p.cod_men}`} p={p} busqueda={busqueda} />
          ))}
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
          <MensajeroCombobox
            value={filtros.cod_men}
            onChange={(cod) => setFiltros((f) => ({ ...f, cod_men: cod }))}
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
                  "$/Envío",
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
                    <CurrencyCell value={p.precio_promedio_cliente} />
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
