from datetime import date, datetime

from pydantic import BaseModel


class EnlaceVistaRead(BaseModel):
    token: str
    fecha: date
    expira: datetime
    ruta: str  # la pantalla arma la URL (y el QR) con esta ruta


class PaqueteVistaRead(BaseModel):
    id: int
    ultimos_4: str
    direccion: str | None
    zona: str | None
    fuera_de_zona: bool
    aviso: str | None  # "Fuera de zona"
    fecha_escaneo: datetime


class PaquetesNuevosRead(BaseModel):
    paquetes: list[PaqueteVistaRead]
    ultimo_id: int  # enviarlo como `desde` en la siguiente consulta
