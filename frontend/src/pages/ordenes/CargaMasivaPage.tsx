import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, ArrowLeft, CheckCircle, AlertCircle, FileText } from "lucide-react";
import { ordenesApi, type CargaMasivaResult } from "@/api/ordenes";

export function CargaMasivaPage() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CargaMasivaResult | null>(null);
  const [error, setError] = useState("");

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setResult(null);
    setError("");
    try {
      const r = await ordenesApi.cargaMasiva(file);
      setResult(r.data);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al procesar el archivo");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <button
        onClick={() => navigate("/ordenes")}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900 mb-6 transition-colors"
      >
        <ArrowLeft size={16} />
        Volver a órdenes
      </button>

      <h1 className="text-xl font-semibold text-gray-900 mb-1">Carga masiva de órdenes</h1>
      <p className="text-sm text-gray-500 mb-2">
        Columnas requeridas:{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">orden, serial, fecha_recepcion, nombre_cliente, tipo_servicio, ambito</code>
      </p>
      <p className="text-sm text-gray-400 mb-6">
        Columnas opcionales:{" "}
        <code className="bg-gray-100 px-1 rounded text-xs">planilla, cod_men</code>
        {" "}· Solo se procesan filas con fecha ≥ 2026-01-01
      </p>

      {/* Zona de drop */}
      <div
        onClick={() => inputRef.current?.click()}
        className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) { setFile(f); setResult(null); setError(""); }
          }}
        />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <FileText size={32} className="text-primary" />
            <p className="font-medium text-gray-900">{file.name}</p>
            <p className="text-sm text-gray-500">{(file.size / 1024).toFixed(1)} KB</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <Upload size={32} className="text-gray-400" />
            <p className="font-medium text-gray-700">Arrastra el CSV aquí o haz clic para seleccionar</p>
            <p className="text-xs text-gray-400">Solo archivos .csv · máx 10 MB</p>
          </div>
        )}
      </div>

      {file && !result && (
        <button
          onClick={handleUpload}
          disabled={loading}
          className="mt-4 w-full bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-xl text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
              Procesando...
            </>
          ) : (
            <>
              <Upload size={16} />
              Procesar e insertar en base de datos
            </>
          )}
        </button>
      )}

      {error && (
        <div className="mt-4 bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {result && (
        <div className="mt-6 space-y-4">
          {/* Resumen */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle size={20} className="text-green-500" />
              <h2 className="font-semibold text-gray-900">Resultado del procesamiento</h2>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {[
                { label: "Filas leídas", value: result.total_filas },
                { label: "Filas ignoradas (antes 2026)", value: result.filas_ignoradas, color: "text-gray-400" },
                { label: "Seriales nuevos", value: result.seriales_nuevos, color: "text-green-700" },
                { label: "Seriales actualizados", value: result.seriales_actualizados, color: "text-teal-700" },
                { label: "Órdenes nuevas", value: result.ordenes_nuevas, color: "text-blue-700" },
                { label: "Órdenes actualizadas", value: result.ordenes_actualizadas, color: "text-orange-600" },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">{label}</p>
                  <p className={`text-2xl font-bold ${color ?? "text-gray-900"}`}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Errores */}
          {result.errores.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <AlertCircle size={16} className="text-yellow-600" />
                <p className="text-sm font-medium text-yellow-800">
                  {result.errores.length} advertencia{result.errores.length !== 1 ? "s" : ""}
                </p>
              </div>
              <ul className="space-y-1 max-h-48 overflow-y-auto">
                {result.errores.map((e, i) => (
                  <li key={i} className="text-xs text-yellow-700 font-mono bg-yellow-100 px-2 py-1 rounded">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={() => { setFile(null); setResult(null); if (inputRef.current) inputRef.current.value = ""; }}
              className="flex-1 border border-gray-300 text-gray-700 py-2 rounded-lg text-sm hover:bg-gray-50"
            >
              Cargar otro archivo
            </button>
            <button
              onClick={() => navigate("/ordenes")}
              className="flex-1 bg-primary hover:bg-primary-hover text-white py-2 rounded-lg text-sm font-medium"
            >
              Ver órdenes
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
