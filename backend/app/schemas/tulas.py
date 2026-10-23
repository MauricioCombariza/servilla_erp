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


class TulaAbierta(TulaRead):
    """Respuesta al abrir: qué dijo iMile del total (Paso 2.3), si se le preguntó."""
    imile_total: str | None = None


class TulaSerialRead(BaseModel):
    serial: str
    en_tabla: bool
    zona: str | None
    localidad: str | None = None  # de la base de despacho: es lo que se muestra si va fuera de zona
    fecha_escaneo: datetime
    imile_estado: str | None  # ok | repetido | bloqueado | error | sin_confirmar | omitido
    imile_mensaje: str | None


class TulaDetalle(TulaRead):
    seriales: list[TulaSerialRead]
    # Contra lo que iMile dice que trae la tula (Paso 2.3); None si iMile no lo dijo
    faltantes: list[str] | None = None
    no_esperados: list[str] | None = None


class BaseDelDia(BaseModel):
    paquetes_hoy: int  # paquetes de la base de despacho subidos hoy (hora de Bogotá)


class ResumenDelDia(BaseModel):
    fecha: date
    tulas: int  # tulas abiertas en el día, de todos los usuarios
    paquetes: int  # seriales leídos en esas tulas, cada uno contado una sola vez


class SerialSinLeer(BaseModel):
    serial: str
    ultimos_4: str
    zona: str | None
    localidad: str | None
    direccion: str | None


class SinLeerDelDia(BaseModel):
    fecha: date
    total: int  # paquetes de la base del día que no se han leído en ninguna tula
    seriales: list[SerialSinLeer]


class AbrirTulaRequest(BaseModel):
    codigo: str | None = None  # vacío → "Sin etiqueta"
    total_esperado: int | None = Field(default=None, ge=0)  # lo llenará iMile (Paso 2.3)
    cerrar_anterior: bool = False


class FijarTotalRequest(BaseModel):
    total_esperado: int | None = Field(default=None, ge=0)


class EscanearSerialRequest(BaseModel):
    serial: str = Field(min_length=1)


class IngresoImile(BaseModel):
    estado: str | None  # ok | repetido | bloqueado | error | sin_confirmar | omitido
    mensaje: str | None


class EscaneoResult(BaseModel):
    tula: TulaRead
    destino: DestinoPaquete
    ya_escaneado: bool
    imile: IngresoImile
