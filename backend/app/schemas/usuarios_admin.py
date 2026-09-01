from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PaginaRead(BaseModel):
    key: str
    label: str
    path: str


class UsuarioAdminBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    nombre_completo: str = Field(min_length=1, max_length=100)
    email: str | None = None
    rol: str = Field(min_length=1, max_length=30)


class UsuarioAdminCreate(UsuarioAdminBase):
    password: str = Field(min_length=6, max_length=100)


class UsuarioAdminUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    rol: str | None = Field(default=None, min_length=1, max_length=30)
    activo: bool | None = None


class UsuarioAdminPasswordReset(BaseModel):
    password: str = Field(min_length=6, max_length=100)


class UsuarioAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    nombre_completo: str
    email: str | None
    rol: str
    activo: bool
    fecha_creacion: datetime | None = None
    ultimo_acceso: datetime | None = None


class RolCreate(BaseModel):
    nombre: str = Field(pattern=r"^[a-z][a-z0-9_]{2,29}$")
    descripcion: str | None = Field(default=None, max_length=200)
    paginas: list[str] = []


class RolUpdate(BaseModel):
    descripcion: str | None = Field(default=None, max_length=200)
    activo: bool | None = None
    paginas: list[str] | None = None


class RolRead(BaseModel):
    nombre: str
    descripcion: str | None
    activo: bool
    fecha_creacion: datetime | None = None
    paginas: list[str] = []
