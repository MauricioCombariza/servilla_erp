import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, KeyRound, Pencil, Plus, ShieldAlert, X } from "lucide-react";
import {
  clavesExternasApi,
  type CategoriaClave,
  type ClaveExterna,
  type ClaveExternaDatos,
} from "@/api/clavesExternas";

/**
 * Registro de claves de sistemas fuera del ERP (SER-MNT-F-02-2 / F-02-3): FortiGate,
 * servidores, bases de datos, correo… Vencen según SER-MNT-PR-02 §20.3.
 * El ERP no guarda ni cambia esas claves: solo registra quién las custodia y cuándo se cambiaron.
 */

const ESTADO: Record<ClaveExterna["estado"], { texto: string; clase: string }> = {
  vencida: { texto: "Vencida", clase: "bg-red-50 text-red-700" },
  sin_registro: { texto: "Sin registro", clase: "bg-red-50 text-red-700" },
  por_vencer: { texto: "Por vencer", clase: "bg-amber-50 text-amber-700" },
  al_dia: { texto: "Al día", clase: "bg-green-50 text-green-700" },
};

const campo = "w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none";
const fecha = (d: string | null) => (d ? new Date(`${d}T12:00:00`).toLocaleDateString("es-CO") : "—");
const hoyISO = () => new Date().toLocaleDateString("sv-SE"); // AAAA-MM-DD en hora local

function errorDe(e: unknown): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg).replace(/^Value error, /, "");
  return "Error al guardar";
}

function AvisoSinClaves() {
  return (
    <p className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
      <ShieldAlert size={14} className="mt-0.5 flex-shrink-0" />
      Nunca escribas la clave aquí. La clave va solo en el sobre sellado de la bóveda.
    </p>
  );
}

function Modal({ titulo, onClose, children }: { titulo: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">{titulo}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>
        <div className="p-6 space-y-4">{children}</div>
      </div>
    </div>
  );
}

