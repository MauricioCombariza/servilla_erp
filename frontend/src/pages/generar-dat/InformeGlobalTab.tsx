import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Download, FileBarChart, FileText, Upload, X } from "lucide-react";
import {
  informeGlobalApi,
  type InformeGlobalResult,
  type ItemInformeGlobal,
  type TipoInformeGlobal,
} from "@/api/generarDat";
import { descargarBase64 } from "./descargas";

const MAX_DAT = 10;
const TIPOS: { value: TipoInformeGlobal; label: string }[] = [
  { value: "centralizado", label: "Centralizado" },
  { value: "entregas", label: "Entregas" },
];

interface Fila {
  id: number;
  file: File;
  orden: string;
  nombre: string;
  tipo: TipoInformeGlobal;
}

/** BCS_CLP_EXT_02_20260804.dat → "CLP" como sugerencia de nombre. */
function nombreSugerido(archivo: string) {
  return archivo.match(/_([A-Za-z]{2,4})_EXT_/)?.[1]?.toUpperCase() ?? "";
}

const fmt = (n: number) => n.toLocaleString("es-CO");

function ResultadoItem({ item }: { item: ItemInformeGlobal }) {
  const total = item.operadores.reduce(
    (acc, o) => ({
      enviada: acc.enviada + o.enviada,
      entrega: acc.entrega + o.entrega,
      devoluciones: acc.devoluciones + o.devoluciones,
      dev_iniciales: acc.dev_iniciales + o.dev_iniciales,
      nrd: acc.nrd + o.nrd,
    }),
    { enviada: 0, entrega: 0, devoluciones: 0, dev_iniciales: 0, nrd: 0 },
  );
  const causales = Object.entries(item.causales);

  return (
    <div className="border border-gray-200 rounded-xl p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <p className="text-sm font-semibold text-gray-900">
          {item.nombre} — orden {item.orden}{" "}
          <span className="font-normal text-gray-500">({item.tipo === "entregas" ? "Entregas" : "Centralizado"})</span>
        </p>
        <p className="text-xs text-gray-500">
          {item.nombre_archivo} · corte {item.corte} · fecha mínima {item.fecha_minima}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-gray-500 text-xs">
              <th className="text-left px-3 py-2 font-medium">Operador</th>
              <th className="text-right px-3 py-2 font-medium">BD enviada</th>
              <th className="text-right px-3 py-2 font-medium">Entrega efectiva</th>
              <th className="text-right px-3 py-2 font-medium">Devoluciones</th>
              <th className="text-right px-3 py-2 font-medium">Dev. iniciales</th>
              <th className="text-right px-3 py-2 font-medium">NRD</th>
            </tr>
          </thead>
          <tbody>
            {item.operadores.map((o) => (
              <tr key={o.operador} className="border-t border-gray-100">
                <td className="px-3 py-1.5 text-gray-900">{o.operador}</td>
                {o.enviada === 0 ? (
                  <td colSpan={5} className="px-3 py-1.5 text-right text-gray-300">—</td>
                ) : (
                  <>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(o.enviada)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(o.entrega)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(o.devoluciones)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(o.dev_iniciales)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">{fmt(o.nrd)}</td>
                  </>
                )}
              </tr>
            ))}
            <tr className="border-t border-gray-200 font-semibold">
              <td className="px-3 py-1.5 text-gray-900">TOTAL</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(total.enviada)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(total.entrega)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(total.devoluciones)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(total.dev_iniciales)}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmt(total.nrd)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {causales.length > 0 && (
        <p className="mt-3 text-xs text-gray-600">
          <span className="font-medium">Causales:</span>{" "}
          {causales.map(([codigo, n]) => `${codigo}: ${fmt(n)}`).join(" · ")}
        </p>
      )}
      {item.advertencias.length > 0 && (
        <div className="mt-3 bg-yellow-50 border border-yellow-200 rounded-lg p-2.5 flex items-start gap-2">
          <AlertTriangle size={14} className="text-yellow-600 flex-shrink-0 mt-0.5" />
          <ul className="text-xs text-yellow-800 space-y-0.5">
            {item.advertencias.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Resultado({ data }: { data: InformeGlobalResult }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <h2 className="text-sm font-semibold text-gray-900">
          {data.items.length} informe(s) generados + consolidado por departamento
        </h2>
        <button
          type="button"
          onClick={() => descargarBase64(data.zip_base64, data.nombre_zip, "application/zip")}
          className="inline-flex items-center gap-1.5 bg-primary hover:bg-primary-hover text-white text-sm font-medium rounded-lg px-4 py-2 transition-colors"
        >
          <Download size={16} />
          Descargar {data.nombre_zip}
        </button>
      </div>
      <div className="space-y-4">
        {data.items.map((it) => (
          <ResultadoItem key={it.nombre_excel} item={it} />
        ))}
      </div>
    </div>
  );
}

export function InformeGlobalTab() {
  const [filas, setFilas] = useState<Fila[]>([]);
  const [errorLocal, setErrorLocal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const siguienteId = useRef(1);

  const mutation = useMutation({
    mutationFn: () => informeGlobalApi.generar(filas.map((f) => ({ ...f, orden: f.orden.trim(), nombre: f.nombre.trim() }))).then((r) => r.data),
  });

  function agregarArchivos(nuevos: FileList | null) {
    if (!nuevos) return;
    const dats = Array.from(nuevos).filter((f) => f.name.toLowerCase().endsWith(".dat"));
    setFilas((prev) =>
      [
        ...prev,
        ...dats.map((file) => ({
          id: siguienteId.current++,
          file,
          orden: "",
          nombre: nombreSugerido(file.name),
          tipo: "centralizado" as TipoInformeGlobal,
        })),
      ].slice(0, MAX_DAT),
    );
    setErrorLocal(dats.length < nuevos.length ? "Solo se aceptan archivos .dat" : "");
    mutation.reset();
    if (inputRef.current) inputRef.current.value = "";
  }

  function actualizar(id: number, cambios: Partial<Fila>) {
    setFilas((prev) => prev.map((f) => (f.id === id ? { ...f, ...cambios } : f)));
    mutation.reset();
  }

  function handleGenerar() {
    setErrorLocal("");
    if (filas.length === 0) return setErrorLocal("Agrega al menos un archivo .dat");
    const sinOrden = filas.find((f) => !/^\d+$/.test(f.orden.trim()));
    if (sinOrden) return setErrorLocal(`${sinOrden.file.name}: ingresa un número de orden válido`);
    const sinNombre = filas.find((f) => !f.nombre.trim());
    if (sinNombre) return setErrorLocal(`${sinNombre.file.name}: ingresa el nombre del informe`);
    mutation.mutate();
  }

  const errorApi = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "Error al generar los informes")
    : "";

  const inputCls =
    "mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none";

  return (
    <>
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Informe global</h2>
        <p className="text-xs text-gray-500 mb-4">
          Sube los .dat ya generados (hasta {MAX_DAT}). Cada uno produce la plantilla de BCS (control de recepción y
          causales de devolución) y al final se arma un consolidado por departamento.
        </p>

        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            agregarArchivos(e.dataTransfer.files);
          }}
          className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".dat"
            multiple
            className="hidden"
            onChange={(e) => agregarArchivos(e.target.files)}
          />
          <div className="flex flex-col items-center gap-1.5">
            <Upload size={24} className="text-gray-400" />
            <p className="text-sm text-gray-700">Arrastra los .dat aquí o haz clic para agregar</p>
            <p className="text-xs text-gray-400">Puedes ir agregando uno a uno; cada archivo lleva su orden, nombre y tipo</p>
          </div>
        </div>

        {filas.length > 0 && (
          <ul className="mt-4 space-y-3">
            {filas.map((f) => (
              <li key={f.id} className="border border-gray-200 rounded-xl p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="flex items-center gap-2 text-sm font-medium text-gray-800 break-all">
                    <FileText size={16} className="text-primary flex-shrink-0" />
                    {f.file.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setFilas((prev) => prev.filter((x) => x.id !== f.id));
                      mutation.reset();
                    }}
                    className="text-gray-400 hover:text-red-500"
                    aria-label={`Quitar ${f.file.name}`}
                  >
                    <X size={16} />
                  </button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <label className="block">
                    <span className="text-xs font-medium text-gray-700">Número de orden</span>
                    <input
                      value={f.orden}
                      onChange={(e) => actualizar(f.id, { orden: e.target.value })}
                      inputMode="numeric"
                      placeholder="Ej: 123797"
                      className={inputCls}
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs font-medium text-gray-700">Nombre del informe</span>
                    <input
                      value={f.nombre}
                      onChange={(e) => actualizar(f.id, { nombre: e.target.value })}
                      maxLength={40}
                      placeholder="Ej: CLP_01"
                      className={inputCls}
                    />
                  </label>
                  <div>
                    <span className="text-xs font-medium text-gray-700">Tipo</span>
                    <div className="mt-1 grid grid-cols-2 gap-2">
                      {TIPOS.map((t) => (
                        <button
                          key={t.value}
                          type="button"
                          onClick={() => actualizar(f.id, { tipo: t.value })}
                          aria-pressed={f.tipo === t.value}
                          className={`border rounded-lg px-2 py-2 text-sm transition-colors ${
                            f.tipo === t.value
                              ? "border-primary bg-blue-50 ring-2 ring-primary font-medium text-gray-900"
                              : "border-gray-300 text-gray-600 hover:border-primary"
                          }`}
                        >
                          {t.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}

        <button
          type="button"
          onClick={handleGenerar}
          disabled={mutation.isPending}
          className="mt-4 w-full bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {mutation.isPending ? (
            <>
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              Generando...
            </>
          ) : (
            <>
              <FileBarChart size={16} />
              Generar informes
            </>
          )}
        </button>

        {(errorLocal || errorApi) && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{errorLocal || errorApi}</p>
          </div>
        )}
      </div>

      {mutation.data && <Resultado data={mutation.data} />}
    </>
  );
}
