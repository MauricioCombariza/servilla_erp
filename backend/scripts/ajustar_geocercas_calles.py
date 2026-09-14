"""
Ajusta geocercas activas para que sus 4 bordes coincidan con la calle/carrera real
más cercana en esa dirección (norte/sur = calle, oriente/occidente = carrera), usando
datos de OpenStreetMap (Overpass API). El polígono original — forma libre dibujada a
mano en /geocercas — se reemplaza por un rectángulo alineado a los 4 cardinales que
aproxima la cuadra real.

Requiere salida a internet (hacia overpass-api.de) desde donde se ejecute.

Geocercas donde no se encuentra una vía cercana en algún lado, o donde el resultado
cambia el área más de lo razonable, quedan marcadas para revisión manual y NO se
tocan — no se fuerza un ajuste sobre datos insuficientes.

Uso:
    python scripts/ajustar_geocercas_calles.py                        # dry-run, todas las activas
    python scripts/ajustar_geocercas_calles.py --ids 12,15            # dry-run, solo esos IDs
    python scripts/ajustar_geocercas_calles.py --commit --ids 12,15   # aplica solo esos IDs (ya aprobados)
    python scripts/ajustar_geocercas_calles.py --restore backup_geocercas_20260914_193000.json
"""

import argparse
import asyncio
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from shapely.geometry import LineString, Point, shape
from shapely.ops import nearest_points
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.geocercas import Geocerca
from app.services.geocercas_service import calcular_area_m2

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Overpass rechaza con 406 las peticiones sin un User-Agent identificable (bloquea el
# default de urllib "Python-urllib/x.y" como medida anti-abuso).
_HEADERS = {"User-Agent": "servilla-erp-geocercas/1.0 (contacto: mcombarizav@gmail.com)"}
MARGEN_GRADOS = 0.0025  # ~250 m en Bogotá, margen de búsqueda alrededor de cada geocerca
RADIO_MAX_M = 400.0  # si la vía más cercana en un lado está más lejos que esto, no se ajusta
UMBRAL_CAMBIO_AREA = 0.60  # si el área cambia más de 60%, se marca para revisión en vez de aplicar

_RE_CALLE = re.compile(
    r"^(calle|cl\.?|cll\.?|diagonal|dg\.?|avenida\s*calle|av\.?\s*calle|av\.?\s*cl\.?)\s",
    re.IGNORECASE,
)
_RE_CARRERA = re.compile(
    r"^(carrera|cr\.?|cra\.?|kra\.?|transversal|tv\.?|avenida\s*carrera|av\.?\s*carrera|av\.?\s*cra\.?)\s",
    re.IGNORECASE,
)


def _overpass_query(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict:
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    query = f"""
    [out:json][timeout:25];
    (
      way["highway"]["name"]({bbox});
    );
    out geom;
    """
    req = urllib.request.Request(
        OVERPASS_URL, data=query.encode("utf-8"), method="POST", headers=_HEADERS
    )
    ultimo_error: Exception | None = None
    for _intento in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            ultimo_error = e
            time.sleep(5)
    raise RuntimeError(f"Overpass falló tras reintentos: {ultimo_error}")


def _clasificar_vias(elementos: list[dict]) -> tuple[list[tuple[str, LineString]], list[tuple[str, LineString]]]:
    calles, carreras = [], []
    for el in elementos:
        nombre = (el.get("tags") or {}).get("name", "")
        geom = el.get("geometry")
        if not nombre or not geom or len(geom) < 2:
            continue
        linea = LineString([(pt["lon"], pt["lat"]) for pt in geom])
        if _RE_CALLE.match(nombre):
            calles.append((nombre, linea))
        elif _RE_CARRERA.match(nombre):
            carreras.append((nombre, linea))
    return calles, carreras


def _distancia_m(p1: Point, p2: Point) -> float:
    # Aproximación plana local (suficiente para comparar distancias cortas en Bogotá;
    # no se persiste, solo se usa para elegir la vía más cercana y filtrar por radio).
    lat_media = math.radians((p1.y + p2.y) / 2)
    dx = (p2.x - p1.x) * 111_320 * math.cos(lat_media)
    dy = (p2.y - p1.y) * 111_320
    return math.hypot(dx, dy)


def _mejor_candidato(
    vias: list[tuple[str, LineString]], centroid: Point, lado: str
) -> tuple[str, Point, float] | None:
    mejor = None
    for nombre, linea in vias:
        punto_cercano = nearest_points(linea, centroid)[0]
        if lado == "norte" and punto_cercano.y <= centroid.y:
            continue
        if lado == "sur" and punto_cercano.y >= centroid.y:
            continue
        if lado == "oriente" and punto_cercano.x <= centroid.x:
            continue
        if lado == "occidente" and punto_cercano.x >= centroid.x:
            continue
        dist = _distancia_m(centroid, punto_cercano)
        if mejor is None or dist < mejor[2]:
            mejor = (nombre, punto_cercano, dist)
    return mejor


def _ajustar_geocerca(geocerca: Geocerca) -> dict:
    geom = shape(geocerca.poligono)
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    centroid = geom.centroid

    datos = _overpass_query(
        min_lon - MARGEN_GRADOS, min_lat - MARGEN_GRADOS,
        max_lon + MARGEN_GRADOS, max_lat + MARGEN_GRADOS,
    )
    calles, carreras = _clasificar_vias(datos.get("elements", []))

    candidatos = {
        "norte": _mejor_candidato(calles, centroid, "norte"),
        "sur": _mejor_candidato(calles, centroid, "sur"),
        "oriente": _mejor_candidato(carreras, centroid, "oriente"),
        "occidente": _mejor_candidato(carreras, centroid, "occidente"),
    }

    faltantes = [lado for lado, c in candidatos.items() if c is None or c[2] > RADIO_MAX_M]
    if faltantes:
        return {"estado": f"SIN_VIA_CERCANA_{'_'.join(faltantes)}", "geocerca": geocerca}

    nuevo_norte = candidatos["norte"][1].y
    nuevo_sur = candidatos["sur"][1].y
    nuevo_oriente = candidatos["oriente"][1].x
    nuevo_occidente = candidatos["occidente"][1].x

    if not (nuevo_occidente < nuevo_oriente and nuevo_sur < nuevo_norte):
        return {"estado": "REVISAR_rectangulo_degenerado", "geocerca": geocerca}

    nuevo_poligono = {
        "type": "Polygon",
        "coordinates": [[
            [nuevo_occidente, nuevo_sur],
            [nuevo_oriente, nuevo_sur],
            [nuevo_oriente, nuevo_norte],
            [nuevo_occidente, nuevo_norte],
            [nuevo_occidente, nuevo_sur],
        ]],
    }
    if not shape(nuevo_poligono).contains(centroid):
        return {"estado": "REVISAR_no_contiene_centroide", "geocerca": geocerca}

    area_actual = float(geocerca.area_m2)
    area_nueva = calcular_area_m2(nuevo_poligono)
    cambio = abs(area_nueva - area_actual) / area_actual if area_actual else 0.0
    estado = "OK" if cambio <= UMBRAL_CAMBIO_AREA else "REVISAR_cambio_area_grande"

    return {
        "estado": estado,
        "geocerca": geocerca,
        "poligono_nuevo": nuevo_poligono,
        "area_actual": area_actual,
        "area_nueva": area_nueva,
        "cambio_pct": cambio * 100,
        "lados": candidatos,
    }


async def _restaurar(archivo: str) -> None:
    with open(archivo, encoding="utf-8") as f:
        backup = json.load(f)
    async with AsyncSessionLocal() as db:
        restauradas = 0
        for fila in backup:
            geocerca = (
                await db.execute(select(Geocerca).where(Geocerca.id == fila["id"]))
            ).scalar_one_or_none()
            if geocerca is None:
                print(f"⚠ Geocerca id={fila['id']} ya no existe, se omite.")
                continue
            geocerca.poligono = fila["poligono_anterior"]
            geocerca.area_m2 = fila["area_m2_anterior"]
            restauradas += 1
        await db.commit()
    print(f"✅ Restauradas {restauradas} geocercas desde {archivo}")


async def main(args: argparse.Namespace) -> None:
    if args.restore:
        await _restaurar(args.restore)
        return

    ids_filtro = {int(x) for x in args.ids.split(",") if x.strip()} if args.ids else None

    async with AsyncSessionLocal() as db:
        query = select(Geocerca).where(Geocerca.activo.is_(True))
        if ids_filtro:
            query = query.where(Geocerca.id.in_(ids_filtro))
        geocercas = (await db.execute(query)).scalars().all()

        if not geocercas:
            print("No hay geocercas activas para procesar.")
            return

        resultados = []
        for g in geocercas:
            print(f"Consultando OSM para geocerca [{g.id}] {g.nombre} ...")
            try:
                resultados.append(_ajustar_geocerca(g))
            except RuntimeError as e:
                resultados.append({"estado": f"ERROR_OVERPASS: {e}", "geocerca": g})

        print("\n=== RESUMEN ===\n")
        aplicables = []
        for r in resultados:
            g = r["geocerca"]
            print(f"[{g.id}] {g.nombre}")
            if r["estado"] == "OK":
                print(f"    Área actual:  {r['area_actual']:,.2f} m²")
                print(f"    Área nueva:   {r['area_nueva']:,.2f} m²   ({r['cambio_pct']:+.1f}%)")
                for lado, c in r["lados"].items():
                    nombre, _punto, dist = c
                    print(f"    {lado.capitalize():10s} -> {nombre}  (dist. {dist:.0f} m)")
                print("    Estado: OK")
                aplicables.append(r)
            else:
                print(f"    Estado: {r['estado']}")
            print()

        if not args.commit:
            print("[DRY-RUN] Sin cambios aplicados. Use --commit --ids <lista> para aplicar.")
            return

        if not ids_filtro:
            print("ERROR: --commit requiere --ids con la lista de geocercas ya aprobadas en el preview.")
            return

        a_aplicar = [r for r in aplicables if r["geocerca"].id in ids_filtro]
        if not a_aplicar:
            print("Ninguna de las geocercas en --ids quedó en estado OK. Nada que aplicar.")
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = f"backup_geocercas_{timestamp}.json"
        backup = [
            {
                "id": r["geocerca"].id,
                "nombre": r["geocerca"].nombre,
                "poligono_anterior": r["geocerca"].poligono,
                "area_m2_anterior": float(r["geocerca"].area_m2),
            }
            for r in a_aplicar
        ]
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)
        print(f"Respaldo guardado en {backup_path}")

        for r in a_aplicar:
            g = r["geocerca"]
            g.poligono = r["poligono_nuevo"]
            g.area_m2 = r["area_nueva"]
        await db.commit()
        print(f"✅ {len(a_aplicar)} geocercas actualizadas.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Aplicar cambios (sin esto es dry-run)")
    parser.add_argument("--ids", help="Lista de IDs separados por coma (requerido con --commit)")
    parser.add_argument("--restore", help="Restaura desde un archivo de respaldo generado por --commit")
    asyncio.run(main(parser.parse_args()))