function CuentaForm({ inicial, categorias, onClose, onSaved }: {
  inicial: ClaveExterna | null; categorias: CategoriaClave[]; onClose: () => void; onSaved: () => void;
}) {
  const [d, setD] = useState<Partial<ClaveExternaDatos>>(
    inicial ?? { categoria: categorias[0]?.clave ?? "", ultimo_cambio: null },
  );
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const set = (k: keyof ClaveExternaDatos) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setD({ ...d, [k]: e.target.value === "" ? null : e.target.value });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setGuardando(true);
    setError("");
    const datos = { ...d, periodicidad_dias: d.periodicidad_dias ? Number(d.periodicidad_dias) : null };
    try {
      if (inicial) {
        const { ultimo_cambio: _omit, ...resto } = datos; // la fecha cambia solo registrando un cambio
        await clavesExternasApi.update(inicial.id, resto);
      } else {
        await clavesExternasApi.create(datos);
      }
      onSaved();
    } catch (err) {
      setError(errorDe(err));
    } finally {
      setGuardando(false);
    }
  }

  const texto = (k: keyof ClaveExternaDatos, label: string, req = false) => (
    <div>
      <label className="block text-xs font-medium text-gray-700 mb-1">{label}{req && " *"}</label>
      <input value={(d[k] as string | null) ?? ""} onChange={set(k)} required={req} className={campo} />
    </div>
  );

  return (
    <Modal titulo={inicial ? "Editar cuenta" : "Nueva cuenta"} onClose={onClose}>
      <form onSubmit={guardar} className="space-y-4">
        <AvisoSinClaves />
        <div className="grid grid-cols-2 gap-3">
          {texto("aplicacion", "Aplicación", true)}
          {texto("usuario", "Usuario de la cuenta", true)}
          {texto("sistema", "Sistema")}
          {texto("ambiente", "Ubicación")}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Categoría (§20.3) *</label>
            <select value={d.categoria ?? ""} onChange={set("categoria")} className={`${campo} bg-white`}>
              {categorias.map((c) => <option key={c.clave} value={c.clave}>{c.nombre} ({c.dias} días)</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Días propios (opcional)</label>
            <input type="number" min={1} max={730} value={d.periodicidad_dias ?? ""} onChange={set("periodicidad_dias")}
              placeholder="Los de la categoría" className={campo} />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {texto("custodio_1", "Custodio 1")}
          {texto("custodio_2", "Custodio 2")}
          {texto("sobre_no", "Sobre No.")}
          {texto("cofre_no", "Cofre No.")}
        </div>
        {!inicial && (
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Último cambio conocido</label>
            <input type="date" max={hoyISO()} value={d.ultimo_cambio ?? ""} onChange={set("ultimo_cambio")} className={campo} />
            <p className="text-xs text-gray-500 mt-1">Si no se sabe, déjalo vacío: queda como vencida hasta que se cambie.</p>
          </div>
        )}
        {texto("notas", "Notas")}
        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</button>
          <button type="submit" disabled={guardando} className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-60">
            {guardando ? "Guardando..." : "Guardar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CambioForm({ cuenta, onClose, onSaved }: { cuenta: ClaveExterna; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ fecha: hoyISO(), responsable: "", sobre_no: "", observacion: "" });
  const [error, setError] = useState("");
  const { data: historial = [] } = useQuery({
    queryKey: ["admin", "claves-externas", cuenta.id, "cambios"],
    queryFn: () => clavesExternasApi.historial(cuenta.id).then((r) => r.data),
  });

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await clavesExternasApi.registrarCambio(cuenta.id, {
        fecha: f.fecha, responsable: f.responsable, sobre_no: f.sobre_no || null, observacion: f.observacion || null,
      });
      onSaved();
    } catch (err) {
      setError(errorDe(err));
    }
  }

  return (
    <Modal titulo={`Registrar cambio · ${cuenta.aplicacion} / ${cuenta.usuario}`} onClose={onClose}>
      <form onSubmit={guardar} className="space-y-4">
        <AvisoSinClaves />
        <p className="text-sm text-gray-600">
          Primero cambia la clave en el sistema y guarda la nueva en un sobre sellado. Después deja aquí la constancia.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Fecha del cambio *</label>
            <input type="date" required max={hoyISO()} value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} className={campo} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Sobre No. nuevo</label>
            <input value={f.sobre_no} onChange={(e) => setF({ ...f, sobre_no: e.target.value })} placeholder={cuenta.sobre_no ?? ""} className={campo} />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Responsable *</label>
          <input required value={f.responsable} onChange={(e) => setF({ ...f, responsable: e.target.value })} className={campo} />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Observación</label>
          <input value={f.observacion} onChange={(e) => setF({ ...f, observacion: e.target.value })} className={campo} />
        </div>
        {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">Cancelar</button>
          <button type="submit" className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium">Registrar cambio</button>
        </div>
      </form>

      <div className="border-t border-gray-200 pt-4">
        <h3 className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2"><History size={14} /> Historial (F-02-2)</h3>
        {historial.length === 0 ? (
          <p className="text-xs text-gray-500">Sin cambios registrados.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-gray-500"><tr><th className="text-left py-1">Fecha</th><th className="text-left">Responsable</th><th className="text-left">Sobre</th><th className="text-left">Observación</th></tr></thead>
            <tbody className="divide-y divide-gray-100">
              {historial.map((h) => (
                <tr key={h.id}><td className="py-1">{fecha(h.fecha)}</td><td>{h.responsable}</td><td>{h.sobre_no ?? "—"}</td><td>{h.observacion ?? ""}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Modal>
  );
}

export function ClavesExternasTable() {
  const qc = useQueryClient();
  const [editando, setEditando] = useState<ClaveExterna | null | "nueva">(null);
  const [cambio, setCambio] = useState<ClaveExterna | null>(null);

  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: ["admin", "claves-externas"],
    queryFn: () => clavesExternasApi.list().then((r) => r.data),
  });
  const { data: categorias = [] } = useQuery({
    queryKey: ["admin", "claves-externas", "categorias"],
    queryFn: () => clavesExternasApi.categorias().then((r) => r.data),
  });
  const desactivar = useMutation({
    mutationFn: (c: ClaveExterna) => clavesExternasApi.update(c.id, { activo: false }),
    onSuccess: () => refrescar(),
  });

  function refrescar() {
    qc.invalidateQueries({ queryKey: ["admin", "claves-externas"] });
  }
  const nombreCat = (k: string) => categorias.find((c) => c.clave === k)?.nombre ?? k;

  return (
    <div>
      <div className="flex items-center justify-between mb-4 gap-4">
        <p className="text-sm text-gray-500">
          Cuentas de sistemas fuera del ERP (FortiGate, servidores, bases de datos, correo). El ERP solo registra
          cuándo se cambió cada clave y quién la custodia. La clave no pasa por el ERP.
        </p>
        <button onClick={() => setEditando("nueva")}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium flex-shrink-0">
          <Plus size={16} /> Nueva cuenta
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : cuentas.length === 0 ? (
        <div className="text-center py-16 text-gray-500 bg-white rounded-xl border border-gray-200">
          Aún no hay cuentas registradas. Empieza por las del Listado de Claves en Bóveda (F-02-3).
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Aplicación", "Usuario", "Categoría", "Custodios", "Sobre / Cofre", "Último cambio", "Vence", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {cuentas.map((c) => (
                <tr key={c.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{c.aplicacion}<div className="text-xs text-gray-500 font-normal">{c.sistema}</div></td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{c.usuario}</td>
                  <td className="px-4 py-3 text-xs text-gray-600">{nombreCat(c.categoria)}<div className="text-gray-400">cada {c.periodicidad_efectiva} días</div></td>
                  <td className="px-4 py-3 text-xs text-gray-600">{[c.custodio_1, c.custodio_2].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">{c.sobre_no ?? "—"} / {c.cofre_no ?? "—"}</td>
                  <td className="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">{fecha(c.ultimo_cambio)}</td>
                  <td className="px-4 py-3 text-xs text-gray-600 whitespace-nowrap">
                    {fecha(c.vence_en)}
                    {c.dias_restantes !== null && (
                      <div className="text-gray-400">{c.dias_restantes < 0 ? `hace ${-c.dias_restantes} días` : `en ${c.dias_restantes} días`}</div>
                    )}
                  </td>
                  <td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${ESTADO[c.estado].clase}`}>{ESTADO[c.estado].texto}</span></td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <button title="Registrar cambio" onClick={() => setCambio(c)} className="text-gray-400 hover:text-primary"><KeyRound size={15} /></button>
                      <button title="Editar" onClick={() => setEditando(c)} className="text-gray-400 hover:text-primary"><Pencil size={15} /></button>
                      <button title="Ya no existe esta cuenta" onClick={() => { if (confirm(`¿Retirar ${c.aplicacion} / ${c.usuario} del registro?`)) desactivar.mutate(c); }}
                        className="text-gray-400 hover:text-red-600"><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando && (
        <CuentaForm inicial={editando === "nueva" ? null : editando} categorias={categorias}
          onClose={() => setEditando(null)} onSaved={() => { refrescar(); setEditando(null); }} />
      )}
      {cambio && (
        <CambioForm cuenta={cambio} onClose={() => setCambio(null)} onSaved={() => { refrescar(); setCambio(null); }} />
      )}
    </div>
  );
}
