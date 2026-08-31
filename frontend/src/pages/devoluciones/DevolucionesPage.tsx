import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, AlertCircle, CheckCircle, FileText, Search } from "lucide-react";
import { devolucionesApi } from "@/api/devoluciones";

const ESTADOS_SUGERIDOS = ["transito", "entregado", "no_ubicado", "reasignado", "devolucion"];

function formatFecha(iso: string) {
  return new Date(iso).toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}

function EstadoSelect({ id, estado }: { id: number; estado: string }) {
  const queryClient = useQueryClient();
  const [valor, setValor] = useState(estado);

  const mutation = useMutation({
    mutationFn: (nuevoEstado: string) => devolucionesApi.updateEstado(id, nuevoEstado),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devoluciones"] }),
    onError: () => setValor(estado),
  });

  const opciones = ESTADOS_SUGERIDOS.includes(estado)
    ? ESTADOS_SUGERIDOS
    : [estado, ...ESTADOS_SUGERIDOS];

  return (
    <select
      value={valor}
      onChange={(e) => {
        const nuevo = e.target.value;
        setValor(nuevo);
        mutation.mutate(nuevo);
      }}
      disabled={mutation.isPending}
      className="text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white disabled:opacity-50"
    >
      {opciones.map((op) => (
        <option key={op} value={op}>
          {op}
        </option>
      ))}
    </select>
  );
}

export function DevolucionesPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [q, setQ] = useState("");

  const queryClient = useQueryClient();

  const { data: devoluciones = [], isLoading, isError } = useQuery({
    queryKey: ["devoluciones", estadoFiltro, q],
    queryFn: () =>
      devolucionesApi
        .list({ estado: estadoFiltro || undefined, q: q || undefined })
        .then((r) => r.data),
  });

  const cargaMutation = useMutation({
    mutationFn: (f: File) => devolucionesApi.cargaMasiva(f),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["devoluciones"] });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setUploadError(msg ?? "Error al procesar el archivo");
    },
  });

  function handleUpload() {
    if (!file) return;
    setUploadError("");
    cargaMutation.mutate(file);
  }

  const resultado = cargaMutation.data?.data;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Devoluciones</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Seriales devueltos, cargados desde Excel. Al subir un archivo, los seriales
          nuevos entran con estado "transito"; los que ya existen solo actualizan sus
          datos de contacto (el estado no se pisa).
        </p>
      </div>

      {/* Zona de carga */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">Cargar Excel</h2>
        <p className="text-xs text-gray-500 mb-3">
          Columnas requeridas: <code className="bg-gray-100 px-1 rounded">serial, nombre, telefono, direccion, localidad</code>
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
                setUploadError("");
                cargaMutation.reset();
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

        {file && !resultado && (
          <button
            onClick={handleUpload}
            disabled={cargaMutation.isPending}
            className="mt-3 w-full bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-xl text-sm transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {cargaMutation.isPending ? (
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

        {uploadError && (
          <div className="mt-3 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
            <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{uploadError}</p>
          </div>
        )}

        {resultado && (
          <div className="mt-3 bg-green-50 border border-green-200 rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle size={16} className="text-green-500" />
              <p className="text-sm font-medium text-gray-900">
                {resultado.total_filas} filas · {resultado.nuevas} nuevas · {resultado.actualizadas} actualizadas
              </p>
            </div>
            {resultado.errores.length > 0 && (
              <ul className="space-y-1 mt-2">
                {resultado.errores.map((e, i) => (
                  <li key={i} className="text-xs text-yellow-700 font-mono bg-yellow-100 px-2 py-1 rounded">
                    {e}
                  </li>
                ))}
              </ul>
            )}
            <button
              onClick={() => {
                cargaMutation.reset();
                setFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="mt-2 text-xs text-primary hover:underline"
            >
              Cargar otro archivo
            </button>
          </div>
        )}
      </div>

      {/* Filtros */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por serial o nombre"
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg"
          />
        </div>
        <select
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-2 py-1.5"
        >
          <option value="">Todos los estados</option>
          {ESTADOS_SUGERIDOS.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
      </div>

      {/* Tabla */}
      {isLoading ? (
        <p className="text-sm text-gray-500">Cargando...</p>
      ) : isError ? (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">Error al cargar las devoluciones.</p>
        </div>
      ) : devoluciones.length === 0 ? (
        <p className="text-sm text-gray-500">No hay devoluciones cargadas.</p>
      ) : (
        <div className="border border-gray-200 rounded-xl overflow-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs">
                <th className="text-left px-3 py-2 font-medium">Serial</th>
                <th className="text-left px-3 py-2 font-medium">Nombre</th>
                <th className="text-left px-3 py-2 font-medium">Teléfono</th>
                <th className="text-left px-3 py-2 font-medium">Dirección</th>
                <th className="text-left px-3 py-2 font-medium">Localidad</th>
                <th className="text-left px-3 py-2 font-medium">Estado</th>
                <th className="text-left px-3 py-2 font-medium">Actualizado</th>
              </tr>
            </thead>
            <tbody>
              {devoluciones.map((d) => (
                <tr key={d.id} className="border-t border-gray-100">
                  <td className="px-3 py-2 text-gray-900 font-mono text-xs">{d.serial}</td>
                  <td className="px-3 py-2 text-gray-700">{d.nombre}</td>
                  <td className="px-3 py-2 text-gray-600">{d.telefono}</td>
                  <td className="px-3 py-2 text-gray-600 max-w-xs truncate" title={d.direccion ?? ""}>
                    {d.direccion}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{d.localidad}</td>
                  <td className="px-3 py-2">
                    <EstadoSelect id={d.id} estado={d.estado} />
                  </td>
                  <td className="px-3 py-2 text-gray-400 text-xs">{formatFecha(d.fecha_actualizacion)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
