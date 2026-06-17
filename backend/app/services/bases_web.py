"""
Utilidad de solo-lectura para bases_web.histo.
Sincroniza ciudad1 → seriales_gestion.ciudad de forma lazy (por planilla).
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import pymysql
import pymysql.cursors
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


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


async def sync_ciudades_planilla(planilla: str, db: AsyncSession) -> int:
    """
    Obtiene ciudad1 desde bases_web.histo para cada serial de la planilla
    y actualiza seriales_gestion.ciudad. Retorna cantidad de seriales actualizados.
    """
    rows = await asyncio.to_thread(_fetch_ciudades_sync, planilla)
    if not rows:
        return 0

    # Bulk UPDATE por serial — PostgreSQL no tiene UPDATE ... VALUES (...) estándar,
    # así que usamos una CTE con unnest para hacerlo en una sola query.
    serials = [r[0] for r in rows]
    ciudades = [r[1] for r in rows]

    result = await db.execute(
        text("""
            UPDATE seriales_gestion sg
            SET ciudad = data.ciudad
            FROM (
                SELECT unnest(:serials::text[])  AS serial,
                       unnest(:ciudades::text[]) AS ciudad
            ) AS data
            WHERE sg.serial   = data.serial
              AND sg.planilla = :planilla
              AND (sg.ciudad IS DISTINCT FROM data.ciudad)
        """),
        {"serials": serials, "ciudades": ciudades, "planilla": planilla},
    )
    await db.commit()
    return result.rowcount
