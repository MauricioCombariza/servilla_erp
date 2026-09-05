from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

# UTM zona 18N (EPSG:32618): zona correcta para Bogotá, permite obtener área en
# metros cuadrados reales en vez de una aproximación esférica sobre grados.
_transformer = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)


def calcular_area_m2(poligono_geojson: dict) -> float:
    geom = shape(poligono_geojson)
    geom_proyectada = transform(_transformer.transform, geom)
    return round(geom_proyectada.area, 2)
