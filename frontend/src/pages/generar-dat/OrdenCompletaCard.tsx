import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Download, FileStack, FileText, Upload, X } from "lucide-react";
import { ordenCompletaApi, type OrdenCompletaResult } from "@/api/generarDat";
import { descargarBase64, XLSX_MIME } from "./descargas";

function Resultado({ data }: { data: OrdenCompletaResult }) {
  return (
    <div className="mt-4 border-t border-gray-100 pt-4">
      <p className="text-sm text-gray-700 mb-3">
        Orden <span className="font-semibold">{data.orden}</span> —{" "}
        <span className="font-semibold">{data.seriales.toLocaleString("es-CO")}</span> seriales en el archivo — fecha
        inicial {data.fecha_ini}.
      </p>
      <div className="flex flex-wrap gap-3">
        {data.dats.map((d) => (
          <button
            key={d.tipo}
            type="button"
            onClick={() => descargarBase64(d.base64, d.nombre, "text/plain")}
            className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Download size={16} />
            {d.tipo === "terceros" ? "Terceros" : "Centralizado"}: {d.nombre} ({d.registros.toLocaleString("es-CO")})
          </button>
        ))}
        {data.por_revisar_base64 && data.nombre_por_revisar && (
          <button
            type="button"
            onClick={() => descargarBase64(data.por_revisar_base64!, data.nombre_por_revisar!, XLSX_MIME)}
            className="inline-flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
          >
            <Download size={16} />
            Por revisar ({data.por_revisar.length})
          </button>
        )}
      </div>

      {data.duplicados.length > 0 && (
        <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-xl p-3 flex items-start gap-2">
          <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-yellow-800">
            {data.duplicados.length} serial(es) repetidos en el archivo (se tomó la última fila):{" "}
            <span className="font-mono text-xs break-all">
              {data.duplicados.slice(0, 30).join(", ")}
              {data.duplicados.length > 30 && ` … y ${data.duplicados.length - 30} más`}
            </span>
          </p>
        </div>
      )}

      {data.por_revisar.length > 0 && (
        <>
          <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-xl p-3 flex items-start gap-2">
            <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-yellow-800">
              {data.por_revisar.length} serial(es) no entraron a los .dat: su estado no corresponde a una causal BCS
              o no tienen un f_emi válido.
            </p>
          </div>
          <div className="mt-3 border border-gray-200 rounded-xl overflow-auto max-h-64">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0">
                <tr className="bg-gray-50 text-gray-500 text-xs">
                  <th className="text-left px-3 py-2 font-medium">Serial</th>
                  <th className="text-left px-3 py-2 font-medium">Courier</th>
                  <th className="text-left px-3 py-2 font-medium">Estado</th>
                  <th className="text-left px-3 py-2 font-medium">Falta</th>
                </tr>
              </thead>
              <tbody>
                {data.por_revisar.map((s) => (
                  <tr key={s.serial} className="border-t border-gray-100">
                    <td className="px-3 py-1.5 font-mono text-xs text-gray-900">{s.serial}</td>
                    <td className="px-3 py-1.5 text-gray-600">{s.courrier || "—"}</td>
                    <td className="px-3 py-1.5 text-gray-600">{s.motivo || "Sin estado"}</td>
                    <td className="px-3 py-1.5 text-gray-600">{s.falta}</td>
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

function CampoInforme({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-gray-700">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value.toUpperCase().replace(/[^A-Z]/g, ""))}
        maxLength={3}
        placeholder="Ej: CON, CLP"
        className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
      />
    </label>
  );
}

export function OrdenCompletaCard() {
  const [fechaIni, setFechaIni] = useState("");
  const [informeCentralizado, setInformeCentralizado] = useState("CON");
  const [informeTerceros, setInformeTerceros] = useState("CON");
  const [file, setFile] = useState<File | null>(null);
  const [errorLocal, setErrorLocal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: () =>
      ordenCompletaApi.generar(fechaIni, informeCentralizado, informeTerceros, file!).then((r) => r.data),
  });

  function elegir(lista: FileList | null) {
    const f = lista?.[0];
    if (inputRef.current) inputRef.current.value = "";
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".xlsx")) return setErrorLocal("Solo se aceptan archivos .xlsx");
    setErrorLocal("");
    setFile(f);
    mutation.reset();
  }

  function handleGenerar() {
    setErrorLocal("");
    if (!fechaIni) return setErrorLocal("Selecciona la fecha inicial");
    if (!/^[A-Z]{3}$/.test(informeCentralizado) || !/^[A-Z]{3}$/.test(informeTerceros))
      return setErrorLocal("El nombre de cada informe debe tener 3 letras");
    if (!file) return setErrorLocal("Sube el Excel de la orden");
    mutation.mutate();
  }

  const errorApi = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "Error al generar los .dat")
    : "";

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <FileStack size={16} className="text-primary" />
        .dat desde la orden completa
      </h2>
      <p className="text-xs text-gray-500 mb-3">
        Sube el Excel de la orden (columnas <code className="bg-gray-100 px-1 rounded">serial, estado, f_emi, orden,
        identdes, oficina, nombred, dir_pred, barrd1, ciudad1, dpto1, courrier</code>) y salen los .dat centralizado y
        terceros. La causal sale de <code className="bg-gray-100 px-1 rounded">estado</code>, F_recepcio es el f_emi y
        F_GESTION es F_recepcio más 2 a 6 días al azar. No consulta bases_web.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
        <label className="block">
          <span className="text-xs font-medium text-gray-700">Fecha inicial</span>
          <input
            type="date"
            value={fechaIni}
            onChange={(e) => {
              setFechaIni(e.target.value);
              mutation.reset();
            }}
            className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
          />
        </label>
        <CampoInforme label="Informe centralizado" value={informeCentralizado} onChange={setInformeCentralizado} />
        <CampoInforme label="Informe terceros" value={informeTerceros} onChange={setInformeTerceros} />
      </div>

      {file ? (
        <div className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
          <span className="flex items-center gap-2 text-sm text-gray-800">
            <FileText size={16} className="text-primary" />
            {file.name}
          </span>
          <button
            type="button"
            onClick={() => {
              setFile(null);
              mutation.reset();
            }}
            className="text-gray-400 hover:text-red-500"
            aria-label={`Quitar ${file.name}`}
          >
            <X size={16} />
          </button>
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            elegir(e.dataTransfer.files);
          }}
          className="border-2 border-dashed border-gray-300 rounded-xl p-5 text-center cursor-pointer hover:border-primary hover:bg-blue-50 transition-colors"
        >
          <div className="flex flex-col items-center gap-1.5">
            <Upload size={22} className="text-gray-400" />
            <p className="text-sm text-gray-700">Arrastra el Excel de la orden o haz clic para seleccionarlo</p>
          </div>
        </div>
      )}
      <input ref={inputRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => elegir(e.target.files)} />

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
            <FileStack size={16} />
            Generar .dat centralizado y terceros
          </>
        )}
      </button>

      {(errorLocal || errorApi) && (
        <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
          <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{errorLocal || errorApi}</p>
        </div>
      )}

      {mutation.data && <Resultado data={mutation.data} />}
    </div>
  );
}
