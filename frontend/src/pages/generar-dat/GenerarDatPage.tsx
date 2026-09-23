import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Download, FileCog, FileText, Upload, X } from "lucide-react";
import { generarDatApi, type GenerarDatResult, type TipoInforme } from "@/api/generarDat";

const MAX_ARCHIVOS = 5;
const TIPOS: { value: TipoInforme; label: string; descripcion: string }[] = [
  { value: "centralizado", label: "Centralizado", descripcion: "Registro completo (375 caracteres)" },
  { value: "terceros", label: "Terceros", descripcion: "Solo de fecha inicial a F_GESTION" },
];
const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function descargarBase64(base64: string, nombre: string, mime: string) {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

function Resumen({ data }: { data: GenerarDatResult }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-900 mb-4">
        Orden {data.orden} — fecha inicial {data.fecha_ini} — {data.tipo === "terceros" ? "Terceros" : "Centralizado"}
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
        <Stat label="Registros en el .dat" value={data.registros} />
        <Stat label="Seriales en Excel" value={data.seriales_excel} />
        <Stat label="Seriales de la orden" value={data.seriales_orden} />
        <Stat label="Orden sin gestión" value={data.errores.length} alerta={data.errores.length > 0} />
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => descargarBase64(data.dat_base64, data.nombre_dat, "text/plain")}
          className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
        >
          <Download size={16} />
          Descargar {data.nombre_dat}
        </button>
        {data.errores_base64 && data.nombre_errores && (
          <button
            type="button"
            onClick={() => descargarBase64(data.errores_base64!, data.nombre_errores!, XLSX_MIME)}
            className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Download size={16} />
            Descargar errores ({data.errores.length})
          </button>
        )}
      </div>

      {data.no_encontrados_en_orden.length > 0 && (
        <Aviso
          titulo={`${data.no_encontrados_en_orden.length} serial(es) de los Excel no pertenecen a la orden y no se incluyeron`}
          seriales={data.no_encontrados_en_orden}
        />
      )}
      {data.duplicados_en_excel.length > 0 && (
        <Aviso
          titulo={`${data.duplicados_en_excel.length} serial(es) repetidos entre los Excel (se tomó el último)`}
          seriales={data.duplicados_en_excel}
        />
      )}

      {data.errores.length > 0 && (
        <div className="mt-5 border border-gray-200 rounded-xl overflow-auto max-h-80">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0">
              <tr className="bg-gray-50 text-gray-500 text-xs">
                <th className="text-left px-3 py-2 font-medium">Serial sin gestión</th>
                <th className="text-left px-3 py-2 font-medium">Courier</th>
              </tr>
            </thead>
            <tbody>
              {data.errores.map((e) => (
                <tr key={e.serial} className="border-t border-gray-100">
                  <td className="px-3 py-1.5 font-mono text-xs text-gray-900">{e.serial}</td>
                  <td className="px-3 py-1.5 text-gray-600">{e.courrier || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, alerta = false }: { label: string; value: number; alerta?: boolean }) {
  return (
    <div className="rounded-lg bg-gray-50 px-4 py-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-xl font-semibold ${alerta ? "text-orange-600" : "text-gray-900"}`}>
        {value.toLocaleString("es-CO")}
      </p>
    </div>
  );
}

function Aviso({ titulo, seriales }: { titulo: string; seriales: string[] }) {
  return (
    <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-xl p-3 flex items-start gap-2">
      <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
      <div className="text-sm text-yellow-800">
        <p className="font-medium">{titulo}</p>
        <p className="font-mono text-xs mt-1 break-all">
          {seriales.slice(0, 30).join(", ")}
          {seriales.length > 30 && ` … y ${seriales.length - 30} más`}
        </p>
      </div>
    </div>
  );
}

export function GenerarDatPage() {
  const [orden, setOrden] = useState("");
  const [fechaIni, setFechaIni] = useState("");
  const [tipo, setTipo] = useState<TipoInforme>("centralizado");
  const [files, setFiles] = useState<File[]>([]);
  const [errorLocal, setErrorLocal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () => generarDatApi.generar(orden.trim(), fechaIni, tipo, files).then((r) => r.data),
  });

  function agregarArchivos(nuevos: FileList | null) {
    if (!nuevos) return;
    const xlsx = Array.from(nuevos).filter((f) => f.name.toLowerCase().endsWith(".xlsx"));
    setFiles((prev) => {
      const nombres = new Set(prev.map((f) => f.name));
      return [...prev, ...xlsx.filter((f) => !nombres.has(f.name))].slice(0, MAX_ARCHIVOS);
    });
    setErrorLocal(xlsx.length < nuevos.length ? "Solo se aceptan archivos .xlsx" : "");
    mutation.reset();
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleGenerar() {
    setErrorLocal("");
    if (!/^\d+$/.test(orden.trim())) return setErrorLocal("Ingresa un número de orden válido");
    if (!fechaIni) return setErrorLocal("Selecciona la fecha inicial");
    if (files.length === 0) return setErrorLocal("Sube al menos un archivo Excel");
    mutation.mutate();
  }

  const errorApi = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "Error al generar el archivo")
    : "";

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <FileCog size={24} className="text-primary" />
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Generar DAT BCS</h1>
          <p className="text-sm text-gray-500">
            Cruza los Excel de gestión con la orden en bases_web y genera el archivo .dat de ancho fijo.
          </p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <label className="block">
            <span className="text-xs font-medium text-gray-700">Número de orden</span>
            <input
              value={orden}
              onChange={(e) => setOrden(e.target.value)}
              inputMode="numeric"
              placeholder="Ej: 123791"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
            />
          </label>
          <label className="block">
            <span className="text-xs font-medium text-gray-700">Fecha inicial</span>
            <input
              type="date"
              value={fechaIni}
              onChange={(e) => setFechaIni(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
            />
          </label>
        </div>

        <div className="mb-4">
          <span className="text-xs font-medium text-gray-700">Tipo de informe</span>
          <div className="mt-1 grid grid-cols-2 gap-2">
            {TIPOS.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => {
                  setTipo(t.value);
                  mutation.reset();
                }}
                aria-pressed={tipo === t.value}
                className={`text-left border rounded-lg px-3 py-2 transition-colors ${
                  tipo === t.value
                    ? "border-primary bg-blue-50 ring-2 ring-primary"
                    : "border-gray-300 hover:border-primary"
                }`}
              >
                <p className="text-sm font-medium text-gray-900">{t.label}</p>
                <p className="text-xs text-gray-500">{t.descripcion}</p>
              </button>
            ))}
          </div>
        </div>

        <p className="text-xs text-gray-500 mb-2">
          Excel de gestión (.xlsx, hasta {MAX_ARCHIVOS}) con las columnas{" "}
          <code className="bg-gray-100 px-1 rounded">serial, Estado, Causal_Dev, F_recepcio, guias, F_GESTION</code>
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
            accept=".xlsx"
            multiple
            className="hidden"
            onChange={(e) => agregarArchivos(e.target.files)}
          />
          <div className="flex flex-col items-center gap-1.5">
            <Upload size={24} className="text-gray-400" />
            <p className="text-sm text-gray-700">Arrastra los archivos aquí o haz clic para seleccionar</p>
            <p className="text-xs text-gray-400">Puedes subir 2 o 3 archivos a la vez</p>
          </div>
        </div>

        {files.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {files.map((f) => (
              <li key={f.name} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                <span className="flex items-center gap-2 text-sm text-gray-800">
                  <FileText size={16} className="text-primary" />
                  {f.name}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setFiles((prev) => prev.filter((x) => x.name !== f.name));
                    mutation.reset();
                  }}
                  className="text-gray-400 hover:text-red-500"
                  aria-label={`Quitar ${f.name}`}
                >
                  <X size={16} />
                </button>
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
              <FileCog size={16} />
              Generar .dat
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

      {mutation.data && <Resumen data={mutation.data} />}
    </div>
  );
}
