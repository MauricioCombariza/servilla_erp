"""Construcción de URL de imagen de guía a partir del serial y descarga proxied."""

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_IMAGENES_URL = "https://186.180.15.66/guias"


def construir_image_url(serial: str) -> str:
    if len(serial) == 16:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:16]
    elif len(serial) == 13:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:13]
    else:
        inicio, medio, final = serial[:4], serial[4:7], serial[4:10]
    return f"{BASE_IMAGENES_URL}/{inicio}/{medio}/{final}.png"


async def fetch_imagen_bytes(serial: str) -> tuple[bytes, str] | None:
    """
    Descarga la imagen de guía desde el servidor legado (186.180.15.66).

    El certificado TLS de ese servidor está vencido desde 2026-02-05 (CN
    gruposervilla.com, dominio cuyo DNS ya no apunta ahí) — se conecta por IP
    sin verificar el certificado, con la misma confianza con la que ya se usa
    pymysql directo contra bases_web en ese mismo host. El backend actúa de
    proxy para que el navegador nunca golpee ese servidor directamente.
    """
    url = construir_image_url(serial)
    try:
        async with httpx.AsyncClient(verify=False, timeout=15) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        logger.error("Error descargando imagen de guía (%s): %s", url, exc)
        return None

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or not content_type.startswith("image/"):
        return None
    return resp.content, content_type
