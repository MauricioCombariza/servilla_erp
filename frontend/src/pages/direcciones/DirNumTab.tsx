import { useRef, useState } from "react";
import { Upload, Download, FileText, AlertCircle } from "lucide-react";
import { direccionesApi, type FilaDirNum } from "@/api/direcciones";

const MAX_MB = 20;
const MAX_BYTES = MAX_MB * 1024 * 1024;

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${(bytes / 1024).toFixed(1)} KB`;
}

export function DirNumTab() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState("");

  const [filas, setFilas] = useState<FilaDirNum[]>([]);
  const [ajustadasOriginales, setAjustadasOriginales] = useState<string[]>([]);

  function limpiarResultado() {
    setFilas([]);
    setAjustadasOriginales([]);
  }

  async function handleProcesar() {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(`El archivo pesa ${formatSize(file.size)} y el máximo son ${MAX_MB} MB.`);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const r = await direccionesApi.dirnum(file);
      setFilas(r.data.filas);
      setAjustadasOriginales(r.data.filas.map((f) => f.direccion_ajustada));
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al procesar el archivo");
      limpiarResultado();
    } finally {
      setLoading(false);
    }
  }

  function handleEditar(i: number, valor: string) {
    setFilas((prev) => prev.map((f, j) => (j === i ? { ...f, direccion_ajustada: valor } : f)));
  }

  async function handleDescargar() {
    const nombreBase = file ? file.name.replace(/\.xlsx$/i, "") : "direcciones";
    setDescargando(true);
    setError("");
    try {
      const r = await direccionesApi.descargarDirnum(nombreBase, filas);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${nombreBase}_dirnum.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al generar el archivo");
    } finally {
      setDescargando(false);
    }
  }

  const sinDirNum = filas.filter((f) => !f.dir_num).length;

  return (
    <div>
      <p className="text-sm text-gray-500 mb-6">
        Carga un Excel (<code className="bg-gray-100 px-1 rounded text-xs">.xlsx</code>) con las columnas{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">serial</code> y{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">direccion</code>. La herramienta agrega la{" "}
        <span className="font-medium">dirección ajustada</span> (formato CL/CR/DG/TR sin complementos) y la{" "}
        <span className="font-medium">dir_num</span> de 18 dígitos.
      </p>

      {/* Archivo */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-600 mb-1">Archivo Excel (.xlsx)</label>
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg px-4 py-2.5 cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors flex items-center gap-2"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { setFile(f); limpiarResultado(); setError(""); }
            }}
          />
          {file ? (
            <>
              <FileText size={16} className="text-primary flex-shrink-0" />
              <span className="text-sm text-gray-900 truncate">{file.name}</span>
              <span className="text-xs text-gray-500 flex-shrink-0">({formatSize(file.size)})</span>
            </>
          ) : (
            <>
              <Upload size={16} className="text-gray-400 flex-shrink-0" />
              <span className="text-sm text-gray-500">Arrastra el archivo aquí o haz clic para seleccionar</span>
            </>
          )}
        </div>
      </div>

      {file && (
        <button
          onClick={handleProcesar}
          disabled={loading}
          className="mb-4 bg-primary hover:bg-primary-hover text-white font-medium py-2.5 px-4 rounded-lg text-sm transition-colors disabled:opacity-60 flex items-center gap-2"
        >
          {loading ? (
            <>
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              Procesando...
            </>
          ) : (
            <>
              <Upload size={16} />
              Ajustar y generar dir_num
            </>
          )}
        </button>
      )}

      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {filas.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="font-semibold text-gray-900">Resultado — {filas.length.toLocaleString()} filas</h2>
              {sinDirNum > 0 && (
                <p className="text-xs text-amber-700">
                  {sinDirNum.toLocaleString()} sin dir_num (resaltadas): corrige la dirección ajustada y se
                  recalcula al descargar.
                </p>
              )}
            </div>
            <button
              onClick={handleDescargar}
              disabled={descargando}
              className="bg-primary hover:bg-primary-hover text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <Download size={16} />
              {descargando ? "Generando..." : "Descargar Excel"}
            </button>
          </div>

          <div className="border border-gray-200 rounded-xl overflow-y-auto overflow-x-hidden max-h-[600px]">
            <table className="w-full table-fixed text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-500 text-xs sticky top-0">
                  <th className="text-left px-2 py-2 font-medium w-[15%]">Serial</th>
                  <th className="text-left px-2 py-2 font-medium w-[35%]">Dirección original</th>
                  <th className="text-left px-2 py-2 font-medium w-[28%]">Dirección ajustada</th>
                  <th className="text-left px-2 py-2 font-medium w-[22%]">dir_num</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f, i) => {
                  const editada = f.direccion_ajustada !== ajustadasOriginales[i];
                  return (
                    <tr
                      key={i}
                      className={`border-b border-gray-100 last:border-0 ${f.dir_num ? "" : "bg-amber-50"}`}
                    >
                      <td className="px-2 py-1.5 text-gray-900 break-words">{f.serial}</td>
                      <td className="px-2 py-1.5 text-gray-600 break-words">{f.direccion}</td>
                      <td className="px-2 py-1">
                        <input
                          type="text"
                          value={f.direccion_ajustada}
                          onChange={(e) => handleEditar(i, e.target.value)}
                          className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                        />
                      </td>
                      <td
                        className={`px-2 py-1.5 font-mono text-xs break-all ${editada ? "text-gray-400 italic" : "text-gray-900"}`}
                        title={editada ? "Dirección editada: la dir_num se recalcula al descargar" : undefined}
                      >
                        {editada ? "se recalcula al descargar" : f.dir_num || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
