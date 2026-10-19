import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertTriangle, MapPin } from "lucide-react";
import { vistaZonasApi, type PaqueteVista } from "@/api/vistaZonas";

const CADA_MS = 1500; // cada celular pide lo nuevo cada 1–2 s

function leerZonas(token: string): string[] | null {
  try {
    const v = localStorage.getItem(`ver-zonas:${token}`);
    return v ? (JSON.parse(v) as string[]) : null;
  } catch {
    return null;
  }
}

function guardarZonas(token: string, zonas: string[]) {
  try {
    localStorage.setItem(`ver-zonas:${token}`, JSON.stringify(zonas));
  } catch {
    // Sin almacenamiento (incógnito): solo toca volver a elegir al recargar
  }
}

function esEnlaceInvalido(e: unknown) {
  return (e as { response?: { status?: number } })?.response?.status === 404;
}

/**
 * Paso 2.7, página pública (sin iniciar sesión): se abre con el QR del día que genera quien
 * escanea. Cada persona elige sus zonas y ve llegar los paquetes de esas zonas y los
 * "Fuera de zona". Con un enlace vencido o inventado no se ve nada.
 */
export function VerZonasPage() {
  const { token = "" } = useParams();
  const [zonas, setZonas] = useState<string[] | null>(null);
  const [invalido, setInvalido] = useState(false);
  const [elegidas, setElegidas] = useState<string[]>(() => leerZonas(token) ?? []);
  const [mirando, setMirando] = useState(() => (leerZonas(token)?.length ?? 0) > 0);

  useEffect(() => {
    vistaZonasApi
      .zonas(token)
      .then(({ data }) => setZonas(data))
      .catch((e) => (esEnlaceInvalido(e) ? setInvalido(true) : setZonas([])));
  }, [token]);

  if (invalido) {
    return (
      <Pantalla>
        <div role="alert" className="rounded-xl bg-red-50 border border-red-200 p-4 text-red-800 flex gap-2">
          <AlertTriangle size={20} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Enlace inválido o vencido</p>
            <p className="text-sm">Pide el QR de hoy a quien está escaneando.</p>
          </div>
        </div>
      </Pantalla>
    );
  }

  if (zonas === null) {
    return (
      <Pantalla>
        <p className="text-center text-gray-500 py-16">Cargando…</p>
      </Pantalla>
    );
  }

  if (!mirando) {
    return (
      <Pantalla>
        <ElegirZonas
          zonas={zonas}
          elegidas={elegidas}
          onCambiar={setElegidas}
          onListo={() => {
            guardarZonas(token, elegidas);
            setMirando(true);
          }}
        />
      </Pantalla>
    );
  }

  return (
    <Pantalla>
      <PaquetesEnVivo
        token={token}
        zonas={elegidas}
        onInvalido={() => setInvalido(true)}
        onCambiarZonas={() => setMirando(false)}
      />
    </Pantalla>
  );
}

function Pantalla({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3">
        <p className="font-semibold text-gray-900">Paquetes por zona</p>
      </header>
      <div className="p-4 w-full max-w-md mx-auto flex flex-col gap-3">{children}</div>
    </div>
  );
}

function ElegirZonas({
  zonas,
  elegidas,
  onCambiar,
  onListo,
}: {
  zonas: string[];
  elegidas: string[];
  onCambiar: (z: string[]) => void;
  onListo: () => void;
}) {
  function alternar(z: string) {
    onCambiar(elegidas.includes(z) ? elegidas.filter((x) => x !== z) : [...elegidas, z]);
  }
  return (
    <>
      <p className="text-sm text-gray-700">Elige tus zonas. Los paquetes "Fuera de zona" los ven todos.</p>
      {zonas.length === 0 ? (
        <p className="text-sm text-gray-500">No hay zonas configuradas.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {zonas.map((z) => {
            const activa = elegidas.includes(z);
            return (
              <button
                key={z}
                type="button"
                aria-pressed={activa}
                onClick={() => alternar(z)}
                className={`px-3 py-2 rounded-lg border text-sm font-medium ${
                  activa ? "bg-primary text-white border-primary" : "bg-white text-gray-700 border-gray-300"
                }`}
              >
                {z}
              </button>
            );
          })}
        </div>
      )}
      <button
        type="button"
        disabled={elegidas.length === 0}
        onClick={onListo}
        className="w-full bg-primary hover:bg-primary-hover text-white font-medium py-3 rounded-lg disabled:opacity-40"
      >
        Ver paquetes ({elegidas.length} zona{elegidas.length === 1 ? "" : "s"})
      </button>
    </>
  );
}

