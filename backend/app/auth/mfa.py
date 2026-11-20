"""Segundo factor con código del celular (TOTP, RFC 6238) y códigos de respaldo.

- Funciona con Google Authenticator, Microsoft Authenticator, Authy, etc.: código de
  6 dígitos que cambia cada 30 segundos. Se acepta el del paso anterior y el siguiente
  (reloj del celular algo corrido) y nunca dos veces el mismo (mfa_ultimo_paso).
- El secreto se guarda cifrado (Fernet). La llave sale de MFA_CLAVE_CIFRADO o, si no
  está, se deriva de JWT_SECRET: cambiar cualquiera de las dos obliga a reiniciar el MFA
  de todos.
- Códigos de respaldo: 10 de un solo uso, guardados como hash (bcrypt), para entrar si
  se pierde el celular.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from functools import lru_cache
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.auth.claves import hash_clave, verificar_clave
from app.config import settings

EMISOR = "Servilla ERP"
PASO_S = 30
DIGITOS = 6
VENTANA = 1  # pasos aceptados antes y después del actual
CODIGOS_RESPALDO = 10


# ── Cifrado del secreto ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    if settings.mfa_clave_cifrado:
        return Fernet(settings.mfa_clave_cifrado.encode())
    llave = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"servilla-mfa",
                 info=b"secreto-totp").derive(settings.jwt_secret.encode())
    return Fernet(base64.urlsafe_b64encode(llave))


def cifrar(secreto: str) -> str:
    return _fernet().encrypt(secreto.encode()).decode()


def descifrar(cifrado: str) -> str | None:
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        return None


# ── TOTP ─────────────────────────────────────────────────────────────────────

def nuevo_secreto() -> str:
    """Secreto base32 de 160 bits (lo que piden las apps)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _clave(secreto: str) -> bytes:
    relleno = "=" * (-len(secreto) % 8)
    return base64.b32decode(secreto.upper() + relleno)


def codigo_en(secreto: str, paso: int) -> str:
    digest = hmac.new(_clave(secreto), struct.pack(">Q", paso), hashlib.sha1).digest()
    corte = digest[-1] & 0x0F
    numero = struct.unpack(">I", digest[corte:corte + 4])[0] & 0x7FFFFFFF
    return str(numero % 10 ** DIGITOS).zfill(DIGITOS)


def paso_actual(momento: float | None = None) -> int:
    return int((momento if momento is not None else time.time()) // PASO_S)


def verificar_totp(secreto: str, codigo: str, ultimo_paso: int | None,
                   momento: float | None = None) -> int | None:
    """Paso al que corresponde el código, o None si no sirve (o ya se usó)."""
    codigo = "".join(c for c in codigo if c.isdigit())
    if len(codigo) != DIGITOS:
        return None
    actual = paso_actual(momento)
    for paso in range(actual - VENTANA, actual + VENTANA + 1):
        if ultimo_paso is not None and paso <= ultimo_paso:
            continue
        if hmac.compare_digest(codigo_en(secreto, paso), codigo):
            return paso
    return None


def uri_otpauth(secreto: str, username: str) -> str:
    """Lo que va en el QR que se escanea con la app."""
    etiqueta = quote(f"{EMISOR}:{username}")
    return (f"otpauth://totp/{etiqueta}?secret={secreto}&issuer={quote(EMISOR)}"
            f"&algorithm=SHA1&digits={DIGITOS}&period={PASO_S}")


# ── Códigos de respaldo ──────────────────────────────────────────────────────

def _normalizar(codigo: str) -> str:
    return "".join(c for c in codigo.upper() if c.isalnum())


def nuevos_codigos_respaldo() -> list[str]:
    """Códigos tipo ABCD-EFGH (sin letras que se confunden: 0/O, 1/I/L)."""
    alfabeto = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    codigos = []
    for _ in range(CODIGOS_RESPALDO):
        crudo = "".join(secrets.choice(alfabeto) for _ in range(8))
        codigos.append(f"{crudo[:4]}-{crudo[4:]}")
    return codigos


def hash_respaldo(codigo: str) -> str:
    return hash_clave(_normalizar(codigo))


def coincide_respaldo(codigo: str, hash_guardado: str) -> bool:
    return verificar_clave(_normalizar(codigo), hash_guardado)


def parece_respaldo(codigo: str) -> bool:
    return len(_normalizar(codigo)) == 8 and not _normalizar(codigo).isdigit()
