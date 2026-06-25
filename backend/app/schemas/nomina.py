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


class NominaParametroCreate(BaseModel):
    parametro: str
    valor: float
    descripcion: str | None = None
    vigencia_desde: date


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


class PagoOperativoCreate(BaseModel):
    tipo: str
    periodo_mes: int
    periodo_anio: int
    monto_total: float
    fecha_vencimiento: date | None = None
    observaciones: str | None = None


class PagoOperativoRead(PagoOperativoCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    estado: str
    fecha_pago: date | None = None
    created_at: datetime | None = None


class MarcarPagadoRequest(BaseModel):
    fecha_pago: date


class EmpleadoResumen(BaseModel):
    id: int
    nombre_completo: str
    cargo: str | None = None
    salario_mensual: float
    auxilio_no_salarial: float
    auxilio_transporte: float
    arl: float
    eps: float
    afp: float
    caja_compensacion: float
    prima: float
    cesantias: float
    int_cesantias: float
    vacaciones: float
    total_seguridad_social: float
    total_provisiones: float
    costo_total: float


class ResumenNominaDetallado(BaseModel):
    total_empleados: int
    empleados: list[EmpleadoResumen]
    total_salarios: float
    total_aux_no_salarial: float
    total_aux_transporte: float
    total_nomina_base: float
    total_arl: float
    total_eps: float
    total_afp: float
    total_caja: float
    total_seguridad_social: float
    total_prima: float
    total_cesantias: float
    total_int_cesantias: float
    total_vacaciones: float
    total_provisiones: float
    costo_total: float


class PeriodoHistorico(BaseModel):
    periodo_mes: int
    periodo_anio: int
    total_empleados: int
    costo_total: float


class RosterAddRequest(BaseModel):
    empleado_id: int
    mes: int
    anio: int


class RosterEntryRead(BaseModel):
    id: int
    empleado_id: int
    periodo_mes: int
    periodo_anio: int
    fecha_creacion: datetime | None = None
    empleado: NominaEmpleadoRead
