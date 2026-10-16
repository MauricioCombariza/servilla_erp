"""Cuántos paquetes trae una tula, según iMile (Paso 2.3). SOLO CONSULTA: no descarga nada.

La descarga de la tula en iMile (dsOffloadingScan → .../unloading/submit) la hace la
persona con la app de iMile. Aquí solo se lee lo ya descargado en la estación con
POST .../unloading/search: un renglón por paquete con su tula (bagNo). Visto en iMile
real (2026-10-16): el servicio no filtra por tula (ignora bagNo, scanNumber, etc. y
devuelve todo lo descargado), así que se trae completo y se cuenta aquí. Ej.: la tula
2610154964301 → 36 paquetes, de 10 tulas y 309 paquetes del vehículo BGNB202610150012.

Si la tula todavía no se ha descargado en iMile no aparece y el total queda en blanco.
Se apaga con IMILE_CONSULTA_TULA_ACTIVA=false (por defecto).
"""
import json
from dataclasses import dataclass

from app.services.imile_sesion import ImileSesion, imile_sesion

RUTA_DESCARGADOS = "/lm/express/ops/v1/biz/unloading/search"
COOKIE_TOKEN = "IMILE_ACCESS_TOKEN"

_TAM_PAGINA = 500
_MAX_PAGINAS = 20  # tope de seguridad: 10.000 paquetes descargados
_ESPERA_MS = 20_000


class ImileConsultaError(Exception):
    pass


@dataclass(frozen=True)
class ConsultaTula:
    encontrada: bool
    total: int | None
    seriales: tuple[str, ...]


class ImileTula:
    def __init__(self, sesion: ImileSesion = imile_sesion, tam_pagina: int = _TAM_PAGINA):
        self._sesion = sesion
        self._tam_pagina = tam_pagina

    async def consultar(self, codigo: str) -> ConsultaTula:
        codigo = codigo.strip()
        async with self._sesion.usar() as page:
            filas = await self._descargados(page)
        seriales = sorted({
            f["waybillNo"] for f in filas
            if f.get("waybillNo") and codigo in (f.get("bagNo"), f.get("scanNumber"))
        })
        if not seriales:
            return ConsultaTula(encontrada=False, total=None, seriales=())
        return ConsultaTula(encontrada=True, total=len(seriales), seriales=tuple(seriales))

    async def _descargados(self, page) -> list[dict]:
        # La página manda el token de la cookie en Authorization; sin él iMile no responde
        headers = {"content-type": "application/json"}
        for c in await page.context.cookies():
            if c["name"] == COOKIE_TOKEN and c["value"]:
                token = c["value"]
                headers["authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
                break

        filas: list[dict] = []
        for pagina in range(1, _MAX_PAGINAS + 1):
            r = await page.request.post(
                f"{self._sesion.base_url}{RUTA_DESCARGADOS}",
                headers=headers,
                data=json.dumps({"pageNum": pagina, "pageSize": self._tam_pagina}),
                timeout=_ESPERA_MS,
            )
            try:
                body = await r.json()
            except ValueError as exc:
                raise ImileConsultaError(f"iMile respondió HTTP {r.status} sin JSON") from exc
            if body.get("status") != "success":
                raise ImileConsultaError(body.get("message") or f"iMile respondió HTTP {r.status}")
            resultados = (body.get("resultObject") or {}).get("results") or []
            filas.extend(resultados)
            if len(resultados) < self._tam_pagina:
                break
        return filas


imile_tula = ImileTula()
