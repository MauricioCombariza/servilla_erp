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

Lo aprendido en la primera corrida real (2026-11-20, ~700 guías seguidas, ninguna salió):
  - Solo con el token, iMile responde "Unauthorized data access. Please refresh the page":
    esta consulta revisa permisos de la página. Hay que mandar lo mismo que el navegador
    (resource-code, path, x-page-path, front-sec, hubcode, lang, sys-name...). front-sec y
    hubcode son del usuario y la estación: se copian de los pedidos que hace la propia
    página de iMile al abrir la consulta de seguimiento, en vez de dejarlos fijos.
  - Muchas consultas seguidas → "The system is busy, please try again later". Se consulta
    una guía cada ~1,5 s; si iMile está ocupado se espera y se reintenta, y si sigue, se
    detiene la corrida (el resto queda para la próxima carga).

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
RUTA_PAGINA = "/DSOperation/WaybillManagement/dsTrackQuery"
RECURSO_PAGINA = "dsTrackQuery"
# Encabezados que la página de iMile pone en cada pedido y que se copian tal cual
_ENCABEZADOS_PAGINA = ("front-sec", "hubcode", "lang", "sys-name", "sys-portal")

_ESPERA_MS = 20_000
_NAV_MS = 30_000
# Cuánto se espera a que la página de iMile haga un pedido del que copiar los encabezados
_ESPERA_ENCABEZADOS_MS = 10_000
# Guías por cada uso de la sesión: entre lote y lote se suelta el navegador para que el
# ingreso y la asignación de paquetes no esperen a que termine el tracking (~8 s por lote).
_LOTE = 5
# Pausa entre una consulta y la siguiente, para no saturar a iMile
_PAUSA_S = 1.5
# Esperas (s) antes de reintentar cuando iMile dice que está ocupado; agotadas, se detiene
_ESPERAS_OCUPADO_S = (10.0, 30.0, 60.0)
# Tantos "Unauthorized" seguidos = faltan permisos o encabezados: no tiene sentido seguir
_MAX_NO_AUTORIZADO = 5
# Veces que se vuelve a entrar a iMile por token vencido en cada llamada a consultar(); si
# el token sigue vencido después de entrar de nuevo, se detiene la corrida
_MAX_RECONEXIONES = 1
# Tope por corrida: si quedan más, siguen en la próxima carga (300 guías ≈ 8 min).
_MAX_POR_CORRIDA = 300
# Una guía que iMile no encuentra o que falla se intenta en tantas cargas y luego se deja
MAX_INTENTOS = 3
# Se guarda (commit) cada tantas guías: con ~2,5 s por guía, 300 guías son ~12 min y antes
# no se veía nada guardado hasta el final (2026-11-20)
_TANDA_GUARDAR = 20

_RE_MOTIVO = re.compile(r"add a problem\[(.*?)\]")
_RE_LLEGADA_DS = re.compile(r"【[^】]*\.DS】\s*Arrived")
_RE_HTML = re.compile(r"<[^>]+>")


class ImileOcupadoError(ImileConsultaError):
    """iMile pide esperar ("The system is busy"): se reintenta más tarde."""


class ImileNoAutorizadoError(ImileConsultaError):
    """iMile rechaza la consulta por permisos ("Unauthorized data access")."""


