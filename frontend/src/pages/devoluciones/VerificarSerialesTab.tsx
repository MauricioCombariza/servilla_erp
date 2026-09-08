import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, Download, FileText, Search, Upload } from "lucide-react";
import { devolucionesApi, type SerialVerificado } from "@/api/devoluciones";

async function extraerErrorBlob(e: unknown): Promise<string> {
  const data = (e as { response?: { data?: unknown } })?.response?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text());
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      // no era JSON, cae al mensaje genérico
    }
  }
  return "Error al verificar el archivo";
}

const MAX_SERIALES = 500;

const CLASIFICACION_LABEL: Record<SerialVerificado["clasificacion"], string> = {
  entrega: "Entrega",
  devolucion: "Devolución",
  ninguna: "No encontrado",
};

const CLASIFICACION_CLASES: Record<SerialVerificado["clasificacion"], string> = {
  entrega: "bg-green-100 text-green-800",
  devolucion: "bg-orange-100 text-orange-800",
  ninguna: "bg-gray-100 text-gray-600",
};

function ClasificacionBadge({ clasificacion }: { clasificacion: SerialVerificado["clasificacion"] }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${CLASIFICACION_CLASES[clasificacion]}`}
    >
      {CLASIFICACION_LABEL[clasificacion]}
    </span>
  );
}

function parseSeriales(texto: string): string[] {
  const vistos = new Set<string>();
  const seriales: string[] = [];
  for (const raw of texto.split(/[\s,]+/)) {
    const s = raw.trim();
    if (s && !vistos.has(s)) {
      vistos.add(s);
      seriales.push(s);
    }
  }
  return seriales;
}

export function VerificarSerialesTab() {
  const [texto, setTexto] = useState("");
  const [errorLocal, setErrorLocal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [errorExcel, setErrorExcel] = useState("");

  const mutation = useMutation({
    mutationFn: (seriales: string[]) => devolucionesApi.verificarSeriales(seriales).then((r) => r.data),
  });

  const excelMutation = useMutation({
    mutationFn: async (f: File) => {
      const r = await devolucionesApi.verificarSerialesExcel(f);
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `seriales_verificados_${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onSuccess: () => {
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    },
    onError: async (e: unknown) => setErrorExcel(await extraerErrorBlob(e)),
  });

  const seriales = parseSeriales(texto);

  function handleVerificar() {
    setErrorLocal("");
    if (seriales.length === 0) {
      setErrorLocal("Pega al menos un serial");
      return;
    }
    if (seriales.length > MAX_SERIALES) {
      setErrorLocal(`Máximo ${MAX_SERIALES} seriales por verificación (pegaste ${seriales.length})`);
      return;
    }
    mutation.mutate(seriales);
  }

  const resultado = mutation.data;
  const errorApi = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "Error al verificar los seriales")
    : "";

  return (
    <div>
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Verificar seriales</h2>
        <p className="text-xs text-gray-500 mb-3">
          Pega uno o varios seriales (uno por línea, o separados por comas/espacios) para saber si
          son devoluciones, entregas, o no aparecen en ninguna de las dos.
        </p>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={6}
          placeholder={"SERIAL1\nSERIAL2\nSERIAL3"}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none"
        />
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-gray-400">
            {seriales.length} serial{seriales.length === 1 ? "" : "es"} detectado
            {seriales.length === 1 ? "" : "s"}
          </p>
          <button
            type="button"
            onClick={handleVerificar}
            disabled={mutation.isPending}
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-60"
          >
            <Search size={16} />
            {mutation.isPending ? "Verificando..." : "Verificar"}
          </button>
        </div>

        {(errorLocal || errorApi) && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{errorLocal || errorApi}</p>
          </div>
        )}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Verificar por Excel</h2>
        <p className="text-xs text-gray-500 mb-3">
          Sube un Excel (.xlsx) con una columna <code className="bg-gray-100 px-1 rounded">serial</code> y
          descarga el mismo archivo con dos columnas nuevas: clasificación (Entrega / Devolución / No
          encontrado) y la fecha de esa gestión.
        </p>
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors"
        >
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setFile(f);
                setErrorExcel("");
                excelMutation.reset();
              }
            }}
          />
          {file ? (
            <div className="flex flex-col items-center gap-1.5">
              <FileText size={24} className="text-primary" />
              <p className="text-sm font-medium text-gray-900">{file.name}</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1.5">
              <Upload size={24} className="text-gray-400" />
              <p className="text-sm text-gray-700">Arrastra el archivo aquí o haz clic para seleccionar</p>
              <p className="text-xs text-gray-400">Excel (.xlsx)</p>
            </div>
          )}
        </div>

        {file && (
          <button
            type="button"
            onClick={() => excelMutation.mutate(file)}
            disabled={excelMutation.isPending}
            className="mt-3 w-full bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {excelMutation.isPending ? (
              <>
                <span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
                Verificando...
              </>
            ) : (
              <>
                <Download size={16} />
                Verificar y descargar
              </>
            )}
          </button>
        )}

        {errorExcel && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{errorExcel}</p>
          </div>
        )}
      </div>

      {resultado && (
        <>
          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <span className="inline-flex items-center gap-1.5 text-sm text-gray-700">
              <span className="w-2.5 h-2.5 rounded-full bg-orange-400" />
              {resultado.total_devoluciones} devolución{resultado.total_devoluciones === 1 ? "" : "es"}
            </span>
            <span className="inline-flex items-center gap-1.5 text-sm text-gray-700">
              <span className="w-2.5 h-2.5 rounded-full bg-green-400" />
              {resultado.total_entregas} entrega{resultado.total_entregas === 1 ? "" : "s"}
            </span>
            <span className="inline-flex items-center gap-1.5 text-sm text-gray-700">
              <span className="w-2.5 h-2.5 rounded-full bg-gray-400" />
              {resultado.total_ninguna} no encontrado{resultado.total_ninguna === 1 ? "" : "s"}
            </span>
          </div>

          <div className="border border-gray-200 rounded-xl overflow-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-gray-500 text-xs">
                  <th className="text-left px-3 py-2 font-medium">Serial</th>
                  <th className="text-left px-3 py-2 font-medium">Clasificación</th>
                  <th className="text-left px-3 py-2 font-medium">Fuente</th>
                  <th className="text-left px-3 py-2 font-medium">Estado</th>
                  <th className="text-left px-3 py-2 font-medium">Cliente / Nombre</th>
                  <th className="text-left px-3 py-2 font-medium">Planilla</th>
                  <th className="text-left px-3 py-2 font-medium">Mensajero</th>
                  <th className="text-left px-3 py-2 font-medium">Fecha</th>
                </tr>
              </thead>
              <tbody>
                {resultado.items.map((item) => (
                  <tr key={item.serial} className="border-t border-gray-100">
                    <td className="px-3 py-2 text-gray-900 font-mono text-xs">{item.serial}</td>
                    <td className="px-3 py-2">
                      <ClasificacionBadge clasificacion={item.clasificacion} />
                    </td>
                    <td className="px-3 py-2 text-gray-500 text-xs">
                      {item.fuente === "seriales_gestion"
                        ? "Gestión"
                        : item.fuente === "devoluciones"
                        ? "Devoluciones"
                        : "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-600">{item.estado_detalle ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-600">{item.cliente ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-600">{item.planilla ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-600">{item.cod_men ?? "—"}</td>
                    <td className="px-3 py-2 text-gray-400 text-xs">{item.fecha ?? "—"}</td>
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
