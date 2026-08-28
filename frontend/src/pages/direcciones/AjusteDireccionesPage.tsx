import { useRef, useState } from "react";
import { Upload, Download, FileText, AlertCircle } from "lucide-react";
import { direccionesApi, type ClienteDirecciones } from "@/api/direcciones";

const MAX_MB = 20;
const MAX_BYTES = MAX_MB * 1024 * 1024;

const CLIENTES: { value: ClienteDirecciones; label: string }[] = [
  { value: "leonisa", label: "Leonisa" },
  { value: "vehigrupo", label: "Banco Vehigrupo" },
];

function formatSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${(bytes / 1024).toFixed(1)} KB`;
}

export function AjusteDireccionesPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [cliente, setCliente] = useState<ClienteDirecciones>("leonisa");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState("");

  const [colDireccion, setColDireccion] = useState<number | null>(null);
  const [direccionesOriginales, setDireccionesOriginales] = useState<string[]>([]);
  const [rows, setRows] = useState<string[][]>([]);

  function handleCambiarCliente(c: ClienteDirecciones) {
    setCliente(c);
    setFile(null);
    setRows([]);
    setDireccionesOriginales([]);
    setColDireccion(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleAjustar() {
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(`El archivo pesa ${formatSize(file.size)} y el máximo son ${MAX_MB} MB.`);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const r = await direccionesApi.ajustar(file, cliente);
      setColDireccion(r.data.col_direccion);
      setDireccionesOriginales(r.data.direcciones_originales);
      setRows(r.data.filas.map((f) => [...f]));
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al procesar el archivo");
      setRows([]);
      setDireccionesOriginales([]);
      setColDireccion(null);
    } finally {
      setLoading(false);
    }
  }

  function handleEditarDireccion(i: number, valor: string) {
    setRows((prev) => {
      const next = prev.map((r) => [...r]);
      if (colDireccion !== null) next[i][colDireccion] = valor;
      return next;
    });
  }

  async function handleDescargar() {
    const nombreBase = file ? file.name.replace(/\.txt$/i, "") : "direcciones";
    setDescargando(true);
    setError("");
    try {
      const r = await direccionesApi.descargar(nombreBase, rows, cliente);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${nombreBase}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al generar el archivo");
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">
        📍 Ajuste Direcciones {cliente === "leonisa" ? "Leonisa" : "Banco Vehigrupo"}
      </h1>

      {/* Selector de cliente */}
      <div className="flex gap-2 mb-4">
        {CLIENTES.map((c) => (
          <button
            key={c.value}
            onClick={() => handleCambiarCliente(c.value)}
            className={`text-sm font-medium py-1.5 px-3 rounded-lg border transition-colors ${
              cliente === c.value
                ? "bg-primary text-white border-primary"
                : "bg-white text-gray-600 border-gray-300 hover:border-primary"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {cliente === "leonisa" ? (
        <p className="text-sm text-gray-500 mb-6">
          Carga el archivo <code className="bg-gray-100 px-1 rounded text-xs">.txt</code> separado por{" "}
          <code className="bg-gray-100 px-1 rounded text-xs">|</code> (sin encabezados). La herramienta
          normaliza la <span className="font-medium">columna 6</span> al formato estándar Leonisa y genera
          el archivo de salida con el mismo nombre del archivo cargado.
        </p>
      ) : (
        <p className="text-sm text-gray-500 mb-6">
          Carga el archivo <code className="bg-gray-100 px-1 rounded text-xs">.txt</code> de{" "}
          <span className="font-medium">ancho fijo</span> del Banco Vehigrupo (288 caracteres por línea,
          sin encabezados). La herramienta normaliza la dirección (columnas 106-170) y genera el archivo
          de salida preservando el mismo formato de ancho fijo.
        </p>
      )}

      {/* Archivo */}
      <div className="mb-4">
        <label className="block text-xs font-medium text-gray-600 mb-1">Archivo de texto (.txt)</label>
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg px-4 py-2.5 cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors flex items-center gap-2"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".txt"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { setFile(f); setRows([]); setDireccionesOriginales([]); setColDireccion(null); setError(""); }
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
          onClick={handleAjustar}
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
              Ajustar direcciones
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

      {rows.length > 0 && colDireccion !== null && (
        <>
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold text-gray-900">Resultado — {rows.length.toLocaleString()} filas</h2>
            <button
              onClick={handleDescargar}
              disabled={descargando}
              className="bg-primary hover:bg-primary-hover text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              <Download size={16} />
              {descargando ? "Generando..." : "Descargar .txt"}
            </button>
          </div>

          <div className="border border-gray-200 rounded-xl overflow-y-auto overflow-x-hidden max-h-[600px]">
            <table className="w-full table-fixed text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-500 text-xs sticky top-0">
                  <th className="text-left px-2 py-2 font-medium w-1/2">Dirección original</th>
                  <th className="text-left px-2 py-2 font-medium w-1/2">Dirección corregida</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="border-b border-gray-100 last:border-0">
                    <td className="px-2 py-1.5 text-gray-600 break-words">
                      {direccionesOriginales[i]?.trim()}
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="text"
                        value={row[colDireccion]}
                        onChange={(e) => handleEditarDireccion(i, e.target.value)}
                        className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
