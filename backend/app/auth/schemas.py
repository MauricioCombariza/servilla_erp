from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    nombre_completo: str
    page_keys: list[str] = []
    debe_cambiar_clave: bool = False
    dias_para_vencer: int | None = None
    # El navegador cierra la sesión tras estos minutos sin que la persona haga nada
    inactividad_minutos: int = 10


class CambioClaveRequest(BaseModel):
    clave_actual: str
    clave_nueva: str = Field(max_length=100)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
    motivo: Literal["salida", "inactividad"] = "salida"


class UserMe(BaseModel):
    id: int
    username: str
    nombre_completo: str
    email: str | None
    rol: str
    activo: bool
    page_keys: list[str] = []
    dias_para_vencer: int | None = None
