import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapContainer, TileLayer, GeoJSON, Polygon, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { area as turfArea } from "@turf/turf";
import { Pencil, Trash2, Eye, EyeOff, Hexagon } from "lucide-react";
import { geocercasApi, type Geocerca, type GeoJSONPolygon } from "@/api/geocercas";

const CENTRO_BARRIOS_UNIDOS: [number, number] = [4.6697, -74.0755];
const ZOOM_INICIAL = 14;
const NOMBRE_BARRIOS_UNIDOS = "BARRIOS UNIDOS";
const LOCALIDADES_URL = "/data/localidades-bogota.geojson";

function estiloLocalidad(feature?: GeoJSON.Feature) {
  const esBarriosUnidos = feature?.properties?.LocNombre === NOMBRE_BARRIOS_UNIDOS;
  return esBarriosUnidos
    ? { color: "#1d550e", weight: 3, fillOpacity: 0.04, fillColor: "#1d550e" }
    : { color: "#9ca3af", weight: 1, fillOpacity: 0, dashArray: "3" };
}

function formatArea(m2: number) {
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(m2)} m²`;
}

function anilloAGeoJSON(latlngs: L.LatLng[]): GeoJSONPolygon {
  const coords: number[][] = latlngs.map((p) => [p.lng, p.lat]);
  const primero = coords[0];
  const ultimo = coords[coords.length - 1];
  if (primero && (primero[0] !== ultimo[0] || primero[1] !== ultimo[1])) {
    coords.push(primero);
  }
  return { type: "Polygon", coordinates: [coords] };
}

interface DibujoResultado {
  poligono: GeoJSONPolygon;
  areaM2: number;
  layer: L.Layer;
}

function DibujoGeocercas({ onDibujado }: { onDibujado: (r: DibujoResultado) => void }) {
  const map = useMap();

  useEffect(() => {
    map.pm.addControls({
      position: "topleft",
      drawMarker: false,
      drawCircleMarker: false,
      drawPolyline: false,
      drawRectangle: false,
      drawCircle: false,
      drawText: false,
      drawPolygon: true,
      editMode: false,
      dragMode: false,
      cutPolygon: false,
      removalMode: false,
      rotateMode: false,
    });

    function handleCreate(e: { layer: L.Layer }) {
      const layer = e.layer as L.Polygon;
      const anillo = (layer.getLatLngs()[0] as L.LatLng[]);
      const poligono = anilloAGeoJSON(anillo);
      const areaM2 = turfArea(poligono as unknown as Parameters<typeof turfArea>[0]);
      onDibujado({ poligono, areaM2, layer });
    }

    map.on("pm:create", handleCreate);
    return () => {
      map.off("pm:create", handleCreate);
      map.pm.removeControls();
    };
  }, [map, onDibujado]);

  return null;
}

export function GeocercasPage() {
  const qc = useQueryClient();
  const [visibles, setVisibles] = useState<Set<number>>(new Set());
  const [pendiente, setPendiente] = useState<DibujoResultado | null>(null);
  const [nombrePendiente, setNombrePendiente] = useState("");
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [nombreEditado, setNombreEditado] = useState("");

  const { data: geocercas = [], isLoading } = useQuery({
    queryKey: ["geocercas"],
    queryFn: () => geocercasApi.listar(true).then((r) => r.data),
  });

  const { data: localidades } = useQuery({
    queryKey: ["localidades-bogota"],
    queryFn: () => fetch(LOCALIDADES_URL).then((r) => r.json() as Promise<GeoJSON.FeatureCollection>),
    staleTime: Infinity,
  });

  useEffect(() => {
    setVisibles(new Set(geocercas.map((g) => g.id)));
  }, [geocercas.map((g) => g.id).join(",")]);

  const crear = useMutation({
    mutationFn: (body: { nombre: string; poligono: GeoJSONPolygon }) => geocercasApi.crear(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["geocercas"] });
      pendiente?.layer.remove();
      setPendiente(null);
      setNombrePendiente("");
    },
  });

  const renombrar = useMutation({
    mutationFn: ({ id, nombre }: { id: number; nombre: string }) =>
      geocercasApi.actualizar(id, { nombre }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["geocercas"] });
      setEditandoId(null);
    },
  });

  const eliminar = useMutation({
    mutationFn: (id: number) => geocercasApi.eliminar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["geocercas"] }),
  });

  function handleDibujado(r: DibujoResultado) {
    setPendiente(r);
    setNombrePendiente("");
  }

  function confirmarCreacion() {
    if (!pendiente || !nombrePendiente.trim()) return;
    crear.mutate({ nombre: nombrePendiente.trim(), poligono: pendiente.poligono });
  }

  function cancelarCreacion() {
    pendiente?.layer.remove();
    setPendiente(null);
    setNombrePendiente("");
  }

  function toggleVisible(id: number) {
    setVisibles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const geocercasVisibles = useMemo(
    () => geocercas.filter((g) => visibles.has(g.id)),
    [geocercas, visibles]
  );

  return (
    <div>
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
          <Hexagon size={20} className="text-primary" />
          Geocercas — Barrios Unidos
        </h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Dibuja hexágonos sobre el mapa (herramienta de polígono, arriba a la izquierda) para
          sectorizar el territorio. Haz clic para ubicar cada vértice y cierra el polígono sobre el
          primer punto.
        </p>
      </div>

      <div className="rounded-xl overflow-hidden border border-gray-200 mb-4" style={{ height: 520 }}>
        <MapContainer center={CENTRO_BARRIOS_UNIDOS} zoom={ZOOM_INICIAL} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {localidades && <GeoJSON data={localidades} style={estiloLocalidad} />}
          <DibujoGeocercas onDibujado={handleDibujado} />
          {geocercasVisibles.map((g) => (
            <Polygon
              key={g.id}
              positions={g.poligono.coordinates[0].map(([lng, lat]) => [lat, lng] as [number, number])}
              pathOptions={{ color: "#2563eb", weight: 2, fillOpacity: 0.15, fillColor: "#3b82f6" }}
            >
              <Tooltip sticky>
                {g.nombre} — {formatArea(g.area_m2)}
              </Tooltip>
            </Polygon>
          ))}
        </MapContainer>
      </div>

      {pendiente && (
        <div className="mb-4 bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-3">
          <div className="text-sm text-gray-700">
            Área calculada: <span className="font-semibold">{formatArea(pendiente.areaM2)}</span>
          </div>
          <input
            autoFocus
            type="text"
            placeholder="Nombre de la geocerca"
            value={nombrePendiente}
            onChange={(e) => setNombrePendiente(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && confirmarCreacion()}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm flex-1 max-w-xs"
          />
          <button
            onClick={confirmarCreacion}
            disabled={!nombrePendiente.trim() || crear.isPending}
            className="bg-primary hover:bg-primary-hover text-white text-sm font-medium px-3 py-1.5 rounded-lg disabled:opacity-50"
          >
            {crear.isPending ? "Guardando..." : "Guardar"}
          </button>
          <button
            onClick={cancelarCreacion}
            className="text-sm text-gray-500 hover:text-gray-700 px-2"
          >
            Cancelar
          </button>
        </div>
      )}

      {crear.isError && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-xl p-3 text-sm text-red-700">
          No se pudo guardar la geocerca. Verifica que el polígono no tenga bordes cruzados.
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-10 text-gray-500">Cargando...</div>
      ) : geocercas.length === 0 ? (
        <div className="text-center py-10 text-gray-400">Aún no hay geocercas creadas</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Nombre", "Área", "Creado por", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {geocercas.map((g: Geocerca) => (
                <tr key={g.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">
                    {editandoId === g.id ? (
                      <input
                        autoFocus
                        type="text"
                        value={nombreEditado}
                        onChange={(e) => setNombreEditado(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && nombreEditado.trim()) {
                            renombrar.mutate({ id: g.id, nombre: nombreEditado.trim() });
                          }
                          if (e.key === "Escape") setEditandoId(null);
                        }}
                        className="border border-gray-300 rounded px-2 py-1 text-sm w-full max-w-xs"
                      />
                    ) : (
                      g.nombre
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{formatArea(g.area_m2)}</td>
                  <td className="px-4 py-3 text-gray-600">{g.creado_por ?? "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleVisible(g.id)}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title={visibles.has(g.id) ? "Ocultar en el mapa" : "Mostrar en el mapa"}
                      >
                        {visibles.has(g.id) ? <Eye size={15} /> : <EyeOff size={15} />}
                      </button>
                      <button
                        onClick={() => {
                          setEditandoId(g.id);
                          setNombreEditado(g.nombre);
                        }}
                        className="text-gray-400 hover:text-primary transition-colors"
                        title="Renombrar"
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        onClick={() => confirm(`¿Eliminar la geocerca "${g.nombre}"?`) && eliminar.mutate(g.id)}
                        className="text-gray-400 hover:text-red-600 transition-colors"
                        title="Eliminar"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
