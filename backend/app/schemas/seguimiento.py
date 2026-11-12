from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Prioridad = Literal["baja", "media", "alta", "critica"]
EstadoTarea = Literal["pendiente", "en_progreso", "completada", "cancelada"]
CategoriaProyecto = Literal["seguridad_informacion", "nuevo_proyecto", "operativo", "otro"]
EstadoProyecto = Literal["planeado", "en_curso", "pausado", "completado", "cancelado"]
Frecuencia = Literal["diaria", "semanal", "mensual"]


# ── Tareas ──────────────────────────────────────────────────────────────────

class TareaCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    proyecto_id: int | None = None
    responsable_id: int | None = None  # None = el usuario actual
    fecha_programada: date
    fecha_limite: date | None = None
    prioridad: Prioridad = "media"
    esfuerzo_horas: Decimal | None = Field(default=None, ge=0, le=9999)


class TareaUpdate(BaseModel):
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descripcion: str | None = None
    proyecto_id: int | None = None
    responsable_id: int | None = None
    fecha_programada: date | None = None
    fecha_limite: date | None = None
    prioridad: Prioridad | None = None
    estado: EstadoTarea | None = None
    esfuerzo_horas: Decimal | None = Field(default=None, ge=0, le=9999)


class TareaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    descripcion: str | None
    proyecto_id: int | None
    proyecto_nombre: str | None = None
    recurrente_id: int | None
    responsable_id: int | None
    responsable_nombre: str | None = None
    creado_por: int | None
    fecha_programada: date
    fecha_limite: date | None
    prioridad: str
    estado: str
    esfuerzo_horas: Decimal | None
    completada_en: datetime | None
    anio_iso: int
    semana_iso: int
    demorada: bool
    dias_atraso: int


class DiaSemana(BaseModel):
    fecha: date
    tareas: list[TareaOut]


class SemanaDetalle(BaseModel):
    anio: int
    semana: int
    lunes: date
    domingo: date
    dias: list[DiaSemana]


class SemanaResumen(BaseModel):
    anio: int
    semana: int
    lunes: date
    domingo: date
    total: int
    completadas: int
    pendientes: int
    demoradas: int
    es_actual: bool


class SemanasAnio(BaseModel):
    anio: int
    semana_actual: int | None
    semanas: list[SemanaResumen]


# ── Proyectos ───────────────────────────────────────────────────────────────

class ProyectoCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    descripcion: str | None = None
    categoria: CategoriaProyecto = "otro"
    responsable_id: int | None = None
    fecha_inicio: date
    fecha_fin: date
    estado: EstadoProyecto = "planeado"
    color: str | None = Field(default=None, max_length=9)

    @model_validator(mode="after")
    def _rango(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior o igual a fecha_inicio")
        return self


class ProyectoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    descripcion: str | None = None
    categoria: CategoriaProyecto | None = None
    responsable_id: int | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    estado: EstadoProyecto | None = None
    color: str | None = Field(default=None, max_length=9)


class ProyectoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None
    categoria: str
    responsable_id: int | None
    responsable_nombre: str | None = None
    fecha_inicio: date
    fecha_fin: date
    estado: str
    color: str | None
    total_tareas: int = 0
    completadas: int = 0
    demoradas: int = 0
    avance: float = 0.0  # 0..100


class ProyectoSemana(BaseModel):
    anio: int
    semana: int
    lunes: date
    total: int
    completadas: int
    demoradas: int


class ProyectoDetalle(ProyectoOut):
    semanas: list[ProyectoSemana]
    tareas: list[TareaOut]


class TareaDistribuir(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    esfuerzo_horas: Decimal | None = Field(default=None, ge=0, le=9999)
    prioridad: Prioridad = "media"
    responsable_id: int | None = None
    fecha_programada: date | None = None  # fijada a mano: no se reparte


class DistribuirRequest(BaseModel):
    tareas: list[TareaDistribuir] = Field(min_length=1, max_length=500)
    fecha_inicio: date | None = None  # default: rango del proyecto
    fecha_fin: date | None = None
    secuencial: bool = False
    aplicar: bool = False


class PropuestaTarea(BaseModel):
    titulo: str
    descripcion: str | None
    esfuerzo_horas: Decimal | None
    prioridad: str
    responsable_id: int | None
    fecha_programada: date
    anio_iso: int
    semana_iso: int


class DistribuirResponse(BaseModel):
    aplicado: bool
    semanas: int
    propuesta: list[PropuestaTarea]
    carga_por_semana: dict[str, float]  # "2026-W46" -> horas (o nº de tareas si no hay esfuerzo)


# ── Recurrentes ─────────────────────────────────────────────────────────────

class RecurrenteBase(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str | None = None
    proyecto_id: int | None = None
    responsable_id: int | None = None
    prioridad: Prioridad = "media"
    frecuencia: Frecuencia
    dias_semana: list[int] | None = None
    dia_mes: int | None = Field(default=None, ge=1, le=31)
    fecha_inicio: date
    fecha_fin: date | None = None
    saltar_festivos: bool = True
    activa: bool = True

    @model_validator(mode="after")
    def _validar(self):
        if self.dias_semana is not None:
            if any(d < 1 or d > 7 for d in self.dias_semana):
                raise ValueError("dias_semana usa ISO: 1=lunes … 7=domingo")
            self.dias_semana = sorted(set(self.dias_semana))
        if self.frecuencia == "semanal" and not self.dias_semana:
            raise ValueError("frecuencia semanal requiere dias_semana")
        if self.frecuencia == "mensual" and self.dia_mes is None:
            raise ValueError("frecuencia mensual requiere dia_mes")
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior o igual a fecha_inicio")
        return self


class RecurrenteCreate(RecurrenteBase):
    pass


class RecurrenteUpdate(RecurrenteBase):
    pass


class RecurrenteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    titulo: str
    descripcion: str | None
    proyecto_id: int | None
    responsable_id: int | None
    prioridad: str
    frecuencia: str
    dias_semana: list[int] | None
    dia_mes: int | None
    fecha_inicio: date
    fecha_fin: date | None
    saltar_festivos: bool
    activa: bool
    generado_hasta: date | None


# ── Otros ───────────────────────────────────────────────────────────────────

class Responsable(BaseModel):
    id: int
    nombre: str
    username: str


class ResumenProyecto(BaseModel):
    id: int
    nombre: str
    categoria: str
    avance: float
    demoradas: int


class ResumenSeguimiento(BaseModel):
    hoy: date
    anio_iso: int
    semana_iso: int
    tareas_hoy: int
    tareas_manana: int
    semana_total: int
    semana_completadas: int
    demoradas: int
    proyectos: list[ResumenProyecto]