class ImileTokenVencidoError(ImileNoAutorizadoError):
    """El token de la sesión venció a mitad de la corrida ("Invalid access token: …").
    La página de iMile no vuelve al login, así que `usar()` no lo nota: hay que volver a
    entrar a la fuerza. Es de la sesión, no de la guía: no gasta intentos (2026-11-23,
    224 de 300 guías fallaron así y se quedaron sin tracking)."""


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
        mensaje = (body or {}).get("message") or "iMile no devolvió el tracking"
        bajo = mensaje.lower()
        if "busy" in bajo:
            raise ImileOcupadoError(mensaje)
        if "token" in bajo and ("invalid" in bajo or "expired" in bajo):
            raise ImileTokenVencidoError(mensaje)
        if "unauthorized" in bajo:
            raise ImileNoAutorizadoError(mensaje)
        raise ImileConsultaError(mensaje)
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
    def __init__(
        self,
        sesion: ImileSesion = imile_sesion,
        lote: int = _LOTE,
        pausa_s: float = _PAUSA_S,
        esperas_ocupado_s: tuple[float, ...] = _ESPERAS_OCUPADO_S,
        max_no_autorizado: int = _MAX_NO_AUTORIZADO,
        espera_encabezados_ms: int = _ESPERA_ENCABEZADOS_MS,
        max_reconexiones: int = _MAX_RECONEXIONES,
    ):
        self._sesion = sesion
        self._max_reconexiones = max_reconexiones
        self._lote = lote
        self._pausa_s = pausa_s
        self._esperas_ocupado_s = esperas_ocupado_s
        self._max_no_autorizado = max_no_autorizado
        self._espera_encabezados_ms = espera_encabezados_ms
        # Por qué se detuvo la última corrida antes de terminar (None = terminó)
        self.detenida: str | None = None
        # Encabezados de la página de seguimiento: se copian una vez y sirven para varias tandas
        self._headers: dict[str, str] | None = None

    async def consultar(self, guias: list[str]) -> dict[str, Tracking | Exception]:
        """Tracking de cada guía, una cada `pausa_s`. Una guía que falla queda con su error y
        se sigue con el resto. Si iMile sigue ocupado tras los reintentos, o rechaza por
        permisos varias seguidas, se detiene: las guías sin consultar no quedan en el
        resultado (siguen pendientes para la próxima carga) y `detenida` dice por qué."""
        resultados: dict[str, Tracking | Exception] = {}
        self.detenida = None
        pendientes = list(guias)
        ocupado_seguidas = 0
        no_autorizado_seguidas = 0
        reconexiones = 0
        while pendientes and self.detenida is None:
            espera_s = 0.0
            reconectar = False
            async with self._sesion.usar() as page:
                if self._headers is None:
                    self._headers = await self._encabezados(page)
                # El token se toma de nuevo: si la sesión volvió a entrar, cambió
                headers = {**self._headers, **(await encabezados_api(page))}
                for n in range(min(self._lote, len(pendientes))):
                    if n:
                        await asyncio.sleep(self._pausa_s)
                    guia = pendientes[0]
                    try:
                        res: Tracking | Exception = await self._una(page, headers, guia)
                    except ImileOcupadoError as exc:
                        # La guía no se da por consultada: se reintenta después de esperar
                        if ocupado_seguidas >= len(self._esperas_ocupado_s):
                            self.detenida = f"iMile sigue ocupado: {exc}"
                        else:
                            espera_s = self._esperas_ocupado_s[ocupado_seguidas]
                        ocupado_seguidas += 1
                        break
                    except ImileTokenVencidoError as exc:
                        # La guía tampoco se da por consultada: se reintenta con sesión nueva
                        if reconexiones >= self._max_reconexiones:
                            self.detenida = f"El token de iMile sigue vencido tras volver a entrar: {exc}"
                        else:
                            reconectar = True
                        break
                    except ImileConsultaError as exc:
                        res = exc
                    pendientes.pop(0)
                    resultados[guia] = res
                    ocupado_seguidas = 0
                    if isinstance(res, ImileNoAutorizadoError):
                        no_autorizado_seguidas += 1
                        if no_autorizado_seguidas >= self._max_no_autorizado:
                            self.detenida = f"iMile no autoriza la consulta: {res}"
                            self._headers = None  # la próxima corrida los vuelve a copiar
                            break
                    else:
                        no_autorizado_seguidas = 0
            if reconectar:
                # Fuera de usar(): conectar() toma el mismo candado de la sesión
                reconexiones += 1
                logger.warning("Tracking iMile: token vencido, se vuelve a entrar a iMile")
                try:
                    await self._sesion.conectar(forzar=True)
                except Exception as exc:  # noqa: BLE001 — cualquier falla del login detiene la corrida
                    self.detenida = f"No se pudo volver a entrar a iMile: {exc}"
                self._headers = None  # front-sec y demás se copian de la sesión nueva
                continue
            # La espera va fuera de la sesión: el ingreso y la asignación siguen mientras tanto
            if espera_s:
                logger.info("iMile ocupado: se reintenta el tracking en %.0f s", espera_s)
                await asyncio.sleep(espera_s)
            elif pendientes and self.detenida is None:
                await asyncio.sleep(self._pausa_s)
        if self.detenida:
            logger.warning("Tracking iMile detenido (%d guías sin consultar): %s",
                           len(pendientes), self.detenida)
        return resultados

    async def _encabezados(self, page) -> dict[str, str]:
        """Encabezados como los que manda la página "Consulta de seguimiento". front-sec y
        hubcode se copian del primer pedido que hace la página al abrirse."""
        vistos: dict[str, str] = {}

        def copiar(request) -> None:
            h = request.headers
            if not vistos and "front-sec" in h:
                vistos.update({k: h[k] for k in _ENCABEZADOS_PAGINA if k in h})

        url_pagina = f"{self._sesion.base_url}/#{RUTA_PAGINA}"
        page.on("request", copiar)
        try:
            await page.goto(url_pagina, timeout=_NAV_MS)
            if not await self._esperar(lambda: bool(vistos)):
                # Cambiar solo el #... puede no disparar pedidos: se recarga la página
                await page.reload(timeout=_NAV_MS)
                await self._esperar(lambda: bool(vistos))
        finally:
            page.remove_listener("request", copiar)
        if not vistos:
            logger.warning("Tracking iMile: la página no hizo pedidos con front-sec; se consulta sin él")

        headers = await encabezados_api(page)
        headers.update({"lang": "es_MX", "sys-name": "DS", "sys-portal": "DS"})
        headers.update(vistos)
        headers.update({
            "accept": "application/json, text/plain, */*",
            "resource-code": RECURSO_PAGINA,
            "path": RUTA_PAGINA,
            "x-page-path": url_pagina,
            "timezone": "-5",
        })
        return headers

    async def _esperar(self, listo) -> bool:
        fin = asyncio.get_running_loop().time() + self._espera_encabezados_ms / 1000
        while not listo():
            if asyncio.get_running_loop().time() >= fin:
                return False
            await asyncio.sleep(0.1)
        return True

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
      AND tracking_intentos < :max_intentos
    ORDER BY tracking_intentos, fecha_entrega DESC
    LIMIT :limite
