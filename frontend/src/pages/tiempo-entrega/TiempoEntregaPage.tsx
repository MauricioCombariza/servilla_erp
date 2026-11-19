import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Download } from "lucide-react";
import { tiempoEntregaApi, type GuiaTiempoEntrega } from "@/api/tiempoEntrega";

type FiltroCumple = "todas" | "cumple" | "no_cumple" | "sin_tracking";

function hoyBogota(): string {
  // en-CA da AAAA-MM-DD
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/Bogota" });
}

function haceDias(dias: number): string {
  const d = new Date(`${hoyBogota()}T12:00:00`);
  d.setDate(d.getDate() - dias);
  return d.toLocaleDateString("en-CA");
}

function formatoFechaHora(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CO", {
    timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function horas(v: number | null) {
  return v === null ? "—" : v.toLocaleString("es-CO", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function Tarjeta({ titulo, valor, detalle, tono = "" }: {
  titulo: string; valor: string; detalle?: string; tono?: string;
}) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <p className="text-xs text-gray-500">{titulo}</p>
      <p className={`text-2xl font-semibold ${tono}`}>{valor}</p>
      {detalle && <p className="text-xs text-gray-400">{detalle}</p>}
    </div>
  );
}

function EtiquetaCumple({ g }: { g: GuiaTiempoEntrega }) {
  if (g.cumple === null) return <span className="rounded px-1.5 text-xs bg-gray-100 text-gray-500">Sin tracking</span>;
  return g.cumple
    ? <span className="rounded px-1.5 text-xs bg-green-100 text-green-800">Sí</span>
    : <span className="rounded px-1.5 text-xs bg-red-100 text-red-800">No</span>;
}

export function TiempoEntregaPage() {
  const [desde, setDesde] = useState(haceDias(7));
  const [hasta, setHasta] = useState(hoyBogota());
  const [filtro, setFiltro] = useState<FiltroCumple>("todas");
  const [busqueda, setBusqueda] = useState("");
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState("");

  const rangoValido = Boolean(desde && hasta && desde <= hasta);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["tiempo-entrega", desde, hasta],
    queryFn: () => tiempoEntregaApi.listar(desde, hasta).then((r) => r.data),
    enabled: rangoValido,
  });

  const filtradas = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return (data?.guias ?? []).filter((g) =>
      (filtro === "todas" ||
        (filtro === "cumple" && g.cumple === true) ||
        (filtro === "no_cumple" && g.cumple === false) ||
        (filtro === "sin_tracking" && g.cumple === null)) &&
      (!q || g.serial.toUpperCase().includes(q) || (g.mensajero ?? "").toUpperCase().includes(q)),
    );
  }, [data, filtro, busqueda]);

  async function descargar() {
    setDescargando(true);
    setError("");
    try {
      const r = await tiempoEntregaApi.descargarExcel(desde, hasta);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tiempo_entrega_${desde}_${hasta}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Error al generar el archivo");
    } finally {
      setDescargando(false);
    }
  }

  const r = data?.resumen;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Tiempo de entrega iMile</h1>
          <p className="text-sm text-gray-500">
            Guías entregadas en el rango (por fecha de entrega). Tiempo real = horas seguidas desde la llegada
            a la estación hasta la entrega. Cumple si el tiempo real menos {data?.descuento_horas ?? 24} h por
            cada devolución es de {data?.ans_horas ?? 48} h o menos.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm text-gray-600">Desde</label>
          <input type="date" value={desde} max={hasta} onChange={(e) => setDesde(e.target.value)}
                 className="border rounded px-2 py-1.5 text-sm" />
          <label className="text-sm text-gray-600">Hasta</label>
          <input type="date" value={hasta} min={desde} onChange={(e) => setHasta(e.target.value)}
                 className="border rounded px-2 py-1.5 text-sm" />
          <button
            onClick={descargar}
            disabled={descargando || !data || data.resumen.total === 0}
            className="flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            <Download size={16} /> {descargando ? "Generando…" : "Excel"}
          </button>
        </div>
      </div>

      {!rangoValido && <p className="text-sm text-red-700">La fecha final no puede ser anterior a la inicial.</p>}
      {error && (
        <div className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle size={16} /> {error}
        </div>
      )}
      {isLoading && <p className="text-sm text-gray-500">Cargando…</p>}
      {isError && (
        <div className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle size={16} /> No se pudo cargar el informe.
        </div>
      )}

      {data && r && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Tarjeta
              titulo={`Cumplen el ANS (${data.ans_horas} h)`}
              valor={r.porcentaje_cumple === null ? "—" : `${r.porcentaje_cumple.toLocaleString("es-CO")} %`}
              detalle={`${r.cumplen} de ${r.con_tracking} medidas`}
              tono={r.porcentaje_cumple !== null && r.porcentaje_cumple < 95 ? "text-red-700" : "text-green-700"}
            />
            <Tarjeta titulo="Tiempo real promedio" valor={`${horas(r.promedio_horas_reales)} h`}
                     detalle={`Ajustado: ${horas(r.promedio_horas_ajustadas)} h`} />
            <Tarjeta titulo="Guías entregadas" valor={r.total.toLocaleString("es-CO")}
                     detalle={r.sin_tracking ? `${r.sin_tracking} sin tracking todavía` : "Todas con tracking"} />
            <Tarjeta titulo="Con devoluciones" valor={r.con_devoluciones.toLocaleString("es-CO")}
                     tono="text-amber-700" />
          </div>

          <div className="rounded-lg border bg-white overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b bg-gray-50">
              <h2 className="text-sm font-semibold mr-2">Guías ({filtradas.length})</h2>
              <select value={filtro} onChange={(e) => setFiltro(e.target.value as FiltroCumple)}
                      className="border rounded px-2 py-1 text-sm">
                <option value="todas">Todas</option>
                <option value="cumple">Cumplen</option>
                <option value="no_cumple">No cumplen</option>
                <option value="sin_tracking">Sin tracking</option>
              </select>
              <input value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
                     placeholder="Buscar guía o mensajero"
                     className="ml-auto border rounded px-2 py-1 text-sm w-56" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-500">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">Guía</th>
                    <th className="text-left px-3 py-2 font-medium">Mensajero</th>
                    <th className="text-right px-3 py-2 font-medium">Devoluciones</th>
                    <th className="text-left px-3 py-2 font-medium">Fecha inicial</th>
                    <th className="text-left px-3 py-2 font-medium">Fecha de entrega</th>
                    <th className="text-right px-3 py-2 font-medium">Tiempo real (h)</th>
                    <th className="text-right px-3 py-2 font-medium">Ajustado (h)</th>
                    <th className="text-left px-3 py-2 font-medium">Cumple</th>
                  </tr>
                </thead>
                <tbody>
                  {filtradas.map((g) => (
                    <tr key={g.serial} className="border-t">
                      <td className="px-3 py-1.5 font-mono">{g.serial}</td>
                      <td className="px-3 py-1.5">
                        {g.mensajero ?? "—"} {g.cod_men && <span className="text-xs text-gray-400">{g.cod_men}</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right">{g.devoluciones ?? "—"}</td>
                      <td className="px-3 py-1.5 whitespace-nowrap">{formatoFechaHora(g.fecha_inicial)}</td>
                      <td className="px-3 py-1.5 whitespace-nowrap">{formatoFechaHora(g.fecha_entrega)}</td>
                      <td className="px-3 py-1.5 text-right">{horas(g.horas_reales)}</td>
                      <td className="px-3 py-1.5 text-right">{horas(g.horas_ajustadas)}</td>
                      <td className="px-3 py-1.5"><EtiquetaCumple g={g} /></td>
                    </tr>
                  ))}
                  {filtradas.length === 0 && (
                    <tr><td colSpan={8} className="px-3 py-6 text-center text-gray-400">
                      No hay guías entregadas en este rango.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
