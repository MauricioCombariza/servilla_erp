import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Download, X } from "lucide-react";
import {
  paquetesEstancadosApi,
  type GrupoEstancados,
  type PaqueteEstancado,
} from "@/api/paquetesEstancados";

const OPCIONES_DIAS = [1, 2, 3, 5, 7];

function colorDias(dias: number) {
  if (dias >= 4) return "bg-red-100 text-red-800";
  if (dias === 3) return "bg-amber-100 text-amber-800";
  return "bg-gray-100 text-gray-700";
}

function formatoFechaHora(iso: string) {
  return new Date(iso).toLocaleString("es-CO", {
    timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function Tarjeta({ titulo, valor, tono = "" }: { titulo: string; valor: number; tono?: string }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <p className="text-xs text-gray-500">{titulo}</p>
      <p className={`text-2xl font-semibold ${tono}`}>{valor.toLocaleString("es-CO")}</p>
    </div>
  );
}

function TablaGrupo({
  titulo, grupos, seleccionado, onSeleccionar, mostrarClave,
}: {
  titulo: string;
  grupos: GrupoEstancados[];
  seleccionado: string | null;
  onSeleccionar: (clave: string | null) => void;
  mostrarClave: boolean;
}) {
  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <h2 className="px-4 py-2 text-sm font-semibold border-b bg-gray-50">{titulo}</h2>
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-gray-500 sticky top-0 bg-white">
            <tr>
              <th className="text-left px-4 py-1.5 font-medium">{mostrarClave ? "Mensajero" : "Zona"}</th>
              <th className="text-right px-4 py-1.5 font-medium">Paquetes</th>
              <th className="text-right px-4 py-1.5 font-medium">Máx. días</th>
            </tr>
          </thead>
          <tbody>
            {grupos.map((g) => {
              const activo = seleccionado === g.clave;
              return (
                <tr
                  key={g.clave || "_vacio"}
                  onClick={() => onSeleccionar(activo ? null : g.clave)}
                  className={`cursor-pointer border-t ${activo ? "bg-primary/10" : "hover:bg-gray-50"}`}
                >
                  <td className="px-4 py-1.5">
                    {g.nombre}
                    {mostrarClave && g.clave && <span className="ml-1 text-xs text-gray-400">{g.clave}</span>}
                  </td>
                  <td className="px-4 py-1.5 text-right font-medium">{g.paquetes}</td>
                  <td className="px-4 py-1.5 text-right">
                    <span className={`inline-block rounded px-1.5 text-xs ${colorDias(g.max_dias)}`}>{g.max_dias}</span>
                  </td>
                </tr>
              );
            })}
            {grupos.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-3 text-center text-gray-400">Sin datos</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function PaquetesEstancadosPage() {
  const [diasMin, setDiasMin] = useState(2);
  const [incluirDevoluciones, setIncluirDevoluciones] = useState(false);
  const [incluirDescartados, setIncluirDescartados] = useState(false);
  const [codigo, setCodigo] = useState<string | null>(null);
  const [zona, setZona] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["paquetes-estancados", diasMin, incluirDevoluciones, incluirDescartados],
    queryFn: () =>
      paquetesEstancadosApi.listar(diasMin, incluirDevoluciones, incluirDescartados).then((r) => r.data),
  });

  const filtrados: PaqueteEstancado[] = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return (data?.paquetes ?? []).filter((p) =>
      (codigo === null || (p.codigo ?? "") === codigo) &&
      (zona === null || (p.zona ?? "") === zona) &&
      (!q || p.serial.toUpperCase().includes(q)),
    );
  }, [data, codigo, zona, busqueda]);

  const paquetes = data?.paquetes ?? [];
  const masDe5 = paquetes.filter((p) => p.dias > 5).length;
  const sinAsignar = paquetes.filter((p) => !p.codigo).length;

  async function descargar() {
    setDescargando(true);
    setError("");
    try {
      const r = await paquetesEstancadosApi.descargarExcel(diasMin, {
        incluir_devoluciones: incluirDevoluciones,
        incluir_descartados: incluirDescartados,
        ...(codigo !== null ? { codigo } : {}),
        ...(zona !== null ? { zona } : {}),
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `paquetes_estancados_${data?.corte ?? ""}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Error al generar el archivo");
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Paquetes estancados</h1>
          <p className="text-sm text-gray-500">
            Paquetes leídos al ingresar en tulas que todavía no aparecen en la descarga de envíos
            (seriales_gestion). Los días se cuentan desde el primer ingreso.
            {data && <> Corte: {data.corte}.</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm text-gray-600 mr-2">
            <input
              type="checkbox"
              checked={incluirDevoluciones}
              onChange={(e) => setIncluirDevoluciones(e.target.checked)}
            />
            Incluir devoluciones
          </label>
          <label className="flex items-center gap-1.5 text-sm text-gray-600 mr-2">
            <input
              type="checkbox"
              checked={incluirDescartados}
              onChange={(e) => setIncluirDescartados(e.target.checked)}
            />
            Incluir lecturas descartadas
          </label>
          <label className="text-sm text-gray-600">Más de</label>
          <select
            value={diasMin}
            onChange={(e) => setDiasMin(Number(e.target.value))}
            className="border rounded px-2 py-1.5 text-sm"
          >
            {OPCIONES_DIAS.map((d) => <option key={d} value={d}>{d} {d === 1 ? "día" : "días"}</option>)}
          </select>
          <button
            onClick={descargar}
            disabled={descargando || !data || data.total === 0}
            className="flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            <Download size={16} /> {descargando ? "Generando…" : "Excel"}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {isLoading && <p className="text-sm text-gray-500">Cargando…</p>}
      {isError && (
        <div className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle size={16} /> No se pudo cargar el reporte.
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Tarjeta titulo={`Con más de ${data.dias_min} días`} valor={data.total} />
            <Tarjeta titulo="Con más de 5 días" valor={masDe5} tono="text-red-700" />
            <Tarjeta titulo="Sin mensajero asignado" valor={sinAsignar} tono="text-amber-700" />
          </div>

          {data.devoluciones_ocultas > 0 && (
            <p className="text-sm text-gray-500">
              No se listan {data.devoluciones_ocultas} paquetes que están en devolución
              (van de vuelta al cliente). Marca "Incluir devoluciones" para verlos.
            </p>
          )}
          {data.descartados_ocultos > 0 && (
            <p className="text-sm text-gray-500">
              No se listan {data.descartados_ocultos} lecturas que no son paquetes (códigos de tula,
              seriales cortados o leídos dos veces, o rechazados por iMile y fuera de la base).
              Marca "Incluir lecturas descartadas" para revisarlas.
            </p>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <TablaGrupo titulo="Por mensajero" grupos={data.por_mensajero} seleccionado={codigo}
                        onSeleccionar={setCodigo} mostrarClave />
            <TablaGrupo titulo="Por zona" grupos={data.por_zona} seleccionado={zona}
                        onSeleccionar={setZona} mostrarClave={false} />
          </div>

          <div className="rounded-lg border bg-white overflow-hidden">
            <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b bg-gray-50">
              <h2 className="text-sm font-semibold mr-2">Detalle ({filtrados.length})</h2>
              {codigo !== null && (
                <button onClick={() => setCodigo(null)}
                        className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs">
                  Mensajero: {codigo || "sin asignar"} <X size={12} />
                </button>
              )}
              {zona !== null && (
                <button onClick={() => setZona(null)}
                        className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs">
                  Zona: {zona || "sin zona"} <X size={12} />
                </button>
              )}
              <input
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                placeholder="Buscar serial"
                className="ml-auto border rounded px-2 py-1 text-sm w-48"
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-gray-500">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium">Serial</th>
                    <th className="text-right px-3 py-2 font-medium">Días</th>
                    <th className="text-left px-3 py-2 font-medium">Primer ingreso</th>
                    <th className="text-left px-3 py-2 font-medium">Zona</th>
                    <th className="text-left px-3 py-2 font-medium">Localidad</th>
                    <th className="text-left px-3 py-2 font-medium">Dirección</th>
                    <th className="text-left px-3 py-2 font-medium">Mensajero</th>
                    <th className="text-left px-3 py-2 font-medium">Asignado el</th>
                    <th className="text-left px-3 py-2 font-medium">iMile</th>
                    {incluirDevoluciones && <th className="text-left px-3 py-2 font-medium">Devolución</th>}
                    {incluirDescartados && <th className="text-left px-3 py-2 font-medium">Descarte</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtrados.map((p) => (
                    <tr key={p.serial} className={`border-t ${p.motivo_descarte ? "bg-gray-50 text-gray-400" : ""}`}>
                      <td className="px-3 py-1.5 font-mono">{p.serial}</td>
                      <td className="px-3 py-1.5 text-right">
                        <span className={`inline-block rounded px-1.5 font-medium ${colorDias(p.dias)}`}>{p.dias}</span>
                      </td>
                      <td className="px-3 py-1.5 whitespace-nowrap">{formatoFechaHora(p.primer_ingreso)}</td>
                      <td className="px-3 py-1.5">{p.zona ?? "—"}</td>
                      <td className="px-3 py-1.5">{p.localidad ?? "—"}</td>
                      <td className="px-3 py-1.5 max-w-xs truncate" title={p.direccion ?? ""}>{p.direccion ?? "—"}</td>
                      <td className="px-3 py-1.5">
                        {p.mensajero
                          ? <>{p.mensajero} <span className="text-xs text-gray-400">{p.codigo}</span></>
                          : <span className="text-amber-700">Sin asignar</span>}
                      </td>
                      <td className="px-3 py-1.5 whitespace-nowrap">
                        {p.fecha_asignacion ?? "—"}
                        {p.origen_asignacion === "serial" && <span className="ml-1 text-xs text-gray-400">(serial)</span>}
                      </td>
                      <td className="px-3 py-1.5">{p.imile_estado ?? "—"}</td>
                      {incluirDevoluciones && <td className="px-3 py-1.5">{p.devolucion ?? "—"}</td>}
                      {incluirDescartados && <td className="px-3 py-1.5">{p.motivo_descarte ?? "—"}</td>}
                    </tr>
                  ))}
                  {filtrados.length === 0 && (
                    <tr><td colSpan={9 + (incluirDevoluciones ? 1 : 0) + (incluirDescartados ? 1 : 0)} className="px-3 py-6 text-center text-gray-400">
                      No hay paquetes con más de {data.dias_min} días sin entregar.
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
