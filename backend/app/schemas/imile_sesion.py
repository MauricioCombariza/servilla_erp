from datetime import datetime

from pydantic import BaseModel


class EstadoSesionImileRead(BaseModel):
    credenciales_configuradas: bool
    navegador_abierto: bool
    conectado: bool
    idioma: str | None
    ultimo_ingreso: datetime | None
