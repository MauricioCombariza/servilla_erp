from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.paquetes_despacho import DestinoPaquete


class TulaRead(BaseModel):
    id: int
    codigo: str | None
    sin_etiqueta: bool
    total_esperado: int | None
    estado: str
    usuario: str
    fecha: date
    fecha_apertura: datetime
    fecha_cierre: datetime | None
    leidos: int
    contador: int  # lo que se muestra arriba a la izquierda (Paso 2.4)
    diferencia: int | None  # positiva: faltan · negativa: sobran


class TulaSerialRead(BaseModel):
    serial: str
    en_tabla: bool
    zona: str | None
    fecha_escaneo: datetime


class TulaDetalle(TulaRead):
    seriales: list[TulaSerialRead]


class AbrirTulaRequest(BaseModel):
    codigo: str | None = None  # vacío → "Sin etiqueta"
    total_esperado: int | None = Field(default=None, ge=0)  # lo llenará iMile (Paso 2.3)
    cerrar_anterior: bool = False


class EscanearSerialRequest(BaseModel):
    serial: str = Field(min_length=1)


class EscaneoResult(BaseModel):
    tula: TulaRead
    destino: DestinoPaquete
    ya_escaneado: bool
