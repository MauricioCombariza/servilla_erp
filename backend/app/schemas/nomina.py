from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class NominaEmpleadoBase(BaseModel):
    nombre_completo: str
    identificacion: str | None = None
    cargo: str | None = None
    salario_mensual: float = 0
    tiene_auxilio_transporte: bool = False
    auxilio_no_salarial: float = 0
    fecha_ingreso: date | None = None


class NominaEmpleadoCreate(NominaEmpleadoBase):
    pass


class NominaEmpleadoUpdate(BaseModel):
    nombre_completo: str | None = None
    identificacion: str | None = None
    cargo: str | None = None
    salario_mensual: float | None = None
    tiene_auxilio_transporte: bool | None = None
    auxilio_no_salarial: float | None = None
    fecha_ingreso: date | None = None
    activo: bool | None = None


class NominaEmpleadoRead(NominaEmpleadoBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activo: bool
    fecha_creacion: datetime | None = None


class NominaProvisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    empleado_id: int
    periodo_mes: int
    periodo_anio: int
    salario_base: float | None = None
    auxilio_transporte: float | None = None
    auxilio_no_salarial: float | None = None
    arl: float | None = None
    eps: float | None = None
    afp: float | None = None
    caja_compensacion: float | None = None
    prima: float | None = None
    cesantias: float | None = None
    int_cesantias: float | None = None
    vacaciones: float | None = None
    fecha_creacion: datetime | None = None


class CalcularProvisionesRequest(BaseModel):
    periodo_mes: int
    periodo_anio: int


class ResumenNomina(BaseModel):
    periodo_mes: int
    periodo_anio: int
    total_empleados: int
    total_salarios: float
    total_seguridad_social: float
    total_provisiones: float
    costo_total: float


class NominaParametroRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parametro: str
    valor: float
    descripcion: str | None = None
    vigencia_desde: date
    activo: bool


class NominaParametroUpdate(BaseModel):
    valor: float | None = None
    descripcion: str | None = None
    activo: bool | None = None
