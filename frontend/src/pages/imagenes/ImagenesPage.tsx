import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { imagenesApi, type ImagenesModo, type ImagenGuia, type ImagenListItem } from "@/api/imagenes";

const MODOS: { value: ImagenesModo; label: string; placeholder: string }[] = [
  { value: "serial",    label: "Serial / Guía", placeholder: "Ej: 9003860413" },
  { value: "nombre",    label: "Nombre",        placeholder: "Ej: barbara monroy" },
  { value: "direccion", label: "Dirección",     placeholder: "Ej: CR 62 70B" },
];

function DetailCard({ data }: { data: ImagenGuia }) {
  return (
    <div className="mt-6 border border-gray-200 rounded-xl p-5 bg-gray-50">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Detalle</h3>
      <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
        <div><span className="text-gray-500">Serial:</span>{" "}<span className="font-mono font-medium">{data.serial}</span></div>
        {data.no_entidad && <div><span className="text-gray-500">Cliente:</span> {data.no_entidad}</div>}
        {data.nombred    && <div><span className="text-gray-500">Nombre:</span> {data.nombred}</div>}
        {data.dirdes1    && <div className="col-span-2"><span className="text-gray-500">Dirección:</span> {data.dirdes1}</div>}
        {data.ciudad1    && <div><span className="text-gray-500">Ciudad:</span> {data.ciudad1}</div>}
        {data.dir_num    && <div><span className="text-gray-500">Dir. Num:</span> {data.dir_num}</div>}
        {data.cod_sec    && <div><span className="text-gray-500">Cod. Sec:</span> {data.cod_sec}</div>}
        {data.servicio   && <div><span className="text-gray-500">Servicio:</span> {data.servicio}</div>}
        {data.orden      && <div><span className="text-gray-500">Orden:</span> {data.orden}</div>}
        {data.planilla   && <div><span className="text-gray-500">Planilla:</span> <span className="font-mono">{data.planilla}</span></div>}
        {data.cod_men    && <div><span className="text-gray-500">Mensajero:</span> {data.cod_men}</div>}
        {data.f_emi      && <div><span className="text-gray-500">Fecha Emisión:</span> {data.f_emi}</div>}
        {data.f_lleva    && <div><span className="text-gray-500">Fecha Lleva:</span> {data.f_lleva}</div>}
        {data.retorno    && <div><span className="text-gray-500">Retorno:</span> {data.retorno}</div>}
        {data.ret_esc    && <div><span className="text-gray-500">Ret. Esc:</span> {data.ret_esc}</div>}
        {data.comentario && <div className="col-span-2"><span className="text-gray-500">Comentario:</span> {data.comentario}</div>}
      </div>
    </div>
  );
}

export function ImagenesPage() {
  const [modo, setModo] = useState<ImagenesModo>("serial");
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [serialDetalle, setSerialDetalle] = useState<string | null>(null);
  const [fotoUrl, setFotoUrl] = useState<string | null>(null);
  const [fotoError, setFotoError] = useState(false);
  const [fotoLoading, setFotoLoading] = useState(false);

  const minLen = modo === "serial" ? 1 : 2;

  const { data: detalle, isFetching: isFetchingDetalle, isError: isErrorDetalle } = useQuery({
    queryKey: ["imagenes-detalle", serialDetalle],
    queryFn: () => imagenesApi.obtenerImagen(serialDetalle as string).then((r) => r.data),
    enabled: !!serialDetalle,
    staleTime: 15_000,
  });

  const { data: lista, isFetching: isFetchingLista, isError: isErrorLista } = useQuery({
    queryKey: ["imagenes-lista", q, modo],
    queryFn: () => imagenesApi.buscarLista(q, modo as "nombre" | "direccion").then((r) => r.data),
    enabled: modo !== "serial" && q.length >= 2,
    staleTime: 15_000,
  });

  useEffect(() => {
    setFotoUrl(null);
    setFotoError(false);
    if (!serialDetalle) return;

    let cancelado = false;
    let urlCreada: string | null = null;
    setFotoLoading(true);

    imagenesApi
      .obtenerFoto(serialDetalle)
      .then((r) => {
        if (cancelado) return;
        urlCreada = URL.createObjectURL(r.data);
        setFotoUrl(urlCreada);
      })
      .catch(() => {
        if (!cancelado) setFotoError(true);
      })
      .finally(() => {
        if (!cancelado) setFotoLoading(false);
      });

    return () => {
      cancelado = true;
      if (urlCreada) URL.revokeObjectURL(urlCreada);
    };
  }, [serialDetalle]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (trimmed.length < minLen) return;
    setQ(trimmed);
    if (modo === "serial") {
      setSerialDetalle(trimmed);
    } else {
      setSerialDetalle(null);
    }
  }

  function handleModoChange(m: ImagenesModo) {
    setModo(m);
    setInput("");
    setQ("");
    setSerialDetalle(null);
  }

  const placeholder = MODOS.find((m) => m.value === modo)?.placeholder ?? "";
  const isFetching = modo === "serial" ? isFetchingDetalle : isFetchingLista;
  const isError = modo === "serial" ? isErrorDetalle : isErrorLista;

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Imágenes de Guía</h1>
      <p className="text-sm text-gray-500 mb-6">
        Busca en el histórico (bases_web) por serial, nombre o dirección, y muestra la imagen de la guía asociada.
      </p>

      <div className="flex gap-1 mb-4 bg-gray-100 p-1 rounded-lg w-fit">
        {MODOS.map((m) => (
          <button
            key={m.value}
            onClick={() => handleModoChange(m.value)}
            className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
              modo === m.value
                ? "bg-white shadow text-gray-900 font-medium"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <div className="relative flex-1 max-w-lg">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={placeholder}
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={input.trim().length < minLen}
          className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg disabled:opacity-50 hover:bg-primary/90 transition-colors"
        >
          Buscar
        </button>
      </form>

      {isFetching && <p className="text-sm text-gray-500 mb-4">Buscando...</p>}
      {isError && (
        <p className="text-sm text-red-600 mb-4">Error al buscar. Intenta de nuevo.</p>
      )}

      {modo !== "serial" && lista && lista.length === 0 && !isFetchingLista && (
        <p className="text-sm text-gray-500">No se encontraron resultados.</p>
      )}

      {modo !== "serial" && lista && lista.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden mb-6">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Serial</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Nombre</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Dirección</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Ciudad</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Fecha</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Mensajero</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {lista.map((item: ImagenListItem, idx: number) => (
                  <tr key={`${item.serial}-${idx}`} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">
                      <button
                        onClick={() => setSerialDetalle(item.serial)}
                        className="text-primary hover:underline"
                      >
                        {item.serial}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{item.nombred ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{item.dirdes1 ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-700">{item.ciudad1 ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">{item.f_emi ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-600">{item.cod_men ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-700">
                      {item.motivo || item.ret_esc || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detalle && !detalle.encontrado && (
        <div className="mb-4 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
          No se encontró el serial en el histórico (bases_web), pero se muestra la imagen calculada.
        </div>
      )}

      {detalle && fotoLoading && (
        <p className="text-sm text-gray-500 mb-4">Cargando imagen...</p>
      )}
      {detalle && fotoUrl && (
        <img
          src={fotoUrl}
          alt={`Guía ${detalle.serial}`}
          className="max-w-full border border-gray-200 rounded-lg"
        />
      )}
      {detalle && fotoError && (
        <p className="text-sm text-red-600">
          No se pudo cargar la imagen desde el servidor de guías.
        </p>
      )}

      {detalle && <DetailCard data={detalle} />}
    </div>
  );
}
