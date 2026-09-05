from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import shape
from shapely.errors import ShapelyError


def _validar_poligono(poligono: dict) -> dict:
    if poligono.get("type") != "Polygon":
        raise ValueError("El polígono debe ser un GeoJSON de tipo 'Polygon'")
    coordinates = poligono.get("coordinates")
    if not coordinates or not coordinates[0] or len(coordinates[0]) < 4:
        raise ValueError("El polígono debe tener al menos 3 vértices (anillo cerrado con 4 puntos)")
    if coordinates[0][0] != coordinates[0][-1]:
        raise ValueError("El anillo del polígono debe estar cerrado (primer punto = último punto)")
    try:
        geom = shape(poligono)
    except (ShapelyError, ValueError, TypeError) as e:
        raise ValueError(f"Polígono GeoJSON inválido: {e}")
    if not geom.is_valid:
        raise ValueError("El polígono no es geométricamente válido (bordes que se cruzan)")
    return poligono


class GeocercaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    poligono: dict
    area_m2: float
    activo: bool
    creado_por: str | None = None
    fecha_creacion: datetime
    fecha_actualizacion: datetime


class GeocercaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    poligono: dict

    @field_validator("poligono")
    @classmethod
    def validar_poligono(cls, v: dict) -> dict:
        return _validar_poligono(v)


class GeocercaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    activo: bool | None = None
