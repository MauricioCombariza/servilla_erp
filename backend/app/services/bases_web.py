"""
Utilidad de solo-lectura para bases_web.histo.
Sincroniza ciudad1 → seriales_gestion.ciudad de forma lazy (por planilla).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from urllib.parse import urlparse

import pymysql
import pymysql.cursors
from sqlalchemy import ARRAY, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Rango de `orden` que delimita el lote de órdenes activo para el reporte de
# pendientes de entrega (courier externo / mensajeros). Es un esquema de
# numeración estructural del sistema legado, no un parámetro de negocio que
# cambie por corrida — igual al hardcode del script Streamlit original.
PENDIENTES_ORDEN_INICIO = 122000
PENDIENTES_ORDEN_FIN = 128000


def _parse_dsn() -> dict:
    """Extrae host/port/user/password/db desde settings.bases_web_url."""
    url = settings.bases_web_url
    if not url:
        return {}
    # Normalizar: mysql+aiomysql:// → mysql://  o  mysql+pymysql:// → mysql://
    if "://" in url:
        scheme, rest = url.split("://", 1)
        url = f"mysql://{rest}"
    parsed = urlparse(url)
    return {
        "host":     parsed.hostname or "186.180.15.66",
        "port":     parsed.port or 12539,
        "user":     parsed.username or "servilla_remoto",
        "password": parsed.password or "",
        "database": (parsed.path or "/bases_web").lstrip("/"),
    }


def _fetch_ciudades_sync(planilla: str) -> list[tuple[str, str | None]]:
    """
    Retorna [(serial, ciudad1), ...] para la planilla desde bases_web.histo.
    Corre en un thread aparte via asyncio.to_thread.
    """
    dsn = _parse_dsn()
    if not dsn:
        logger.warning("bases_web_url no configurado — ciudad no disponible")
        return []

    try:
        conn = pymysql.connect(
            host=dsn["host"],
            port=dsn["port"],
            user=dsn["user"],
            password=dsn["password"],
            database=dsn["database"],
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=10,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT serial,
                           NULLIF(TRIM(ciudad1), '') AS ciudad
                    FROM histo
                    WHERE planilla = %s OR lot_esc = %s
                    """,
                    (planilla, planilla),
                )
                rows = cur.fetchall()
        return [(r["serial"], r["ciudad"]) for r in rows if r["serial"]]
    except Exception as exc:
        logger.error("Error conectando a bases_web: %s", exc)
        return []


def _buscar_histo_serial_sync(termino: str) -> list[dict]:
    dsn = _parse_dsn()
    if not dsn:
        return []
    try:
        conn = pymysql.connect(
            **dsn,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=15,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT serial, nombred, dirdes1, ciudad1, f_emi, cod_men, cod_esc "
                    "FROM histo WHERE serial LIKE %s ORDER BY f_emi DESC LIMIT 100",
                    (f"%{termino}%",),
                )
                return cur.fetchall()
    except Exception as exc:
        logger.error("Error buscando serial en bases_web.histo: %s", exc)
        return []


def _buscar_histo_nombre_sync(termino: str) -> list[dict]:
    dsn = _parse_dsn()
    if not dsn:
        return []
    palabras = [p for p in termino.strip().split() if p]
    if not palabras:
        return []
    try:
        conn = pymysql.connect(
            **dsn,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=15,
        )
        with conn:
            with conn.cursor() as cur:
                cond = " AND ".join(["LOWER(nombred) LIKE %s"] * len(palabras))
                params = tuple(f"%{p.lower()}%" for p in palabras)
                cur.execute(
                    f"SELECT serial, nombred, dirdes1, ciudad1, f_emi, cod_men, cod_esc "
                    f"FROM histo WHERE {cond} ORDER BY f_emi DESC LIMIT 200",
                    params,
                )
                return cur.fetchall()
    except Exception as exc:
        logger.error("Error buscando nombre en bases_web.histo: %s", exc)
        return []


async def buscar_histo(termino: str, modo: str) -> list[dict]:
    if modo == "serial":
        return await asyncio.to_thread(_buscar_histo_serial_sync, termino)
    elif modo == "nombre":
        return await asyncio.to_thread(_buscar_histo_nombre_sync, termino)
    return []


def _fetch_pendientes_courier_sync(codigos: list[int], corte: str) -> list[dict]:
    """
    Retorna filas de bases_web.histo consideradas 'pendientes de entrega' para
    los cod_men dados: aún no entregadas ni devueltas (retorno/ret_esc), dentro
    del lote de órdenes activo (PENDIENTES_ORDEN_INICIO..FIN) y con f_emi >= corte.

    histo.cod_men/orden son VARCHAR — se castean a entero para comparar (igual
    al pd.to_numeric defensivo del script Streamlit original, que no asumía
    match exacto de string). histo.f_emi también es VARCHAR 'YYYY.MM.DD' (no
    DATE): el corte debe venir formateado igual para que la comparación de
    string funcione (ver updateDashboard.py: 'YYYY-MM-DD' NO filtra nada aquí,
    porque '.' > '-' en orden lexicográfico).
    """
    dsn = _parse_dsn()
    if not dsn or not codigos:
        return []
    try:
        conn = pymysql.connect(
            **dsn,
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5,
            read_timeout=30,
        )
        placeholders = ",".join(["%s"] * len(codigos))
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT serial, orden, cod_men, f_emi, no_entidad, nombred,
                           dirdes1, cod_sec, ciudad1, dpto1, retorno, ret_esc, motivo
                    FROM histo
                    WHERE CAST(TRIM(cod_men) AS UNSIGNED) IN ({placeholders})
                      AND f_emi >= %s
                      AND CAST(TRIM(orden) AS UNSIGNED) BETWEEN %s AND %s
                      AND retorno NOT IN ('D', 'o')
                      AND ret_esc IN ('i', 'p')
                    """,
                    (*codigos, corte, PENDIENTES_ORDEN_INICIO, PENDIENTES_ORDEN_FIN),
                )
                return cur.fetchall()
    except Exception as exc:
        logger.error("Error consultando pendientes de entrega en bases_web.histo: %s", exc)
        return []


async def fetch_pendientes_courier(codigos: list[int], dias_corte: int = 60) -> list[dict]:
    corte = (date.today() - timedelta(days=dias_corte)).strftime("%Y.%m.%d")
    return await asyncio.to_thread(_fetch_pendientes_courier_sync, codigos, corte)


async def sync_ciudades_planilla(planilla: str, db: AsyncSession) -> int:
    """
    Obtiene ciudad1 desde bases_web.histo para cada serial de la planilla
    y actualiza seriales_gestion.ciudad. Retorna cantidad de seriales actualizados.
    """
    rows = await asyncio.to_thread(_fetch_ciudades_sync, planilla)
    if not rows:
        return 0

    serials = [r[0] for r in rows]
    ciudades = [r[1] for r in rows]

    sql = text("""
        UPDATE seriales_gestion sg
        SET ciudad = data.ciudad
        FROM unnest(:serials, :ciudades) AS data(serial, ciudad)
        WHERE sg.serial   = data.serial
          AND sg.planilla = :planilla
          AND sg.ciudad IS DISTINCT FROM data.ciudad
    """).bindparams(
        bindparam("serials",  type_=ARRAY(String)),
        bindparam("ciudades", type_=ARRAY(String)),
    )
    result = await db.execute(sql, {"serials": serials, "ciudades": ciudades, "planilla": planilla})
    await db.commit()
    return result.rowcount
