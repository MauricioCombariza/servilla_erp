import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Html5QrcodeSupportedFormats } from "html5-qrcode";
import { CAMARA_TRASERA, CONFIG_ESCANER, crearEscaner } from "@/utils/escanerCamara";
import { AlertTriangle, Camera, CameraOff, CloudOff, PackageOpen, QrCode, RotateCw, X } from "lucide-react";
import {
  tulasApi,
  type DestinoPaquete,
  type EscaneoResult,
  type ImileEstado,
  type Tula,
  type TulaAbierta,
  type TulaAbiertaConflicto,
  type SinLeerDelDia,
  type TulaDetalle,
} from "@/api/tulas";
import { actualizarBase, destinoLocal } from "@/offline/base";
import { useCambiosImile } from "@/offline/cambios";
import { abrirSinEtiqueta, alResultado, encolar, nuevoId, pendientesEnCola, resolverConflicto, useCola, type Op } from "@/offline/cola";
import { kvGuardar, kvLeer } from "@/offline/idb";
import { CompartirVista } from "./CompartirVista";
import { FlujoPaquetesNav } from "./FlujoPaquetesNav";
import { CerrarSesionBoton } from "./CerrarSesionBoton";

const SCANNER_ELEMENT_ID = "tulas-qr-reader";
// Largos de tulas.codigo y tula_seriales.serial (flujo/internal/tulas: MaxCodigo, MaxSerial)
const MAX_CODIGO_TULA = 255;
const MAX_SERIAL = 50;
const SCAN_FORMATS = [
  Html5QrcodeSupportedFormats.QR_CODE,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.CODE_39,
  Html5QrcodeSupportedFormats.CODE_93,
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.ITF,
];
const ANTIRREBOTE_MS = 2000; // la cámara lee el mismo código varias veces por segundo
const BASE_CADA_MS = 5 * 60_000; // la base del celular se revisa cada 5 min (304 si no cambió)
const CLAVE_PANTALLA = "pantalla_tulas";

/** Lo que se está leyendo: el código de una tula, o los paquetes de la tula abierta. */
type Modo = "tula" | "paquetes";

/** La tula en el celular: sin id mientras el servidor no confirme que la abrió. */
type TulaLocal = Omit<Tula, "id"> & { id: number | null; local_id: string };

type Lectura = {
  serial: string;
  // en_cola: guardada en el celular, falta que llegue al servidor
  envio: "en_cola" | "listo" | "falla";
  zona: string | null;
  localidad: string | null;
  aviso: string | null;
  imile: ImileEstado;
  imileMensaje: string | null;
  error?: string;
};

type Conflicto = { codigo: string | null; abierta: TulaLocal };

type PantallaGuardada = { tula: TulaLocal | null; lecturas: Lectura[]; imileTotal: string | null };

