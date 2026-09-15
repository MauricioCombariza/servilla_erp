"""Construcción de URL de imagen de guía a partir del serial."""

BASE_IMAGENES_URL = "https://186.180.15.66/guias"


def construir_image_url(serial: str) -> str:
    if len(serial) == 16:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:16]
    elif len(serial) == 13:
        inicio, medio, final = serial[:8], serial[8:13], serial[10:13]
    else:
        inicio, medio, final = serial[:4], serial[4:7], serial[4:10]
    return f"{BASE_IMAGENES_URL}/{inicio}/{medio}/{final}.png"
