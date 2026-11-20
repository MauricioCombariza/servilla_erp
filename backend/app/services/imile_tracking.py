"""Tracking de una guía en iMile, para medir el tiempo de entrega (mejora continua). SOLO CONSULTA.

La página "Consulta de seguimiento" (#/DSOperation/WaybillManagement/dsTrackQuery) hace
POST /saastms/v1/biz/track/query con {"searchType": "waybillNo", "searchValue": <guía>}.
Visto en iMile real (2026-11-19, guía 6110626411459): resultObject.trackInfo[<guía>] es la
lista de eventos, del más nuevo al más viejo, cada uno con content, time y trackType:
  - trackType "Problem" → una novedad ("add a problem[<motivo>]"). Cada novedad descuenta
    24 h del tiempo de entrega (regla de iMile).
  - "【BOG-….DS】Arrived" → llegada a la estación de reparto: inicio de las 48 h. Coincide
    con "Primera hora de llegada en DS" del informe de guías.
Las horas vienen en hora de Bogotá (la página manda el encabezado timezone: -5).

Después de cada carga masiva del informe Delivered se consultan las guías entregadas que
aún no tienen tracking (completar_tracking_pendiente). Se apaga con
IMILE_TRACKING_ACTIVO=false (por defecto).
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.imile_sesion import ImileSesion, imile_sesion
from app.services.imile_tula import ImileConsultaError, encabezados_api

logger = logging.getLogger(__name__)

RUTA_TRACKING = "/saastms/v1/biz/track/query"
TIPO_NOVEDAD = "Problem"

_ZONA = ZoneInfo("America/Bogota")
_ESPERA_MS = 20_000
# Guías por cada uso de la sesión: entre lote y lote se suelta el navegador para que el
# ingreso y la asignación de paquetes no esperen a que termine todo el tracking.
_LOTE = 20
# Tope por corrida: si quedan más, siguen en la próxima carga.
_MAX_POR_CORRIDA = 2_000

_RE_MOTIVO = re.compile(r"add a problem\[(.*?)\]")
_RE_LLEGADA_DS = re.compile(r"【[^】]*\.DS】\s*Arrived")
_RE_HTML = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Novedad:
    hora: datetime
    motivo: str


@dataclass(frozen=True)
class Tracking:
    encontrado: bool
    llegada_ds: datetime | None = None
    novedades: tuple[Novedad, ...] = ()


def _hora(valor: str | None) -> datetime | None:
    try:
        return datetime.strptime((valor or "").strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=_ZONA)
    except ValueError:
        return None


def leer_tracking(body: dict | None, guia: str) -> Tracking:
    """Respuesta de .../track/query → llegada a la estación y novedades."""
    if not body or body.get("status") != "success":
        raise ImileConsultaError((body or {}).get("message") or "iMile no devolvió el tracking")
    eventos = ((body.get("resultObject") or {}).get("trackInfo") or {}).get(guia) or []
    if not eventos:
        return Tracking(encontrado=False)

    llegadas: list[datetime] = []
    novedades: list[Novedad] = []
    for ev in eventos:
        hora = _hora(ev.get("time"))
        if hora is None:
            continue
        contenido = ev.get("content") or ""
        if ev.get("trackType") == TIPO_NOVEDAD:
            m = _RE_MOTIVO.search(contenido)
            motivo = m.group(1) if m else _RE_HTML.sub("", contenido).strip()
            novedades.append(Novedad(hora, motivo))
        elif _RE_LLEGADA_DS.search(contenido):
            llegadas.append(hora)

    return Tracking(
        encontrado=True,
        # Si volvió a llegar a la estación (p. ej. tras una devolución), cuenta la primera
        llegada_ds=min(llegadas) if llegadas else None,
        novedades=tuple(sorted(novedades, key=lambda n: n.hora)),
    )


class ImileTracking:
    def __init__(self, sesion: ImileSesion = imile_sesion, lote: int = _LOTE):
        self._sesion = sesion
        self._lote = lote

    async def consultar(self, guias: list[str]) -> dict[str, Tracking | Exception]:
        """Tracking de cada guía. Una guía que falla queda con su error y se sigue con el resto."""
        resultados: dict[str, Tracking | Exception] = {}
        for i in range(0, len(guias), self._lote):
            async with self._sesion.usar() as page:
                headers = await encabezados_api(page)
                headers["timezone"] = "-5"
                for guia in guias[i:i + self._lote]:
                    try:
                        resultados[guia] = await self._una(page, headers, guia)
                    except ImileConsultaError as exc:
                        resultados[guia] = exc
        return resultados

    async def _una(self, page, headers: dict, guia: str) -> Tracking:
        r = await page.request.post(
            f"{self._sesion.base_url}{RUTA_TRACKING}",
            headers=headers,
            data=json.dumps({"searchType": "waybillNo", "searchValue": guia}),
            timeout=_ESPERA_MS,
        )
        try:
            body = await r.json()
        except ValueError as exc:
            raise ImileConsultaError(f"iMile respondió HTTP {r.status} sin JSON") from exc
        return leer_tracking(body, guia)


imile_tracking = ImileTracking()


# ── Completar el tracking de las guías entregadas ────────────────────────────

_PENDIENTES = text("""
    SELECT serial FROM seriales_gestion
    WHERE fecha_entrega IS NOT NULL AND novedades_imile IS NULL
    ORDER BY fecha_entrega DESC
    LIMIT :limite
""")

_GUARDAR = text("""
    UPDATE seriales_gestion
    SET fecha_llegada_ds = :llegada_ds,
        novedades_imile  = CAST(:novedades AS JSONB)
    WHERE serial = :serial
""")

_en_curso = asyncio.Lock()


@dataclass
class ResumenTracking:
    consultadas: int = 0
    guardadas: int = 0
    sin_tracking: int = 0
    errores: int = 0


async def completar_tracking_pendiente(
    consulta: ImileTracking = imile_tracking, limite: int = _MAX_POR_CORRIDA
) -> ResumenTracking:
    """Consulta el tracking de las guías entregadas que aún no lo tienen y lo guarda.
    Si ya hay una corrida en curso (dos cargas seguidas), no arranca otra."""
    resumen = ResumenTracking()
    if _en_curso.locked():
        return resumen
    async with _en_curso, AsyncSessionLocal() as db:
        guias = list((await db.execute(_PENDIENTES, {"limite": limite})).scalars())
        if not guias:
            return resumen
        resumen.consultadas = len(guias)
        for guia, res in (await consulta.consultar(guias)).items():
            if isinstance(res, Exception):
                resumen.errores += 1
                logger.warning("Tracking iMile %s: %s", guia, res)
                continue
            if not res.encontrado:
                # Se deja en NULL para volver a intentar en la próxima carga
                resumen.sin_tracking += 1
                continue
            novedades = [{"hora": n.hora.isoformat(), "motivo": n.motivo} for n in res.novedades]
            await db.execute(_GUARDAR, {
                "serial": guia, "llegada_ds": res.llegada_ds,
                "novedades": json.dumps(novedades, ensure_ascii=False),
            })
            resumen.guardadas += 1
        await db.commit()
    logger.info("Tracking iMile: %s", resumen)
    return resumen