function leerDetalle(e: unknown): unknown {
  return (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
}

function detalleDe(body: unknown): unknown {
  return (body as { detail?: unknown })?.detail;
}

function vibrar(patron: number | number[]) {
  if (navigator.vibrate) navigator.vibrate(patron);
}

function conContador<T extends Pick<Tula, "total_esperado" | "leidos">>(t: T): T & Pick<Tula, "contador" | "diferencia"> {
  const diferencia = t.total_esperado == null ? null : t.total_esperado - t.leidos;
  return { ...t, contador: diferencia ?? t.leidos, diferencia };
}

function desdeServidor(t: Tula, localId?: string): TulaLocal {
  return { ...t, local_id: localId ?? nuevoId() };
}

/** A qué tula va una operación: su id si el servidor ya la confirmó, si no la del celular. */
function refTula(t: TulaLocal): Pick<Op, "tula_id" | "tula_local_id"> {
  return t.id != null ? { tula_id: t.id } : { tula_local_id: t.local_id };
}

function esDeLaTula(op: Op, t: TulaLocal | null): boolean {
  return !!t && (op.tula_local_id === t.local_id || (t.id != null && op.tula_id === t.id));
}

/**
 * Pasos 2.2, 2.4, 2.5, 2.6 y 2.8 en una sola pantalla para celular: se lee la tula y ahí
 * mismo sus paquetes. Cada paquete se cuenta, se muestra su destino y se ingresa en iMile.
 * Sirve con el lector Bluetooth (escribe en el campo y manda Enter) o con la cámara.
 * El botón del QR comparte la vista por zonas (2.7) con los demás celulares.
 *
 * Funciona sin señal: el destino sale de la base guardada en el celular y cada lectura
 * queda en la cola del celular (offline/cola.ts), que la manda sola al volver la señal.
 * El ingreso en iMile lo hace el servidor después; su resultado llega por /flujo/cambios.
 */
export function EscaneoTulasPage() {
  const [tula, setTula] = useState<TulaLocal | null>(null);
  const [modo, setModo] = useState<Modo>("tula");
  const [codigo, setCodigo] = useState("");
  const [totalEsperado, setTotalEsperado] = useState("");
  const [lecturas, setLecturas] = useState<Lectura[]>([]);
  const [ultimo, setUltimo] = useState<{ destino: DestinoPaquete; ya: boolean } | null>(null);
  const [conflicto, setConflicto] = useState<Conflicto | null>(null);
  const [confirmarCierre, setConfirmarCierre] = useState(false);
  const [cerrada, setCerrada] = useState<TulaDetalle | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Paso 2.3: lo que dijo iMile del total al abrir la tula (queda visible mientras esté abierta)
  const [imileTotal, setImileTotal] = useState<string | null>(null);
  const [camara, setCamara] = useState(false);
  const [compartir, setCompartir] = useState(false); // Paso 2.7: QR de la vista por zonas
  const [verSinLeer, setVerSinLeer] = useState(false);
  // Se recargó con lecturas sin mandar: manda lo guardado en el celular, no el servidor
  const [fuenteLocal, setFuenteLocal] = useState<boolean | null>(null);
  const campoRef = useRef<HTMLInputElement>(null);
  const ultimaLecturaRef = useRef({ codigo: "", at: 0 });
  const tulaRef = useRef(tula);
  tulaRef.current = tula;
  // La tula cuyo cierre se está esperando (su resumen solo se muestra si sigue en pantalla)
  const cierreRef = useRef<TulaLocal | null>(null);
  const queryClient = useQueryClient();
  const cola = useCola();

  // La base del día en el celular: al entrar y cada 5 min
  useEffect(() => {
    void actualizarBase();
    const t = setInterval(() => void actualizarBase(), BASE_CADA_MS);
    return () => clearInterval(t);
  }, []);

  // Lo guardado en el celular (si quedó algo sin mandar, o no hay señal, manda eso)
  useEffect(() => {
    void (async () => {
      const guardada = await kvLeer<PantallaGuardada>(CLAVE_PANTALLA);
      const pendientes = await pendientesEnCola();
      if (guardada?.tula && (pendientes.length > 0 || !navigator.onLine)) {
        setTula(guardada.tula);
        setLecturas(guardada.lecturas);
        setImileTotal(guardada.imileTotal);
        setModo("paquetes");
        setFuenteLocal(true);
      } else {
        setFuenteLocal(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (fuenteLocal === null) return;
    void kvGuardar(CLAVE_PANTALLA, { tula, lecturas, imileTotal } satisfies PantallaGuardada);
  }, [tula, lecturas, imileTotal, fuenteLocal]);

  // Con todo enviado, al entrar (o recargar) se retoma la tula abierta del servidor
  const abiertaQuery = useQuery({
    queryKey: ["tula-abierta"],
    queryFn: async () => {
      const abierta = (await tulasApi.abierta()).data;
      return abierta ? (await tulasApi.detalle(abierta.id)).data : null;
    },
    enabled: fuenteLocal === false,
    refetchOnWindowFocus: false,
  });

  // Sin la base de despacho de hoy, todo saldría "No está en la tabla" y sin zona
  const baseQuery = useQuery({
    queryKey: ["tulas-base-del-dia"],
    queryFn: () => tulasApi.baseDelDia().then((r) => r.data),
  });
  const sinBase = baseQuery.data?.paquetes_hoy === 0;

  // Tulas y paquetes leídos hoy entre todos (otros también escanean: se refresca solo)
  const delDiaQuery = useQuery({
    queryKey: ["tulas-del-dia"],
    queryFn: () => tulasApi.delDia().then((r) => r.data),
    refetchInterval: 15000,
  });
  // Paquetes de la base del día que todavía no han pasado por ninguna tula
  const sinLeerQuery = useQuery({
    queryKey: ["tulas-sin-leer"],
    queryFn: () => tulasApi.sinLeer().then((r) => r.data),
    refetchInterval: 15000,
  });
  const refrescarDelDia = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["tulas-del-dia"] });
    void queryClient.invalidateQueries({ queryKey: ["tulas-sin-leer"] });
  }, [queryClient]);
  const sinLeer = sinLeerQuery.data;

  useEffect(() => {
    if (!abiertaQuery.isSuccess) return;
    const d = abiertaQuery.data;
    if (!d) {
      setTula(null);
      setLecturas([]);
      return;
    }
    setTula((t) => desdeServidor(d, t?.id === d.id ? t.local_id : undefined));
    setModo("paquetes");
    setLecturas(
      [...d.seriales].reverse().map((s) => ({
        serial: s.serial,
        envio: "listo",
        zona: s.zona,
        localidad: s.localidad,
        aviso: s.en_tabla ? (s.zona ? null : "Fuera de zona") : "No está en la tabla",
        imile: s.imile_estado,
        imileMensaje: s.imile_mensaje,
      })),
    );
  }, [abiertaQuery.isSuccess, abiertaQuery.data]);

  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), 4000);
    return () => clearTimeout(t);
  }, [aviso]);

  function enfocar() {
    setTimeout(() => campoRef.current?.focus(), 0);
  }

  function actualizarLectura(serial: string, cambios: Partial<Lectura>) {
    setLecturas((ls) => ls.map((l) => (l.serial === serial ? { ...l, ...cambios } : l)));
  }

  // ---------- Respuestas del servidor (llegan cuando hay señal) ----------

  useEffect(() => alResultado((op, r) => {
    const actual = tulaRef.current;
    const ok = r.status >= 200 && r.status < 300;
    switch (op.tipo) {
      case "abrir_tula": {
        if (!ok) {
          if (r.status !== 409) setAviso(String(detalleDe(r.body) ?? "No se pudo abrir la tula"));
          return;
        }
        const t = r.body as TulaAbierta;
        if (op.tula_local_id !== actual?.local_id) return;
        setTula((x) => x && conContador({ ...x, ...t, id: t.id, local_id: x.local_id, leidos: Math.max(x.leidos, t.leidos) }));
        setImileTotal(t.imile_total);
        refrescarDelDia();
        return;
      }
      case "serial": {
        if (!esDeLaTula(op, actual)) return;
        const serial = String(op.datos?.serial ?? "");
        if (!ok) {
          actualizarLectura(serial, { envio: "falla", error: String(detalleDe(r.body) ?? "No se pudo registrar") });
          vibrar([50, 50, 50]);
          return;
        }
        const e = r.body as EscaneoResult;
        actualizarLectura(serial, {
          envio: "listo", zona: e.destino.zona, localidad: e.destino.localidad, aviso: e.destino.aviso,
          imile: e.imile.estado, imileMensaje: e.imile.mensaje,
        });
        // El servidor confirma el destino (p. ej. un paquete de días atrás que no estaba en el celular)
        setUltimo((u) => (u && u.destino.serial === e.destino.serial ? { ...u, destino: e.destino } : u));
        setTula((x) => x && conContador({ ...x, id: e.tula.id, total_esperado: e.tula.total_esperado, leidos: Math.max(x.leidos, e.tula.leidos) }));
        if (!e.ya_escaneado) refrescarDelDia();
        return;
      }
      case "total":
        if (!ok) setAviso("No se pudo guardar el total");
        return;
      case "cerrar_tula":
        if (!esDeLaTula(op, cierreRef.current)) return;
        if (ok) {
          setCerrada(r.body as TulaDetalle);
          refrescarDelDia();
        } else {
          setAviso(String(detalleDe(r.body) ?? "No se pudo cerrar la tula"));
        }
        return;
    }
  }), [refrescarDelDia]);

  // Estado de iMile de cada paquete (lo hace el servidor en segundo plano)
  useCambiosImile(tula?.id != null, (cambios) => {
    const id = tulaRef.current?.id;
    for (const c of cambios) {
      if (c.tula_id === id) actualizarLectura(c.serial, { imile: c.imile_estado, imileMensaje: c.imile_mensaje });
    }
  });

  // ---------- Tula ----------

  function abrirTula(cod: string | null, cerrarAnterior = false) {
    // Ya hay una abierta en el celular: se pregunta aquí mismo, sin ir al servidor
    if (tula && !cerrarAnterior) {
      if (cod !== null && cod === tula.codigo) {
        setModo("paquetes");
        enfocar();
        return;
      }
      setConflicto({ codigo: cod, abierta: tula });
      return;
    }
    const total = totalEsperado.trim() === "" ? null : Number(totalEsperado);
    const nueva: TulaLocal = conContador({
      id: null, local_id: nuevoId(), codigo: cod, sin_etiqueta: cod === null, total_esperado: total,
      estado: "abierta", usuario: "", fecha: new Date().toISOString().slice(0, 10),
      fecha_apertura: new Date().toISOString(), fecha_cierre: null, leidos: 0, contador: 0, diferencia: null,
    });
    void encolar({
      tipo: "abrir_tula", tula_local_id: nueva.local_id,
      datos: { codigo: cod, total_esperado: total, cerrar_anterior: cerrarAnterior },
    });
    setTula(nueva);
    setImileTotal(cod !== null && total === null ? "Consultando en iMile cuántos paquetes trae…" : null);
    setModo("paquetes");
    setLecturas([]);
    setUltimo(null);
    setConflicto(null);
    setCerrada(null);
    cierreRef.current = null;
    setTotalEsperado("");
    vibrar(80);
    enfocar();
  }

  function guardarTotal(total: number) {
    if (!tula) return;
    void encolar({ tipo: "total", ...refTula(tula), datos: { total_esperado: total } });
    setTula(conContador({ ...tula, total_esperado: total }));
    setImileTotal(null);
    enfocar();
  }

  function cerrarTula() {
    if (!tula) return;
    void encolar({ tipo: "cerrar_tula", ...refTula(tula) });
    cierreRef.current = tula;
    // Mientras llega la respuesta del servidor (con faltantes según iMile) se muestra lo del celular
    setCerrada({ ...tula, id: tula.id ?? 0, estado: "cerrada", seriales: [], faltantes: null, no_esperados: null });
    setTula(null);
    setImileTotal(null);
    setModo("tula");
    setLecturas([]);
    setUltimo(null);
    setConfirmarCierre(false);
    enfocar();
  }

  // ---------- Paquetes ----------

  function leerPaquete(serial: string, reenviar = false) {
    if (!tula) return;
    const previa = lecturas.find((l) => l.serial === serial);
    const destino = destinoLocal(serial) ?? {
      serial, ultimos_4: serial.slice(-4), en_tabla: false, direccion: null, direccion_estandarizada: null,
      localidad: null, zona: null, fuera_de_zona: false, aviso: "Sin la base en el celular: se confirma al enviar",
    };
    setUltimo({ destino, ya: !!previa && !reenviar });
    if (previa && !reenviar && previa.envio !== "falla") {
      // Ya leído en esta tula: no se cuenta ni se manda otra vez
      setLecturas((ls) => [previa, ...ls.filter((l) => l.serial !== serial)]);
      vibrar([40, 60, 40]);
      return;
    }
    const fila: Lectura = {
      serial, envio: "en_cola", zona: destino.zona, localidad: destino.localidad, aviso: destino.aviso,
      imile: null, imileMensaje: null,
    };
    setLecturas((ls) => [fila, ...ls.filter((l) => l.serial !== serial)]);
    if (!previa) setTula(conContador({ ...tula, leidos: tula.leidos + 1 }));
    void encolar({ tipo: "serial", ...refTula(tula), datos: { serial } });
    vibrar(80);
  }

  async function reintentarImile(serial: string) {
    if (tula?.id == null) return;
    actualizarLectura(serial, { imile: "pendiente", imileMensaje: "Reintentando…" });
    try {
      const r = (await tulasApi.reintentarImile(tula.id, serial)).data;
      actualizarLectura(serial, { imile: r.imile_estado, imileMensaje: r.imile_mensaje });
    } catch (e) {
      const sinRespuesta = !(e as { response?: unknown })?.response;
      actualizarLectura(serial, { imile: "error", imileMensaje: sinRespuesta ? "Sin señal: inténtalo otra vez" : String(leerDetalle(e) ?? "No se pudo reintentar") });
    }
  }

  // Al abrir una tula sin señal había otra abierta en el servidor (p. ej. desde otro celular)
  const choque = cola.bloqueo?.op.tipo === "abrir_tula" && cola.bloqueo.status === 409
    ? (cola.bloqueo.detalle as TulaAbiertaConflicto | undefined)
    : undefined;
  // El servidor no aceptó el código de la tula (422): lo leído espera a que se abra sin etiqueta
  const rechazo = cola.bloqueo?.op.tipo === "abrir_tula" && cola.bloqueo.status === 422 ? cola.bloqueo : null;

  function seguirSinEtiqueta() {
    if (!rechazo) return;
    if (tula?.local_id === rechazo.op.tula_local_id) {
      setTula((x) => x && conContador({ ...x, codigo: null, sin_etiqueta: true }));
      setImileTotal(null);
    }
    void abrirSinEtiqueta();
    enfocar();
  }

  function resolverChoque(decision: "cerrar" | "seguir") {
    if (!choque) return;
    if (decision === "seguir") {
      // Lo leído pasa a la tula que ya estaba abierta
      setTula((x) => conContador({ ...desdeServidor(choque.tula_abierta), leidos: choque.tula_abierta.leidos + (x?.leidos ?? 0) }));
      setImileTotal(null);
    }
    void resolverConflicto(decision, choque.tula_abierta.id);
    enfocar();
  }

  // ---------- Entrada: lector Bluetooth, teclado o cámara ----------

  function recibirCodigo(raw: string) {
    const cod = raw.trim();
    if (!cod || conflicto) return;
    const ahora = Date.now();
    if (ultimaLecturaRef.current.codigo === cod && ahora - ultimaLecturaRef.current.at < ANTIRREBOTE_MS) return;
    ultimaLecturaRef.current = { codigo: cod, at: ahora };

    // Lo que no cabe en la base (se leyó otra cosa, p. ej. un QR) se avisa aquí mismo
    if (modo === "tula" && cod.length > MAX_CODIGO_TULA) {
      setAviso("Eso no parece el código de una tula");
      vibrar([50, 50, 50]);
      return;
    }
    if (modo === "paquetes" && cod.length > MAX_SERIAL) {
      setAviso("Eso no parece el código de un paquete");
      vibrar([50, 50, 50]);
      return;
    }

    if (modo === "tula") abrirTula(cod);
    else leerPaquete(cod);
  }

  // La cámara llama siempre a la versión más reciente (con el modo y la tula actuales)
  const recibirRef = useRef(recibirCodigo);
  recibirRef.current = recibirCodigo;

  useEffect(() => {
    if (!camara) return;
    const scanner = crearEscaner(SCANNER_ELEMENT_ID, SCAN_FORMATS);
    scanner
      .start(
        CAMARA_TRASERA,
        CONFIG_ESCANER,
        (texto) => recibirRef.current(texto),
        () => {},
      )
      .catch(() => {
        setAviso("No se pudo abrir la cámara");
        setCamara(false);
      });
    return () => {
      scanner.stop().then(() => scanner.clear()).catch(() => {});
    };
  }, [camara]);

  function enviarCampo(e: React.FormEvent) {
    e.preventDefault();
    recibirCodigo(codigo);
    setCodigo("");
  }

  const enCola = lecturas.filter((l) => l.envio === "en_cola").length;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3">
        <Contador tula={tula} />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 truncate">
            {tula ? (tula.sin_etiqueta ? "Tula sin etiqueta" : `Tula ${tula.codigo}`) : "Escaneo de tulas"}
          </p>
          <p className="text-xs text-gray-500">
            {tula
              ? `${tula.leidos} leído${tula.leidos === 1 ? "" : "s"}${tula.total_esperado != null ? ` de ${tula.total_esperado}` : ""}${enCola ? ` · ${enCola} por enviar` : ""}`
              : "Lee el código de la tula para empezar"}
          </p>
        </div>
        {tula && modo === "paquetes" && (
          <button
            type="button"
            onClick={() => { setModo("tula"); enfocar(); }}
            className="shrink-0 text-sm text-primary font-medium hover:underline"
          >
            Nueva tula
          </button>
        )}
        <button
          type="button"
          onClick={() => setCompartir(true)}
          aria-label="Compartir vista por zonas (QR)"
          title="Compartir vista por zonas (QR)"
          className="shrink-0 text-gray-600 hover:text-primary p-1"
        >
          <QrCode size={24} />
        </button>
        <CerrarSesionBoton />
      </header>

      {delDiaQuery.data && (
        <div className="bg-white border-b border-gray-200 px-4 py-1.5 text-sm text-gray-600 text-center">
          Hoy: <span className="font-semibold text-gray-900">{delDiaQuery.data.tulas}</span>{" "}
          tula{delDiaQuery.data.tulas === 1 ? "" : "s"} ·{" "}
          <span className="font-semibold text-gray-900">{delDiaQuery.data.paquetes}</span>{" "}
          paquete{delDiaQuery.data.paquetes === 1 ? "" : "s"} leído{delDiaQuery.data.paquetes === 1 ? "" : "s"}
          {sinLeer && sinLeer.total > 0 && (
            <>
              {" · "}
              <button
                type="button"
                onClick={() => setVerSinLeer((v) => !v)}
                aria-expanded={verSinLeer}
                className="font-semibold text-amber-700 underline"
              >
                {sinLeer.total} serial{sinLeer.total === 1 ? "" : "es"} sin leer
              </button>
            </>
          )}
          {sinLeer && sinLeer.total === 0 && !sinBase && delDiaQuery.data.paquetes > 0 && (
            <span className="text-green-700"> · Base completa ✓</span>
          )}
        </div>
      )}

      <div className="bg-white border-b border-gray-200 px-4 py-2">
        <FlujoPaquetesNav className="max-w-md mx-auto" />
      </div>

      {verSinLeer && sinLeer && sinLeer.total > 0 && (
        <SinLeer datos={sinLeer} onCerrar={() => { setVerSinLeer(false); enfocar(); }} />
      )}

      {compartir && <CompartirVista onCerrar={() => { setCompartir(false); enfocar(); }} />}

      <div className="p-4 flex flex-col gap-3 flex-1 w-full max-w-md mx-auto">
        {sinBase && (
          <div role="alert" className="rounded-lg px-4 py-3 bg-amber-100 text-amber-900 flex items-start gap-2 text-sm">
            <AlertTriangle size={18} className="shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">No se ha subido la base de despacho de hoy</p>
              <p>
                Súbela antes de escanear: sin ella los paquetes salen "No está en la tabla" y sin zona.
              </p>
              <Link to="/subir-despacho" className="inline-block mt-1 font-medium underline">
                Subir base de despacho
              </Link>
            </div>
          </div>
        )}

        {/* Qué se va a leer ahora */}
        <div
          className={`rounded-lg px-4 py-2 text-sm font-medium text-center ${
            modo === "tula" ? "bg-amber-100 text-amber-900" : "bg-primary/10 text-primary"
          }`}
        >
          {modo === "tula" ? "Lee el código de la TULA" : "Lee los PAQUETES de la tula"}
        </div>

        {modo === "tula" && (
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
            <label className="block text-sm text-gray-700" htmlFor="total">
              Paquetes que trae <span className="text-gray-400">(vacío: se consulta en iMile)</span>
            </label>
            <input
              id="total"
              type="number"
              inputMode="numeric"
              min={0}
              value={totalEsperado}
              onChange={(e) => setTotalEsperado(e.target.value)}
              placeholder="Ej. 25"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-base outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              type="button"
              onClick={() => abrirTula(null)}
              className="w-full border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-40"
            >
              Tula sin etiqueta
            </button>
            {tula && (
              <button
                type="button"
                onClick={() => { setModo("paquetes"); enfocar(); }}
                className="w-full text-sm text-gray-500 hover:underline"
              >
                Volver a la tula abierta
              </button>
            )}
          </div>
        )}

        <form onSubmit={enviarCampo} className="flex gap-2">
          <input
            ref={campoRef}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            autoFocus
            autoComplete="off"
            placeholder={modo === "tula" ? "Código de la tula" : "Serial del paquete"}
            className="min-w-0 flex-1 border border-gray-300 rounded-lg px-3 py-3 text-base font-mono outline-none focus:ring-2 focus:ring-primary"
          />
          <button
            type="submit"
            disabled={!codigo.trim()}
            className="shrink-0 bg-gray-800 hover:bg-gray-900 text-white font-medium px-4 rounded-lg text-sm disabled:opacity-40"
          >
            {modo === "tula" ? "Abrir" : "Leer"}
          </button>
          <button
            type="button"
            onClick={() => setCamara((c) => !c)}
            aria-label={camara ? "Apagar cámara" : "Usar cámara"}
            className="shrink-0 border border-gray-300 rounded-lg px-3 text-gray-700 hover:bg-gray-50"
          >
            {camara ? <CameraOff size={20} /> : <Camera size={20} />}
          </button>
        </form>

        {camara && <div id={SCANNER_ELEMENT_ID} className="w-full rounded-xl overflow-hidden bg-black" />}

        {tula && modo === "paquetes" && imileTotal && (
          <div
            className={`rounded-lg px-4 py-2.5 text-sm ${
              tula.total_esperado != null ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-900"
            }`}
          >
            {imileTotal}
          </div>
        )}

        {tula && modo === "paquetes" && !tula.sin_etiqueta && tula.total_esperado == null && (
          <TotalAMano onGuardar={guardarTotal} />
        )}

        <EstadoConexion pendientes={cola.pendientes} sinSenal={cola.sinSenal} enviando={cola.enviando} />

        {choque && (
          <div role="alert" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
            <p className="font-medium text-amber-900">
              En el servidor ya estaba abierta la{" "}
              {choque.tula_abierta.sin_etiqueta ? "tula sin etiqueta" : `tula ${choque.tula_abierta.codigo}`} con{" "}
              {choque.tula_abierta.leidos} paquete{choque.tula_abierta.leidos === 1 ? "" : "s"} (quizá desde otro celular).
            </p>
            <p className="text-amber-800 mt-1">Lo que leíste sigue guardado. ¿Qué hago?</p>
            <div className="flex flex-col gap-2 mt-3">
              <button
                type="button"
                onClick={() => resolverChoque("cerrar")}
                className="bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-lg"
              >
                Cerrar esa y seguir en la nueva
              </button>
              <button
                type="button"
                onClick={() => resolverChoque("seguir")}
                className="border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg bg-white"
              >
                Pasar lo leído a la que estaba abierta
              </button>
            </div>
          </div>
        )}

        {rechazo && (
          <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm">
            <p className="font-medium text-red-900">
              No se pudo abrir la tula {String(rechazo.op.datos?.codigo ?? "").slice(0, 30)}
              {String(rechazo.op.datos?.codigo ?? "").length > 30 ? "…" : ""}:{" "}
              {typeof rechazo.detalle === "string" ? rechazo.detalle : "el código no sirve"}.
            </p>
            <p className="text-red-800 mt-1">
              Lo que leíste sigue guardado, pero no llega al servidor hasta que se abra la tula.
            </p>
            <button
              type="button"
              onClick={seguirSinEtiqueta}
              className="w-full mt-3 bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-lg"
            >
              Abrir como tula sin etiqueta
            </button>
          </div>
        )}

        {aviso && (
          <div role="alert" className="rounded-lg px-4 py-2.5 text-sm font-medium text-center bg-red-100 text-red-800">
            {aviso}
          </div>
        )}

        {conflicto && (
          <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
            <p className="font-medium text-amber-900">
              Tienes abierta la {conflicto.abierta.sin_etiqueta ? "tula sin etiqueta" : `tula ${conflicto.abierta.codigo}`}{" "}
              con {conflicto.abierta.leidos} paquete{conflicto.abierta.leidos === 1 ? "" : "s"}.
            </p>
            <p className="text-amber-800 mt-1">¿La cierro y abro la {conflicto.codigo ? `tula ${conflicto.codigo}` : "tula sin etiqueta"}?</p>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={() => abrirTula(conflicto.codigo, true)}
                className="flex-1 bg-primary hover:bg-primary-hover text-white font-medium py-2.5 rounded-lg disabled:opacity-40"
              >
                Sí, cerrar y abrir
              </button>
              <button
                type="button"
                onClick={() => { setConflicto(null); enfocar(); }}
                className="flex-1 border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg bg-white"
              >
                No
              </button>
            </div>
          </div>
        )}

        {cerrada && <ResumenCierre tula={cerrada} />}

        {modo === "paquetes" && ultimo && <Destino destino={ultimo.destino} ya={ultimo.ya} />}

        {tula && lecturas.length > 0 && (
          <ul className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
            {lecturas.map((l) => (
              <FilaLectura
                key={l.serial}
                lectura={l}
                onReenviar={() => leerPaquete(l.serial, true)}
                onReintentarImile={() => reintentarImile(l.serial)}
              />
            ))}
          </ul>
        )}

        {tula && modo === "paquetes" && (
          confirmarCierre ? (
            <div className="rounded-xl border border-gray-300 bg-white p-4 text-sm">
              <p className="font-medium text-gray-900">
                ¿Cerrar la tula con {tula.leidos} paquete{tula.leidos === 1 ? "" : "s"}?
              </p>
              <div className="flex gap-2 mt-3">
                <button
                  type="button"
                  onClick={cerrarTula}
                  className="flex-1 bg-gray-800 hover:bg-gray-900 text-white font-medium py-2.5 rounded-lg"
                >
                  Sí, cerrar
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmarCierre(false)}
                  className="flex-1 border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg"
                >
                  No
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirmarCierre(true)}
              className="w-full border border-gray-300 text-gray-700 font-medium py-2.5 rounded-lg text-sm hover:bg-gray-50 bg-white"
            >
              Cerrar tula
            </button>
          )
        )}
      </div>
    </div>
  );
}

