from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class RegistroHorasBase(BaseModel):
    personal_id: int
    orden_id: int | None = None
    fecha: date
    horas_trabajadas: float
    tarifa_hora: float
    tipo_trabajo: str
    observaciones: str | None = None


class RegistroHorasCreate(RegistroHorasBase):
    pass


class RegistroHorasUpdate(BaseModel):
    fecha: date | None = None
    horas_trabajadas: float | None = None
    tarifa_hora: float | None = None
    tipo_trabajo: str | None = None
    observaciones: str | None = None


class RegistroHorasRead(RegistroHorasBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: float | None = None
    aprobado: bool
    aprobado_por: int | None = None
    fecha_aprobacion: datetime | None = None
    liquidado: bool
    fecha_creacion: datetime | None = None


class RegistroLaboresBase(BaseModel):
    personal_id: int
    orden_id: int | None = None
    fecha: date
    tipo_labor: str
    cantidad: int
    tarifa_unitaria: float
    observaciones: str | None = None


class RegistroLaboresCreate(RegistroLaboresBase):
    pass


class RegistroLaboresUpdate(BaseModel):
    fecha: date | None = None
    tipo_labor: str | None = None
    cantidad: int | None = None
    tarifa_unitaria: float | None = None
    observaciones: str | None = None


class RegistroLaboresRead(RegistroLaboresBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: float | None = None
    aprobado: bool
    aprobado_por: int | None = None
    fecha_aprobacion: datetime | None = None
    liquidado: bool
    fecha_creacion: datetime | None = None


class ResumenLabores(BaseModel):
    personal_id: int
    nombre_completo: str
    total_horas: float
    total_horas_monto: float
    total_labores: int
    total_labores_monto: float
    total_general: float
