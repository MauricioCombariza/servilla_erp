import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertCircle, AlertTriangle, Download, FileSpreadsheet } from "lucide-react";
import { formatoServillaApi, type FormatoServillaResult } from "@/api/generarDat";
import { descargarBase64, XLSX_MIME } from "./descargas";

function Resultado({ data }: { data: FormatoServillaResult }) {
  return (
    <div className="mt-4 border-t border-gray-100 pt-4">
      <p className="text-sm text-gray-700 mb-3">
        <span className="font-semibold">{data.filas.toLocaleString("es-CO")}</span> seriales de la orden{" "}
        {data.orden} ({data.excluidos.toLocaleString("es-CO")} de PRINDEL y LECTA excluidos).
      </p>
      <button
        type="button"
        onClick={() => descargarBase64(data.excel_base64, data.nombre, XLSX_MIME)}
        className="inline-flex items-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors"
      >
        <Download size={16} />
        Descargar {data.nombre}
      </button>

      {data.por_revisar.length > 0 && (
        <>
          <div className="mt-4 bg-yellow-50 border border-yellow-200 rounded-xl p-3 flex items-start gap-2">
            <AlertTriangle size={16} className="text-yellow-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-yellow-800">
              {data.por_revisar.length} serial(es) quedaron incompletos (resaltados en amarillo en el Excel):
              sin causal por no tener un motivo reconocido, o sin fechas por no tener un f_emi válido. Complétalos a
              mano antes de subirlo al generador.
            </p>
          </div>
          <div className="mt-3 border border-gray-200 rounded-xl overflow-auto max-h-64">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0">
                <tr className="bg-gray-50 text-gray-500 text-xs">
                  <th className="text-left px-3 py-2 font-medium">Serial</th>
                  <th className="text-left px-3 py-2 font-medium">Courier</th>
                  <th className="text-left px-3 py-2 font-medium">Motivo</th>
                  <th className="text-left px-3 py-2 font-medium">Falta</th>
                </tr>
              </thead>
              <tbody>
                {data.por_revisar.map((s) => (
                  <tr key={s.serial} className="border-t border-gray-100">
                    <td className="px-3 py-1.5 font-mono text-xs text-gray-900">{s.serial}</td>
                    <td className="px-3 py-1.5 text-gray-600">{s.courrier || "—"}</td>
                    <td className="px-3 py-1.5 text-gray-600">{s.motivo || "Sin motivo"}</td>
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

export function FormatoServillaCard() {
  const [orden, setOrden] = useState("");
  const [errorLocal, setErrorLocal] = useState("");

  const mutation = useMutation({
    mutationFn: () => formatoServillaApi.generar(orden.trim()).then((r) => r.data),
  });

  function handleGenerar() {
    setErrorLocal("");
    if (!/^\d+$/.test(orden.trim())) return setErrorLocal("Ingresa un número de orden válido");
    mutation.mutate();
  }

  const errorApi = mutation.isError
    ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "Error al generar el formato")
    : "";

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
      <h2 className="text-sm font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <FileSpreadsheet size={16} className="text-primary" />
        Formato Servilla
      </h2>
      <p className="text-xs text-gray-500 mb-3">
        Genera el Excel de gestión de la orden con todos los courriers menos PRINDEL y LECTA. La causal sale del
        motivo en bases_web, F_recepcio es el f_emi del serial y F_GESTION es F_recepcio más 2 a 6 días al azar.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
        <label className="block">
          <span className="text-xs font-medium text-gray-700">Número de orden</span>
          <input
            value={orden}
            onChange={(e) => {
              setOrden(e.target.value);
              mutation.reset();
            }}
            inputMode="numeric"
            placeholder="Ej: 123791"
            className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
          />
        </label>
        <button
          type="button"
          onClick={handleGenerar}
          disabled={mutation.isPending}
          className="inline-flex items-center justify-center gap-2 border border-primary text-primary hover:bg-blue-50 font-medium px-4 py-2 rounded-lg text-sm transition-colors disabled:opacity-60"
        >
          {mutation.isPending ? "Generando..." : "Generar formato"}
        </button>
      </div>

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