/** Sin señal o con lecturas por enviar: que se sepa que nada se perdió. */
function EstadoConexion({ pendientes, sinSenal, enviando }: { pendientes: number; sinSenal: boolean; enviando: boolean }) {
  if (pendientes === 0 && !sinSenal) return null;
  if (sinSenal) {
    return (
      <div role="status" className="rounded-lg px-4 py-2.5 text-sm bg-gray-800 text-white flex items-center gap-2">
        <CloudOff size={18} className="shrink-0" />
        <span>
          Sin señal: puedes seguir leyendo.
          {pendientes > 0 && ` ${pendientes} lectura${pendientes === 1 ? "" : "s"} guardada${pendientes === 1 ? "" : "s"} en el celular, se envían solas al volver la señal.`}
        </span>
      </div>
    );
  }
  return (
    <div role="status" className="rounded-lg px-4 py-2 text-xs text-center bg-gray-100 text-gray-600">
      {enviando ? "Enviando" : "Por enviar"}: {pendientes}
    </div>
  );
}

/** Total escrito a mano con la tula ya abierta (cuando iMile no lo tenía). */
function TotalAMano({ onGuardar }: { onGuardar: (total: number) => void }) {
  const [valor, setValor] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valor.trim() !== "") onGuardar(Number(valor));
      }}
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2"
    >
      <label htmlFor="total-a-mano" className="text-sm text-gray-700 flex-1">
        ¿Cuántos paquetes trae?
      </label>
      <input
        id="total-a-mano"
        type="number"
        inputMode="numeric"
        min={0}
        value={valor}
        onChange={(e) => setValor(e.target.value)}
        className="w-20 border border-gray-300 rounded-lg px-2 py-1.5 text-base outline-none focus:ring-2 focus:ring-primary"
      />
      <button
        type="submit"
        disabled={valor.trim() === ""}
        className="bg-gray-800 text-white text-sm font-medium px-3 py-1.5 rounded-lg disabled:opacity-40"
      >
        Guardar
      </button>
    </form>
  );
}

