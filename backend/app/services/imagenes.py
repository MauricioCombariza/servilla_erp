"""Construcción de URL de imagen de guía a partir del serial y descarga proxied."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _base_url() -> str:
    """URL base de las imágenes en el servidor legado (IMAGENES_LEGADO_URL).

    No hay valor por defecto: sin configuración la descarga queda deshabilitada,
    para no conectarse nunca a una dirección escrita en el código.
    """
    return settings.imagenes_legado_url.rstrip("/")


def construir_image_url(serial: str) -> str:
    if len(serial) == 16:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:16]
    elif len(serial) == 13:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:13]
    else:
        inicio, medio, final = serial[:4], serial[4:7], serial[4:10]
    return f"{_base_url()}/{inicio}/{medio}/{final}.png"


async def fetch_imagen_bytes(serial: str) -> tuple[bytes, str] | None:
    """
    Descarga la imagen de guía desde el servidor legado.

    El certificado TLS de ese servidor está vencido desde 2026-02-05 (CN
    gruposervilla.com, dominio cuyo DNS ya no apunta ahí). Si se configura
    IMAGENES_LEGADO_CA se verifica contra ese certificado; si no, se conecta sin
    verificar (por eso el acceso a ese servidor debe estar restringido en el
    firewall a la IP del ERP, y a futuro ir por túnel WireGuard). El backend
    actúa de proxy para que el navegador nunca golpee ese servidor directamente.
    """
    if not _base_url():
        logger.warning("IMAGENES_LEGADO_URL no configurado — imágenes de guía no disponibles")
        return None
    url = construir_image_url(serial)
    verify: bool | str = settings.imagenes_legado_ca or False
    try:
        async with httpx.AsyncClient(verify=verify, timeout=15) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error("Error descargando imagen de guía (%s): %s", url, exc)
        return None

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not content_type.startswith("image/"):
        return None
    return resp.content, content_type
