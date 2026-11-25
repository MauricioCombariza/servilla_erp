import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { Copy, Check } from "lucide-react";
import { authApi, type LoginResponse, type MfaPendiente, type MfaQrNuevo } from "@/api/auth";

/** Mensaje del servidor (detail) o uno genérico. */
function mensaje(e: unknown, generico: string): { texto: string; vencido: boolean } {
  const r = (e as { response?: { status?: number; data?: { detail?: unknown } } }).response;
  const detalle = typeof r?.data?.detail === "string" ? r.data.detail : "";
  if (!r) return { texto: "Sin conexión. Intenta de nuevo.", vencido: false };
  return { texto: detalle || generico, vencido: detalle.startsWith("Se venció") };
}

const claseInput =
  "w-full border border-gray-300 rounded-lg px-3 py-2 text-lg tracking-widest text-center focus:ring-2 focus:ring-primary focus:border-primary outline-none";
const claseBoton =
  "w-full bg-primary hover:bg-primary-hover text-white font-medium py-2 rounded-lg text-sm transition-colors disabled:opacity-60";

interface PasoProps {
  pendiente: MfaPendiente;
  onListo: (d: LoginResponse) => void;
  onVolver: (aviso?: string) => void;
}

/**
 * Ya tiene el segundo factor: pide el código de la app (o uno de respaldo).
 * Con "Cambié de celular" ese mismo código, en vez de entrar, pide un QR nuevo.
 */
