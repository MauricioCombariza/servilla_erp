from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.seguimiento import (
    CategoriaProyecto,
    DistribuirRequest,
    DistribuirResponse,
    EstadoProyecto,
    EstadoTarea,
    ProyectoCreate,
    ProyectoDetalle,
    ProyectoOut,
    ProyectoUpdate,
    RecurrenteCreate,
    RecurrenteOut,
    RecurrenteUpdate,
    Responsable,
    ResumenSeguimiento,
    SemanaDetalle,
    SemanasAnio,
    TareaCreate,
    TareaOut,
    TareaUpdate,
)
from app.services import seguimiento_service as svc

router = APIRouter(prefix="/api/seguimiento", tags=["seguimiento"])
_auth = Depends(require_page("seguimiento_tareas"))

MAX_RANGO_DIAS = 400


@router.get("/responsables", response_model=list[Responsable])
async def responsables(db: AsyncSession = Depends(get_db), _=_auth):
    return await svc.listar_responsables(db)


@router.get("/resumen", response_model=ResumenSeguimiento)
async def resumen(db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.resumen(db, user, svc.hoy_bogota())


# ── Tareas ──────────────────────────────────────────────────────────────────

@router.get("/tareas/hoy", response_model=list[TareaOut])
async def tareas_hoy(
    responsable_id: int | None = None, proyecto_id: int | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    hoy = svc.hoy_bogota()
    return await svc.listar_tareas(db, user, hoy, hoy, hoy, responsable_id, proyecto_id)


@router.get("/tareas/manana", response_model=list[TareaOut])
async def tareas_manana(
    responsable_id: int | None = None, proyecto_id: int | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    hoy = svc.hoy_bogota()
    manana = hoy + timedelta(days=1)
    return await svc.listar_tareas(db, user, manana, manana, hoy, responsable_id, proyecto_id)


@router.get("/tareas/demoradas", response_model=list[TareaOut])
async def tareas_demoradas(
    responsable_id: int | None = None, proyecto_id: int | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    return await svc.listar_demoradas(db, user, svc.hoy_bogota(), responsable_id, proyecto_id)


@router.get("/tareas", response_model=list[TareaOut])
async def tareas(
    desde: date, hasta: date,
    responsable_id: int | None = None, proyecto_id: int | None = None,
    estado: EstadoTarea | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    if hasta < desde or (hasta - desde).days > MAX_RANGO_DIAS:
        raise HTTPException(status_code=400, detail=f"Rango inválido (máximo {MAX_RANGO_DIAS} días)")
    return await svc.listar_tareas(db, user, desde, hasta, svc.hoy_bogota(), responsable_id, proyecto_id, estado)


@router.post("/tareas", response_model=TareaOut, status_code=status.HTTP_201_CREATED)
async def crear_tarea(body: TareaCreate, db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.crear_tarea(db, user, body.model_dump(), svc.hoy_bogota())


@router.patch("/tareas/{tarea_id}", response_model=TareaOut)
async def actualizar_tarea(tarea_id: int, body: TareaUpdate, db: AsyncSession = Depends(get_db),
                           user: dict = _auth):
    return await svc.actualizar_tarea(db, user, tarea_id, body.model_dump(exclude_unset=True), svc.hoy_bogota())


@router.post("/tareas/{tarea_id}/completar", response_model=TareaOut)
async def completar(tarea_id: int, db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.cambiar_estado(db, user, tarea_id, "completada", svc.hoy_bogota())


@router.post("/tareas/{tarea_id}/reabrir", response_model=TareaOut)
async def reabrir(tarea_id: int, db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.cambiar_estado(db, user, tarea_id, "pendiente", svc.hoy_bogota())


@router.delete("/tareas/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_tarea(tarea_id: int, db: AsyncSession = Depends(get_db), user: dict = _auth):
    await svc.eliminar_tarea(db, user, tarea_id)


# ── Semanas ─────────────────────────────────────────────────────────────────

@router.get("/semanas", response_model=SemanasAnio)
async def semanas(
    anio: int | None = Query(default=None, ge=2000, le=2100),
    responsable_id: int | None = None, proyecto_id: int | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    hoy = svc.hoy_bogota()
    return await svc.semanas_anio(db, user, anio or hoy.isocalendar().year, hoy, responsable_id, proyecto_id)


@router.get("/semanas/{anio}/{semana}", response_model=SemanaDetalle)
async def semana(
    anio: int, semana: int,
    responsable_id: int | None = None, proyecto_id: int | None = None,
    db: AsyncSession = Depends(get_db), user: dict = _auth,
):
    return await svc.semana_detalle(db, user, anio, semana, svc.hoy_bogota(), responsable_id, proyecto_id)


# ── Proyectos ───────────────────────────────────────────────────────────────

@router.get("/proyectos", response_model=list[ProyectoOut])
async def proyectos(
    categoria: CategoriaProyecto | None = None, estado: EstadoProyecto | None = None,
    db: AsyncSession = Depends(get_db), _=_auth,
):
    return await svc.listar_proyectos(db, svc.hoy_bogota(), categoria, estado)


@router.post("/proyectos", response_model=ProyectoDetalle, status_code=status.HTTP_201_CREATED)
async def crear_proyecto(body: ProyectoCreate, db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.crear_proyecto(db, user, body.model_dump(), svc.hoy_bogota())


@router.get("/proyectos/{proyecto_id}", response_model=ProyectoDetalle)
async def proyecto(proyecto_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    return await svc.detalle_proyecto(db, proyecto_id, svc.hoy_bogota())


@router.patch("/proyectos/{proyecto_id}", response_model=ProyectoDetalle)
async def actualizar_proyecto(proyecto_id: int, body: ProyectoUpdate, db: AsyncSession = Depends(get_db),
                              user: dict = _auth):
    return await svc.actualizar_proyecto(db, user, proyecto_id, body.model_dump(exclude_unset=True),
                                         svc.hoy_bogota())


@router.delete("/proyectos/{proyecto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_proyecto(proyecto_id: int, db: AsyncSession = Depends(get_db), user: dict = _auth):
    await svc.eliminar_proyecto(db, user, proyecto_id)


@router.post("/proyectos/{proyecto_id}/distribuir", response_model=DistribuirResponse)
async def distribuir(proyecto_id: int, body: DistribuirRequest, db: AsyncSession = Depends(get_db),
                     user: dict = _auth):
    return await svc.distribuir_proyecto(db, user, proyecto_id, body.model_dump(), svc.hoy_bogota())


# ── Recurrentes ─────────────────────────────────────────────────────────────

@router.get("/recurrentes", response_model=list[RecurrenteOut])
async def recurrentes(db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.listar_recurrentes(db, user)


@router.post("/recurrentes", response_model=RecurrenteOut, status_code=status.HTTP_201_CREATED)
async def crear_recurrente(body: RecurrenteCreate, db: AsyncSession = Depends(get_db), user: dict = _auth):
    return await svc.crear_recurrente(db, user, body.model_dump())


@router.put("/recurrentes/{rec_id}", response_model=RecurrenteOut)
async def actualizar_recurrente(rec_id: int, body: RecurrenteUpdate, db: AsyncSession = Depends(get_db),
                                user: dict = _auth):
    return await svc.actualizar_recurrente(db, user, rec_id, body.model_dump(), svc.hoy_bogota())


@router.delete("/recurrentes/{rec_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_recurrente(rec_id: int, db: AsyncSession = Depends(get_db), user: dict = _auth):
    await svc.eliminar_recurrente(db, user, rec_id, svc.hoy_bogota())