function PaquetesEnVivo({
  token,
  zonas,
  onInvalido,
  onCambiarZonas,
}: {
  token: string;
  zonas: string[];
  onInvalido: () => void;
  onCambiarZonas: () => void;
}) {
  const [paquetes, setPaquetes] = useState<PaqueteVista[]>([]);
  const [sinConexion, setSinConexion] = useState(false);
  const [nuevoId, setNuevoId] = useState<number | null>(null);
  const desdeRef = useRef(0);

  useEffect(() => {
    let vigente = true;
    let t: ReturnType<typeof setTimeout>;
    desdeRef.current = 0;
    setPaquetes([]);
    let primera = true;

    async function consultar() {
      try {
        const { data } = await vistaZonasApi.paquetes(token, zonas, desdeRef.current);
        if (!vigente) return;
        setSinConexion(false);
        desdeRef.current = data.ultimo_id;
        if (data.paquetes.length > 0) {
          const nuevos = [...data.paquetes].reverse();
          setPaquetes((prev) => [...nuevos, ...prev]);
          if (!primera) {
            setNuevoId(nuevos[0].id);
            if (navigator.vibrate) navigator.vibrate(150);
          }
        }
        primera = false;
      } catch (e) {
        if (!vigente) return;
        if (esEnlaceInvalido(e)) return onInvalido();
        setSinConexion(true);
      }
      if (vigente) t = setTimeout(consultar, CADA_MS);
    }
    consultar();
    return () => {
      vigente = false;
      clearTimeout(t);
    };
    // zonas.join: el arreglo cambia de identidad en cada render del padre
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, zonas.join(",")]);

  const fuera = paquetes.filter((p) => p.fuera_de_zona).length;

  return (
    <>
      <div className="flex items-center gap-3">
        <div className="shrink-0 w-16 h-16 rounded-xl bg-primary/10 text-primary flex flex-col items-center justify-center">
          <span className="text-2xl font-bold leading-none">{paquetes.length}</span>
          <span className="text-[10px] uppercase mt-1">paquetes</span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-gray-900 truncate">Zonas: {zonas.join(", ")}</p>
          <p className="text-xs text-gray-500">
            {fuera > 0 ? `${fuera} fuera de zona · ` : ""}se actualiza solo
          </p>
        </div>
        <button type="button" onClick={onCambiarZonas} className="shrink-0 text-sm text-primary font-medium hover:underline">
          Cambiar
        </button>
      </div>

      {sinConexion && (
        <p role="alert" className="rounded-lg px-3 py-2 bg-amber-100 text-amber-900 text-sm">
          Sin conexión con el servidor, reintentando…
        </p>
      )}

      {paquetes.length === 0 ? (
        <p className="text-center text-gray-500 py-12">Esperando paquetes de tus zonas…</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {paquetes.map((p) => (
            <li
              key={p.id}
              className={`rounded-xl border-2 p-3 bg-white ${
                p.fuera_de_zona ? "border-amber-300 bg-amber-50" : p.id === nuevoId ? "border-green-400" : "border-gray-200"
              }`}
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-3xl font-bold tracking-wider text-gray-900">{p.ultimos_4}</span>
                <span className={`text-sm font-semibold ${p.fuera_de_zona ? "text-amber-800" : "text-primary"}`}>
                  {p.fuera_de_zona ? p.aviso ?? "Fuera de zona" : p.zona}
                </span>
              </div>
              {p.direccion && (
                <p className="text-sm text-gray-700 mt-1 flex items-start gap-1">
                  <MapPin size={14} className="shrink-0 mt-0.5" /> {p.direccion}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