""")

_GUARDAR = text("""
    UPDATE seriales_gestion
    SET fecha_llegada_ds = :llegada_ds,
        novedades_imile  = CAST(:novedades AS JSONB)
    WHERE serial = :serial
""")

_FALLIDO = text("""
    UPDATE seriales_gestion SET tracking_intentos = tracking_intentos + 1 WHERE serial = :serial
""")

_en_curso = asyncio.Lock()


@dataclass
class ResumenTracking:
    consultadas: int = 0
    guardadas: int = 0
    sin_tracking: int = 0
    errores: int = 0
    # No se alcanzaron a consultar (corrida detenida): siguen pendientes
    sin_consultar: int = 0
    detenida: str | None = None
    primer_error: str | None = None


async def completar_tracking_pendiente(
    consulta: ImileTracking = imile_tracking, limite: int = _MAX_POR_CORRIDA
) -> ResumenTracking:
    """Consulta el tracking de las guías entregadas que aún no lo tienen y lo guarda.
    Si ya hay una corrida en curso (dos cargas seguidas), no arranca otra."""
    resumen = ResumenTracking()
    if _en_curso.locked():
        return resumen
    async with _en_curso, AsyncSessionLocal() as db:
        # Solo guías entregadas (tracking final) y sin tracking guardado: una vez guardado,
        # nunca se vuelve a consultar
        guias = list((await db.execute(
            _PENDIENTES, {"limite": limite, "max_intentos": MAX_INTENTOS})).scalars())
        if not guias:
            return resumen
        resumen.consultadas = len(guias)
        logger.info("Tracking iMile: %d guías entregadas por consultar", len(guias))
        for i in range(0, len(guias), _TANDA_GUARDAR):
            tanda = guias[i:i + _TANDA_GUARDAR]
            resultados = await consulta.consultar(tanda)
            await _guardar(db, resultados, resumen)
            await db.commit()  # lo consultado queda guardado aunque la corrida se corte después
            logger.info("Tracking iMile: %d/%d consultadas, %d guardadas",
                        min(i + len(tanda), len(guias)), len(guias), resumen.guardadas)
            if consulta.detenida:
                resumen.detenida = consulta.detenida
                resumen.sin_consultar = len(guias) - i - len(resultados)
                break
    logger.info("Tracking iMile: %s", resumen)
    return resumen


async def _guardar(db, resultados: dict[str, Tracking | Exception], resumen: ResumenTracking) -> None:
    for guia, res in resultados.items():
        if isinstance(res, Exception):
            resumen.errores += 1
            # "Unauthorized" es de la sesión, no de la guía: no gasta intentos
            if not isinstance(res, ImileNoAutorizadoError):
                await db.execute(_FALLIDO, {"serial": guia})
            # Una línea por guía llenaba el log (cientos con el mismo error): va la primera
            resumen.primer_error = resumen.primer_error or f"{guia}: {res}"
            logger.debug("Tracking iMile %s: %s", guia, res)
            continue
        if not res.encontrado:
            # Se deja en NULL para volver a intentar en la próxima carga (hasta MAX_INTENTOS)
            resumen.sin_tracking += 1
            await db.execute(_FALLIDO, {"serial": guia})
            continue
        novedades = [{"hora": n.hora.isoformat(), "motivo": n.motivo} for n in res.novedades]
        await db.execute(_GUARDAR, {
            "serial": guia, "llegada_ds": res.llegada_ds,
            "novedades": json.dumps(novedades, ensure_ascii=False),
        })
        resumen.guardadas += 1
