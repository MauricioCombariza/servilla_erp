import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { imagenesApi, type ImagenGuia } from "@/api/imagenes";

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
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [imgError, setImgError] = useState(false);

  const { data, isFetching, isError } = useQuery({
    queryKey: ["imagenes", q],
    queryFn: () => imagenesApi.obtenerImagen(q).then((r) => r.data),
    enabled: q.length > 0,
    staleTime: 15_000,
  });

  useEffect(() => {
    setImgError(false);
  }, [q]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (trimmed.length > 0) setQ(trimmed);
  }

  return (
    <div className="max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold text-gray-900 mb-1">Imágenes de Guía</h1>
      <p className="text-sm text-gray-500 mb-6">
        Busca el histórico (bases_web) por serial y muestra la imagen de la guía asociada.
      </p>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6">
        <div className="relative flex-1 max-w-lg">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ej: 9003860413"
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={input.trim().length === 0}
          className="px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg disabled:opacity-50 hover:bg-primary/90 transition-colors"
        >
          Buscar
        </button>
      </form>

      {isFetching && <p className="text-sm text-gray-500 mb-4">Buscando...</p>}
      {isError && (
        <p className="text-sm text-red-600 mb-4">Error al buscar. Intenta de nuevo.</p>
      )}

      {data && !data.encontrado && (
        <div className="mb-4 px-4 py-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
          No se encontró el serial en el histórico (bases_web), pero se muestra la imagen calculada.
        </div>
      )}

      {data && !imgError && (
        <img
          src={data.image_url}
          alt={`Guía ${data.serial}`}
          onError={() => setImgError(true)}
          className="max-w-full border border-gray-200 rounded-lg"
        />
      )}
      {data && imgError && (
        <p className="text-sm text-red-600">
          No se pudo cargar la imagen ({data.image_url}).
        </p>
      )}

      {data && <DetailCard data={data} />}
    </div>
  );
}