/** Paso 2.4: arriba a la izquierda. Con total esperado baja (faltan / sobran); sin él sube. */
function Contador({ tula }: { tula: Pick<Tula, "total_esperado" | "contador"> | null }) {
  if (!tula) {
    return (
      <div className="shrink-0 w-16 h-16 rounded-xl bg-gray-100 flex items-center justify-center text-gray-400">
        <PackageOpen size={28} />
      </div>
    );
  }
  const conTotal = tula.total_esperado != null;
  const sobran = conTotal && tula.contador < 0;
  const completa = conTotal && tula.contador === 0;
  const color = sobran ? "bg-red-100 text-red-700" : completa ? "bg-green-100 text-green-700" : "bg-primary/10 text-primary";
  return (
    <div className={`shrink-0 w-16 h-16 rounded-xl flex flex-col items-center justify-center ${color}`}>
      <span className="text-2xl font-bold leading-none">{Math.abs(tula.contador)}</span>
      <span className="text-[10px] uppercase mt-1">{!conTotal ? "leídos" : sobran ? "sobran" : "faltan"}</span>
    </div>
  );
}

/** Paso 2.6: el destino del último paquete, grande para leerlo de un vistazo. */
function Destino({ destino, ya }: { destino: DestinoPaquete; ya: boolean }) {
  const enZona = destino.en_tabla && destino.zona;
  const fondo = !destino.en_tabla ? "border-red-300 bg-red-50" : enZona ? "border-green-300 bg-green-50" : "border-amber-300 bg-amber-50";
  return (
    <div className={`rounded-xl border-2 p-4 ${fondo}`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-4xl font-bold font-mono text-gray-900">{destino.ultimos_4}</span>
        <span className={`text-2xl font-bold ${enZona ? "text-green-800" : "text-amber-800"}`}>
          {destino.zona ?? destino.localidad ?? "—"}
        </span>
      </div>
      {destino.aviso && (
        <p className={`mt-1 font-semibold ${destino.en_tabla ? "text-amber-800" : "text-red-700"}`}>{destino.aviso}</p>
      )}
      {(destino.direccion_estandarizada || destino.direccion) && (
        <p className="mt-1 text-sm text-gray-700 break-words">{destino.direccion_estandarizada || destino.direccion}</p>
      )}
      {destino.zona && destino.localidad && <p className="text-xs text-gray-500">{destino.localidad}</p>}
      {ya && <p className="mt-2 text-sm font-medium text-amber-800">Ya estaba leído en esta tula: no se cuenta otra vez</p>}
    </div>
  );
}

const ETIQUETA_IMILE: Record<string, { texto: string; clase: string }> = {
  ok: { texto: "iMile ✓", clase: "text-green-700" },
  repetido: { texto: "iMile: ya ingresado", clase: "text-amber-700" },
  bloqueado: { texto: "iMile: bloqueado", clase: "text-red-700" },
  error: { texto: "iMile: error", clase: "text-red-700" },
  sin_confirmar: { texto: "iMile: sin confirmar", clase: "text-amber-700" },
  omitido: { texto: "iMile apagado", clase: "text-gray-400" },
  pendiente: { texto: "iMile: en cola…", clase: "text-gray-500" },
};

function FilaLectura({ lectura: l, onReenviar, onReintentarImile }: {
  lectura: Lectura; onReenviar: () => void; onReintentarImile: () => void;
}) {
  // Sin estado ni mensaje: la lectura quedó guardada pero iMile nunca contestó (p. ej. se recargó la página)
  const sinRespuesta = l.envio === "listo" && l.imile == null && !l.imileMensaje;
  const etiqueta = l.imile
    ? ETIQUETA_IMILE[l.imile] ?? { texto: `iMile: ${l.imile}`, clase: "text-red-700" }
    : sinRespuesta ? { texto: "iMile: sin respuesta", clase: "text-amber-700" } : null;
  const reintentable = sinRespuesta || l.imile === "error" || l.imile === "bloqueado" || l.imile === "sin_confirmar";
  return (
    <li className="px-4 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-gray-800">
          <span className="text-gray-400">{l.serial.slice(0, -4)}</span>
          <span className="font-bold">{l.serial.slice(-4)}</span>
        </span>
        {/* Fuera de zona: la localidad, para saber hacia dónde va */}
        <span className={`shrink-0 font-medium ${l.zona ? "text-gray-700" : "text-amber-700"}`}>
          {l.zona ?? l.localidad ?? ""}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 mt-0.5 text-xs">
        <span className={l.aviso ? "text-amber-700" : "text-gray-400"}>
          {l.envio === "falla" ? <span className="text-red-700">{l.error}</span> : l.aviso ?? ""}
        </span>
        {l.envio === "en_cola" && <span className="text-gray-500">Guardado · por enviar</span>}
        {l.envio === "falla" && (
          <button type="button" onClick={onReenviar} className="inline-flex items-center gap-1 text-primary font-medium">
            <RotateCw size={12} /> Reenviar
          </button>
        )}
        {l.envio === "listo" && etiqueta && (
          <span className="flex items-center gap-2">
            <span className={etiqueta.clase} title={l.imileMensaje ?? undefined}>{etiqueta.texto}</span>
            {reintentable && (
              <button type="button" onClick={onReintentarImile} className="inline-flex items-center gap-1 text-primary font-medium">
                <RotateCw size={12} /> Reintentar
              </button>
            )}
          </span>
        )}
        {l.envio === "listo" && !etiqueta && l.imileMensaje && <span className="text-gray-500">{l.imileMensaje}</span>}
      </div>
      {l.envio === "listo" && reintentable && l.imileMensaje && (
        <p className="text-xs text-red-700 mt-0.5 break-words">{l.imileMensaje}</p>
      )}
    </li>
  );
}

/** Paso 2.8: lo que quedó al cerrar la tula. */
function ResumenCierre({ tula }: { tula: TulaDetalle }) {
  const conTotal = tula.total_esperado != null;
  const diferencia = tula.diferencia ?? 0;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <p className="font-semibold text-gray-900">
        {tula.sin_etiqueta ? "Tula sin etiqueta" : `Tula ${tula.codigo}`} cerrada
      </p>
      <dl className="grid grid-cols-3 gap-2 mt-3 text-center">
        <div className="rounded-lg bg-gray-50 p-2">
          <dd className="text-xl font-bold">{conTotal ? tula.total_esperado : "—"}</dd>
          <dt className="text-xs text-gray-500">Esperados</dt>
        </div>
        <div className="rounded-lg bg-gray-50 p-2">
          <dd className="text-xl font-bold">{tula.leidos}</dd>
          <dt className="text-xs text-gray-500">Leídos</dt>
        </div>
        <div className={`rounded-lg p-2 ${conTotal && diferencia !== 0 ? "bg-amber-50" : "bg-gray-50"}`}>
          <dd className="text-xl font-bold">{conTotal ? Math.abs(diferencia) : "—"}</dd>
          <dt className="text-xs text-gray-500">{!conTotal ? "Diferencia" : diferencia > 0 ? "Faltan" : diferencia < 0 ? "Sobran" : "Completa"}</dt>
        </div>
      </dl>
      {tula.faltantes && tula.faltantes.length > 0 && (
        <ListaSeriales titulo={`Faltaron (${tula.faltantes.length})`} seriales={tula.faltantes} clase="text-red-700" />
      )}
      {tula.no_esperados && tula.no_esperados.length > 0 && (
        <ListaSeriales
          titulo={`Leídos que no venían en esta tula según iMile (${tula.no_esperados.length})`}
          seriales={tula.no_esperados}
          clase="text-amber-700"
        />
      )}
      {tula.faltantes && tula.faltantes.length === 0 && (
        <p className="mt-3 text-sm text-green-700">Llegaron todos los paquetes que iMile dice que trae.</p>
      )}
    </div>
  );
}

