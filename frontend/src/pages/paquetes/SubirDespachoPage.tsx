import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import {
  paquetesDespachoApi,
  type CargaDespachoResult,
  type ColumnasFaltantes,
  type PaqueteSinSector,
} from "@/api/paquetesDespacho";

/** Fecha de hoy en Bogotá (YYYY-MM-DD), aunque el celular tenga otra zona horaria. */
function hoyBogota(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota" }).format(new Date());
}

type ErrorCarga = { mensaje: string; faltantes?: string[]; columnasArchivo?: string[] };

function leerError(e: unknown): ErrorCarga {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail && typeof detail === "object" && "faltantes" in detail) {
    const d = detail as ColumnasFaltantes;
    return { mensaje: "Este archivo no es una base de despacho de iMile", faltantes: d.faltantes, columnasArchivo: d.columnas_archivo };
  }
  return { mensaje: typeof detail === "string" ? detail : "No se pudo subir el archivo" };
}

/**
 * Paso 1.4: subir desde el celular la base de despacho que llega por WhatsApp.
 * El Excel se elige del celular (carpeta de documentos de WhatsApp), se sectoriza y queda
 * listo para los cruces del escaneo. Las direcciones sin sector se corrigen aquí mismo.
 */
export function SubirDespachoPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [fEmi, setFEmi] = useState(hoyBogota());
  const [resultado, setResultado] = useState<CargaDespachoResult | null>(null);
  const [error, setError] = useState<ErrorCarga | null>(null);

  const cargar = useMutation({
    mutationFn: () => paquetesDespachoApi.cargar(archivo!, fEmi).then((r) => r.data),
    onSuccess: (data) => {
      setResultado(data);
      setError(null);
    },
    onError: (e) => {
      setResultado(null);
      setError(leerError(e));
    },
  });

  function elegirArchivo(file: File | null) {
    setArchivo(file);
    setResultado(null);
    setError(null);
  }

  function otraBase() {
    elegirArchivo(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="mx-auto w-full max-w-md space-y-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-1">Subir base de despacho</h1>
          <p className="text-sm text-gray-500 mb-5">
            Elige el Excel que llegó por WhatsApp. Se guarda y se sectoriza para los cruces del escaneo.
          </p>

          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            onChange={(e) => elegirArchivo(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="w-full flex items-center gap-3 border-2 border-dashed border-gray-300 rounded-lg px-4 py-4 text-left hover:border-primary transition-colors"
          >
            <FileSpreadsheet className="shrink-0 text-primary" size={28} />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-gray-900 truncate">
                {archivo ? archivo.name : "Elegir archivo Excel (.xlsx)"}
              </span>
              <span className="block text-xs text-gray-500">
                {archivo ? `${(archivo.size / 1024).toFixed(0)} KB · tocar para cambiar` : "Desde Documentos de WhatsApp"}
              </span>
            </span>
          </button>

          <label className="block text-sm font-medium text-gray-700 mt-4 mb-1" htmlFor="f_emi">
            Fecha de ingreso
          </label>
          <input
            id="f_emi"
            type="date"
            value={fEmi}
            onChange={(e) => setFEmi(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-3 text-base focus:ring-2 focus:ring-primary focus:border-primary outline-none"
          />

          <button
            type="button"
            disabled={!archivo || !fEmi || cargar.isPending}
            onClick={() => cargar.mutate()}
            className="w-full inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-lg text-base transition-colors disabled:opacity-40 disabled:cursor-not-allowed mt-5"
          >
            <Upload size={18} />
            {cargar.isPending ? "Subiendo y sectorizando..." : "Subir base"}
          </button>

          {error && (
            <div role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <p className="font-medium">{error.mensaje}</p>
              {error.faltantes && (
                <>
                  <p className="mt-2 font-medium">Faltan estas columnas:</p>
                  <ul className="list-disc pl-5">
                    {error.faltantes.map((f) => <li key={f}>{f}</li>)}
                  </ul>
                  <p className="mt-2 font-medium">El archivo trae:</p>
                  <p className="text-xs break-words">{error.columnasArchivo?.join(" · ")}</p>
                </>
              )}
            </div>
          )}
        </div>

        {resultado && <Resultado resultado={resultado} onOtraBase={otraBase} />}
      </div>
    </div>
  );
}

function Resultado({ resultado, onOtraBase }: { resultado: CargaDespachoResult; onOtraBase: () => void }) {
  const pendientes = resultado.sin_sector.length;
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center gap-2 text-green-700 mb-4">
        <CheckCircle2 size={22} />
        <h2 className="text-lg font-semibold">Base guardada</h2>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-center">
        <Dato etiqueta="Paquetes" valor={resultado.total} />
        <Dato etiqueta="Nuevos" valor={resultado.creados} />
        <Dato etiqueta="Reemplazados" valor={resultado.reemplazados} />
        <Dato etiqueta="Sin sector" valor={pendientes} alerta={pendientes > 0} />
      </dl>

      {pendientes > 0 && (
        <div className="mt-5">
          <p className="text-sm font-medium text-gray-900">Corrige estas direcciones</p>
          <p className="text-xs text-gray-500 mb-3">
            No se pudieron ubicar. Escribe la dirección bien (ej. CL 64 # 25-12) y guarda.
          </p>
          <ul className="space-y-3">
            {resultado.sin_sector.map((p) => <CorregirDireccion key={p.serial} paquete={p} />)}
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={onOtraBase}
        className="w-full mt-5 border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg text-sm hover:bg-gray-50"
      >
        Subir otra base
      </button>
    </div>
  );
}

function Dato({ etiqueta, valor, alerta = false }: { etiqueta: string; valor: number; alerta?: boolean }) {
  return (
    <div className={`rounded-lg p-3 ${alerta ? "bg-amber-50" : "bg-gray-50"}`}>
      <dd className={`text-2xl font-bold ${alerta ? "text-amber-700" : "text-gray-900"}`}>{valor}</dd>
      <dt className="text-xs text-gray-500">{etiqueta}</dt>
    </div>
  );
}

function CorregirDireccion({ paquete }: { paquete: PaqueteSinSector }) {
  const [direccion, setDireccion] = useState(paquete.direccion ?? "");
  const corregir = useMutation({
    mutationFn: () => paquetesDespachoApi.corregirDireccion(paquete.serial, direccion).then((r) => r.data),
  });
  const corregido = corregir.data;
  const ubicado = corregido && corregido.localidad;

  return (
    <li className="rounded-lg border border-gray-200 p-3">
      <p className="text-xs text-gray-500">
        Serial <span className="font-mono text-gray-800">…{paquete.serial.slice(-4)}</span>
      </p>
      <p className="text-xs text-gray-500 break-words mb-2">{paquete.direccion}</p>
      <div className="flex gap-2">
        <input
          value={direccion}
          onChange={(e) => setDireccion(e.target.value)}
          className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none"
        />
        <button
          type="button"
          disabled={!direccion.trim() || corregir.isPending}
          onClick={() => corregir.mutate()}
          className="shrink-0 bg-primary hover:bg-primary-hover text-white text-sm font-medium px-3 rounded-lg disabled:opacity-40"
        >
          {corregir.isPending ? "..." : "Guardar"}
        </button>
      </div>
      {corregido && (
        <p className={`text-xs mt-2 ${ubicado ? "text-green-700" : "text-amber-700"}`}>
          {ubicado
            ? `✓ ${corregido.localidad}${corregido.zona ? ` · zona ${corregido.zona}` : " · fuera de zona"}`
            : "Todavía no se puede ubicar, revisa la dirección"}
        </p>
      )}
      {corregir.isError && <p className="text-xs mt-2 text-red-600">No se pudo guardar</p>}
    </li>
  );
}
