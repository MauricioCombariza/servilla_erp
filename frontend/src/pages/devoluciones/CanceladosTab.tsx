import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Ban } from "lucide-react";
import { devolucionesApi, type CanceladoItem } from "@/api/devoluciones";

const MAX_SERIALES = 500;

const RESULTADO: Record<CanceladoItem["resultado"], { label: string; clases: string }> = {
  nuevo: { label: "Registrado", clases: "bg-green-100 text-green-800" },
  actualizado: { label: "Cambiado a cancelado", clases: "bg-blue-100 text-blue-800" },
  ya_cancelado: { label: "Ya estaba cancelado", clases: "bg-gray-100 text-gray-600" },
  invalido: { label: "No es un serial válido", clases: "bg-red-100 text-red-800" },
};

function parseSeriales(texto: string): string[] {
  return Array.from(new Set(texto.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)));
}

/** Paquetes cancelados por la aplicación y retornados al cliente: quedan en devoluciones
 *  con estado "cancelado" y dejan de contar como pendientes / estancados. */
export function CanceladosTab() {
  const [texto, setTexto] = useState("");
  const [errorLocal, setErrorLocal] = useState("");
  const queryClient = useQueryClient();
  const seriales = parseSeriales(texto);

  const mutation = useMutation({
    mutationFn: (lista: string[]) => devolucionesApi.marcarCancelados(lista).then((r) => r.data),
    onSuccess: () => {
      setTexto("");
      queryClient.invalidateQueries({ queryKey: ["devoluciones"] });
      queryClient.invalidateQueries({ queryKey: ["paquetes-estancados"] });
    },
  });

  function registrar() {
    setErrorLocal("");
    if (seriales.length === 0) return setErrorLocal("Escribe o escanea al menos un serial");
    if (seriales.length > MAX_SERIALES) return setErrorLocal(`Máximo ${MAX_SERIALES} seriales por vez`);
    mutation.mutate(seriales);
  }

  const error =
    errorLocal ||
    (mutation.isError
      ? ((mutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Error al registrar los cancelados")
      : "");
  const r = mutation.data;

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <div>
          <h2 className="font-semibold text-gray-900">Paquetes cancelados por la aplicación</h2>
          <p className="text-sm text-gray-500">
            Escanea o pega los seriales que la aplicación canceló y se retornaron al cliente, uno por
            línea. Quedan en devoluciones con estado <b>cancelado</b>, con los datos de la base de
            despacho, y ya no salen como pendientes ni como paquetes estancados.
          </p>
        </div>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={8}
          placeholder={"6101526556557\n3671050777091\n…"}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm"
        />
        <div className="flex items-center gap-3">
          <button
            onClick={registrar}
            disabled={mutation.isPending || seriales.length === 0}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            <Ban size={16} />
            {mutation.isPending ? "Registrando…" : `Marcar ${seriales.length || ""} como cancelados`}
          </button>
          {error && (
            <span className="flex items-center gap-1.5 text-sm text-red-600">
              <AlertCircle size={16} /> {error}
            </span>
          )}
        </div>
      </div>

      {r && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b text-sm text-gray-700 flex flex-wrap gap-x-4 gap-y-1">
            <span><b>{r.nuevos}</b> registrados</span>
            <span><b>{r.actualizados}</b> cambiados a cancelado</span>
            <span><b>{r.ya_cancelados}</b> ya estaban</span>
            {r.invalidos > 0 && (
              <span className="text-red-700"><b>{r.invalidos}</b> no son seriales válidos (no se guardaron)</span>
            )}
          </div>
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-500 bg-gray-50">
              <tr>
                <th className="text-left px-4 py-2 font-medium">Serial</th>
                <th className="text-left px-4 py-2 font-medium">Resultado</th>
                <th className="text-left px-4 py-2 font-medium">Estado anterior</th>
                <th className="text-left px-4 py-2 font-medium">En la base</th>
              </tr>
            </thead>
            <tbody>
              {r.items.map((i) => (
                <tr key={i.serial} className="border-t">
                  <td className="px-4 py-1.5 font-mono">{i.serial}</td>
                  <td className="px-4 py-1.5">
                    <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${RESULTADO[i.resultado].clases}`}>
                      {RESULTADO[i.resultado].label}
                    </span>
                  </td>
                  <td className="px-4 py-1.5">{i.estado_anterior ?? "—"}</td>
                  <td className="px-4 py-1.5">{i.resultado === "invalido" ? "—" : i.en_base ? "Sí" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