/** Lo que venía en la base de despacho del día y no se ha leído en ninguna tula. */
function SinLeer({ datos, onCerrar }: { datos: SinLeerDelDia; onCerrar: () => void }) {
  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-3">
      <div className="max-w-md mx-auto">
        <div className="flex items-center justify-between gap-2">
          <p className="font-semibold text-amber-900 text-sm">
            {datos.total} serial{datos.total === 1 ? "" : "es"} de la base sin leer
          </p>
          <button type="button" onClick={onCerrar} aria-label="Cerrar lista" className="text-amber-900 p-1">
            <X size={18} />
          </button>
        </div>
        <ul className="mt-2 max-h-72 overflow-y-auto bg-white rounded-lg border border-amber-200 divide-y divide-gray-100 text-sm">
          {datos.seriales.map((s) => (
            <li key={s.serial} className="px-3 py-1.5 flex items-center justify-between gap-2">
              <span className="font-mono truncate">
                <span className="text-gray-400">{s.serial.slice(0, -4)}</span>
                <span className="font-bold text-gray-900">{s.ultimos_4}</span>
              </span>
              <span className={`shrink-0 text-xs font-medium ${s.zona ? "text-gray-700" : "text-amber-700"}`}>
                {s.zona ?? s.localidad ?? "Sin sector"}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ListaSeriales({ titulo, seriales, clase }: { titulo: string; seriales: string[]; clase: string }) {
  return (
    <div className="mt-3">
      <p className={`text-sm font-medium ${clase}`}>{titulo}</p>
      <ul className="mt-1 grid grid-cols-2 gap-x-3 text-sm font-mono">
        {seriales.map((s) => (
          <li key={s} className="truncate">
            <span className="text-gray-400">{s.slice(0, -4)}</span>
            <span className="font-bold text-gray-900">{s.slice(-4)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