export function PasoCodigo({ pendiente, onListo, onVolver, onQrNuevo }: PasoProps & {
  onQrNuevo: (q: MfaQrNuevo) => void;
}) {
  const [codigo, setCodigo] = useState("");
  const [respaldo, setRespaldo] = useState(false);
  const [qrNuevo, setQrNuevo] = useState(false);
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError("");
    try {
      if (qrNuevo) onQrNuevo((await authApi.mfaReconfigurar(pendiente.mfa_token, codigo)).data);
      else onListo((await authApi.mfaVerificar(pendiente.mfa_token, codigo)).data);
    } catch (err) {
      const m = mensaje(err, "Código incorrecto");
      if (m.vencido) onVolver(m.texto);
      else setError(m.texto);
      setCodigo("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} className="space-y-4">
      <p className="text-sm text-gray-700">
        Hola, {pendiente.nombre_completo}. {qrNuevo
          ? "Para generar un QR nuevo, escribe el código de 6 dígitos que muestra la app en el celular de antes, o uno de tus códigos de respaldo."
          : respaldo
          ? "Escribe uno de tus códigos de respaldo (cada uno sirve una sola vez)."
          : "Abre la app de autenticación del celular y escribe el código de 6 dígitos de Servilla ERP."}
      </p>
      <input
        value={codigo}
        onChange={(e) => setCodigo(e.target.value)}
        inputMode={respaldo || qrNuevo ? "text" : "numeric"}
        autoComplete="one-time-code"
        autoCapitalize="characters"
        maxLength={respaldo || qrNuevo ? 9 : 6}
        placeholder={qrNuevo ? "123456 o ABCD-EFGH" : respaldo ? "ABCD-EFGH" : "123456"}
        className={claseInput}
        autoFocus
      />
      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      <button type="submit" disabled={enviando || codigo.trim().length < 6} className={claseBoton}>
        {enviando ? "Verificando..." : qrNuevo ? "Generar QR nuevo" : "Ingresar"}
      </button>
      <div className="flex justify-between text-xs">
        {qrNuevo ? (
          <button type="button" onClick={() => { setQrNuevo(false); setCodigo(""); setError(""); }}
                  className="text-primary hover:underline">
            Solo quiero ingresar
          </button>
        ) : (
          <button type="button" onClick={() => { setRespaldo(!respaldo); setCodigo(""); setError(""); }}
                  className="text-primary hover:underline">
            {respaldo ? "Usar el código de la app" : "No tengo el celular"}
          </button>
        )}
        <button type="button" onClick={() => onVolver()} className="text-gray-500 hover:underline">
          Volver
        </button>
      </div>
      {!qrNuevo && (
        <button type="button" onClick={() => { setQrNuevo(true); setRespaldo(false); setCodigo(""); setError(""); }}
                className="w-full text-xs text-primary hover:underline">
          Cambié de celular: generar QR nuevo
        </button>
      )}
      {respaldo && !qrNuevo && (
        <p className="text-xs text-gray-500">
          Si tampoco tienes los códigos de respaldo, pide al administrador que reinicie tu segundo factor.
        </p>
      )}
    </form>
  );
}

/** Primer ingreso con segundo factor: QR para la app y confirmación con el primer código. */
export function PasoConfigurar({ pendiente, onListo, onVolver }: PasoProps) {
  const token = pendiente.mfa_token;
  const preparar = useCallback(async () => (await authApi.mfaConfigurar(token)).data, [token]);
  const confirmar = useCallback(async (c: string) => (await authApi.mfaActivar(token, c)).data, [token]);
  return <VistaQr preparar={preparar} confirmar={confirmar} onListo={onListo} onVolver={onVolver} />;
}

/** Cambio de celular: el QR ya viene generado; al confirmar reemplaza al anterior. */
export function PasoQrNuevo({ qr, onListo, onVolver }: {
  qr: MfaQrNuevo;
  onListo: (d: LoginResponse) => void;
  onVolver: (aviso?: string) => void;
}) {
  const preparar = useCallback(async () => qr, [qr]);
  const confirmar = useCallback(
    async (c: string) => (await authApi.mfaReactivar(qr.mfa_token, c)).data, [qr]);
  return (
    <VistaQr preparar={preparar} confirmar={confirmar} onListo={onListo} onVolver={onVolver}
             titulo="Código QR nuevo para tu celular"
             aviso="Al confirmar, el código del celular anterior deja de servir y tus códigos de respaldo cambian." />
  );
}

function VistaQr({ preparar, confirmar, onListo, onVolver, titulo, aviso }: {
  preparar: () => Promise<{ secreto: string; uri: string }>;
  confirmar: (codigo: string) => Promise<LoginResponse>;
  onListo: (d: LoginResponse) => void;
  onVolver: (aviso?: string) => void;
  titulo?: string;
  aviso?: string;
}) {
  const [qr, setQr] = useState("");
  const [secreto, setSecreto] = useState("");
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    let vivo = true;
    preparar()
      .then(async (data) => {
        const imagen = await QRCode.toDataURL(data.uri, { width: 220, margin: 1 });
        if (vivo) { setQr(imagen); setSecreto(data.secreto); }
      })
      .catch((err) => {
        const m = mensaje(err, "No se pudo preparar el código QR");
        if (m.vencido) onVolver(m.texto);
        else if (vivo) setError(m.texto);
      });
    return () => { vivo = false; };
  }, [preparar, onVolver]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError("");
    try {
      onListo(await confirmar(codigo));
    } catch (err) {
      const m = mensaje(err, "El código no coincide");
      if (m.vencido) onVolver(m.texto);
      else setError(m.texto);
      setCodigo("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} className="space-y-4">
      <div className="text-sm text-gray-700 space-y-2">
        <p className="font-medium">{titulo ?? "Configura el código del celular (una sola vez)"}</p>
        <ol className="list-decimal pl-5 space-y-1 text-gray-600">
          <li>Instala <strong>Google Authenticator</strong> o <strong>Microsoft Authenticator</strong> en tu celular.</li>
          <li>En la app toca <strong>+</strong> y escanea este código.</li>
          <li>Escribe abajo el número de 6 dígitos que aparece.</li>
        </ol>
        {aviso && <p className="text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">{aviso}</p>}
      </div>
      <div className="flex justify-center min-h-[220px] items-center">
        {qr ? <img src={qr} alt="Código QR para la app de autenticación" className="w-[220px] h-[220px]" />
            : <span className="text-sm text-gray-400">Preparando…</span>}
      </div>
      {secreto && (
        <div className="text-xs text-gray-500">
          ¿No puedes escanear? Escribe esta clave en la app:
          <div className="mt-1 flex items-center gap-2">
            <code className="flex-1 break-all bg-gray-50 rounded px-2 py-1 font-mono text-gray-800">
              {secreto.match(/.{1,4}/g)?.join(" ")}
            </code>
            <button type="button" title="Copiar"
                    onClick={() => { void navigator.clipboard?.writeText(secreto); setCopiado(true); }}
                    className="text-gray-500 hover:text-primary">
              {copiado ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
        </div>
      )}
      <input
        value={codigo}
        onChange={(e) => setCodigo(e.target.value)}
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        placeholder="123456"
        className={claseInput}
      />
      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      <button type="submit" disabled={enviando || !secreto || codigo.trim().length < 6} className={claseBoton}>
        {enviando ? "Verificando..." : "Confirmar"}
      </button>
      <button type="button" onClick={() => onVolver()} className="w-full text-xs text-gray-500 hover:underline">
        Volver
      </button>
    </form>
  );
}

/** Se muestran una sola vez al terminar la configuración. */
export function PasoCodigosRespaldo({ codigos, onSeguir }: { codigos: string[]; onSeguir: () => void }) {
  const [guardados, setGuardados] = useState(false);
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-700">
        <strong>Listo.</strong> Guarda estos códigos de respaldo en un lugar seguro (por ejemplo, anotados en
        papel). Sirven para entrar si pierdes el celular; cada uno se usa una sola vez y
        <strong> no se vuelven a mostrar</strong>.
      </p>
      <div className="grid grid-cols-2 gap-2 bg-gray-50 rounded-lg p-3 font-mono text-sm text-gray-800 text-center">
        {codigos.map((c) => <span key={c}>{c}</span>)}
      </div>
      <button type="button" onClick={() => void navigator.clipboard?.writeText(codigos.join("\n"))}
              className="w-full text-xs text-primary hover:underline">
        Copiar los códigos
      </button>
      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input type="checkbox" checked={guardados} onChange={(e) => setGuardados(e.target.checked)} />
        Ya los guardé
      </label>
      <button type="button" disabled={!guardados} onClick={onSeguir} className={claseBoton}>
        Continuar
      </button>
    </div>
  );
}
