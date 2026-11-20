import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Copy, Check } from "lucide-react";
import { authApi, type LoginResponse, type MfaPendiente } from "@/api/auth";

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

/** Ya tiene el segundo factor: pide el código de la app (o uno de respaldo). */
export function PasoCodigo({ pendiente, onListo, onVolver }: PasoProps) {
  const [codigo, setCodigo] = useState("");
  const [respaldo, setRespaldo] = useState(false);
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError("");
    try {
      onListo((await authApi.mfaVerificar(pendiente.mfa_token, codigo)).data);
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
        Hola, {pendiente.nombre_completo}. {respaldo
          ? "Escribe uno de tus códigos de respaldo (cada uno sirve una sola vez)."
          : "Abre la app de autenticación del celular y escribe el código de 6 dígitos de Servilla ERP."}
      </p>
      <input
        value={codigo}
        onChange={(e) => setCodigo(e.target.value)}
        inputMode={respaldo ? "text" : "numeric"}
        autoComplete="one-time-code"
        autoCapitalize="characters"
        maxLength={respaldo ? 9 : 6}
        placeholder={respaldo ? "ABCD-EFGH" : "123456"}
        className={claseInput}
        autoFocus
      />
      {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      <button type="submit" disabled={enviando || codigo.trim().length < 6} className={claseBoton}>
        {enviando ? "Verificando..." : "Ingresar"}
      </button>
      <div className="flex justify-between text-xs">
        <button type="button" onClick={() => { setRespaldo(!respaldo); setCodigo(""); setError(""); }}
                className="text-primary hover:underline">
          {respaldo ? "Usar el código de la app" : "No tengo el celular"}
        </button>
        <button type="button" onClick={() => onVolver()} className="text-gray-500 hover:underline">
          Volver
        </button>
      </div>
      {respaldo && (
        <p className="text-xs text-gray-500">
          Si tampoco tienes los códigos de respaldo, pide al administrador que reinicie tu segundo factor.
        </p>
      )}
    </form>
  );
}

/** Primer ingreso con segundo factor: QR para la app y confirmación con el primer código. */
export function PasoConfigurar({ pendiente, onListo, onVolver }: PasoProps) {
  const [qr, setQr] = useState("");
  const [secreto, setSecreto] = useState("");
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    let vivo = true;
    authApi.mfaConfigurar(pendiente.mfa_token)
      .then(async ({ data }) => {
        const imagen = await QRCode.toDataURL(data.uri, { width: 220, margin: 1 });
        if (vivo) { setQr(imagen); setSecreto(data.secreto); }
      })
      .catch((err) => {
        const m = mensaje(err, "No se pudo preparar el código QR");
        if (m.vencido) onVolver(m.texto);
        else if (vivo) setError(m.texto);
      });
    return () => { vivo = false; };
  }, [pendiente.mfa_token, onVolver]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError("");
    try {
      onListo((await authApi.mfaActivar(pendiente.mfa_token, codigo)).data);
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
        <p className="font-medium">Configura el código del celular (una sola vez)</p>
        <ol className="list-decimal pl-5 space-y-1 text-gray-600">
          <li>Instala <strong>Google Authenticator</strong> o <strong>Microsoft Authenticator</strong> en tu celular.</li>
          <li>En la app toca <strong>+</strong> y escanea este código.</li>
          <li>Escribe abajo el número de 6 dígitos que aparece.</li>
        </ol>
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
