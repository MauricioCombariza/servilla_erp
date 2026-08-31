from pydantic import BaseModel


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


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMe(BaseModel):
    id: int
    username: str
    nombre_completo: str
    email: str | None
    rol: str
    activo: bool
    page_keys: list[str] = []
