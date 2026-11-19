from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.config import settings


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
    password: str = Field(max_length=100)  # reglas en app/auth/claves.py


class UsuarioAdminUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    nombre_completo: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    rol: str | None = Field(default=None, min_length=1, max_length=30)
    activo: bool | None = None


class UsuarioAdminPasswordReset(BaseModel):
    password: str = Field(max_length=100)  # reglas en app/auth/claves.py


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
    clave_cambiada_en: datetime | None = None
    debe_cambiar_clave: bool = False

    @computed_field
    @property
    def clave_vence_en(self) -> datetime | None:
        if self.clave_cambiada_en is None:
            return None
        return self.clave_cambiada_en + timedelta(days=settings.clave_vigencia_dias)


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
