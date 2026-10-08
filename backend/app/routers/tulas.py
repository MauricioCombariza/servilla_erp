from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.tulas import (
    AbrirTulaRequest,
    EscanearSerialRequest,
    EscaneoResult,
    IngresoImile,
    TulaDetalle,
    TulaRead,
    TulaSerialRead,
)
from app.services.tulas_service import (
    ResumenTula,
    TulaAbiertaError,
    TulaCerradaError,
    TulaNoEncontradaError,
    abrir_tula,
    cerrar_tula,
    listar_tulas,
    obtener_tula,
    registrar_serial,
    reintentar_imile,
    resumen,
    seriales_de,
    tula_abierta,
)

router = APIRouter(prefix="/api/tulas", tags=["tulas"])
_auth = Depends(require_page("escaneo_tulas"))


def _tula_read(r: ResumenTula) -> TulaRead:
    t = r.tula
    return TulaRead(
        id=t.id, codigo=t.codigo, sin_etiqueta=t.sin_etiqueta, total_esperado=t.total_esperado,
        estado=t.estado, usuario=t.usuario, fecha=t.fecha, fecha_apertura=t.fecha_apertura,
        fecha_cierre=t.fecha_cierre, leidos=r.leidos, contador=r.contador, diferencia=r.diferencia,
    )


def _serial_read(s) -> TulaSerialRead:
    return TulaSerialRead(
        serial=s.serial, en_tabla=s.en_tabla, zona=s.zona, fecha_escaneo=s.fecha_escaneo,
        imile_estado=s.imile_estado, imile_mensaje=s.imile_mensaje,
    )


async def _detalle(db: AsyncSession, r: ResumenTula) -> TulaDetalle:
    seriales = [
        _serial_read(s) for s in await seriales_de(db, r.tula.id)
    ]
    return TulaDetalle(**_tula_read(r).model_dump(), seriales=seriales)


@router.post("/", response_model=TulaRead, status_code=201)
async def abrir(
    body: AbrirTulaRequest,
    db: AsyncSession = Depends(get_db),
    usuario: dict = _auth,
):
    """Abre una tula (codigo vacío = "Sin etiqueta"). Si hay otra abierta responde 409
    con la tula abierta; la pantalla pregunta y reenvía con cerrar_anterior=true."""
    try:
        tula = await abrir_tula(
            db, usuario["username"], body.codigo, body.total_esperado, body.cerrar_anterior
        )
    except TulaAbiertaError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "mensaje": str(e),
                "tula_abierta": _tula_read(await resumen(db, e.tula)).model_dump(mode="json"),
            },
        )
    return _tula_read(await resumen(db, tula))


@router.get("/abierta", response_model=TulaRead | None)
async def abierta(db: AsyncSession = Depends(get_db), usuario: dict = _auth):
    """La tula abierta del usuario (para retomar si se recarga la pantalla), o null."""
    tula = await tula_abierta(db, usuario["username"])
    return _tula_read(await resumen(db, tula)) if tula else None


@router.post("/{tula_id}/seriales", response_model=EscaneoResult)
async def escanear(
    tula_id: int,
    body: EscanearSerialRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    """Lee un paquete de la tula: lo cuenta (si no estaba ya), lo ingresa en iMile (2.5)
    y devuelve su destino (2.6)."""
    try:
        r = await registrar_serial(db, tula_id, body.serial)
    except TulaNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TulaCerradaError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return EscaneoResult(
        tula=_tula_read(r.resumen),
        destino=asdict(r.destino),
        ya_escaneado=r.ya_escaneado,
        imile=IngresoImile(estado=r.imile_estado, mensaje=r.imile_mensaje),
    )


@router.post("/{tula_id}/seriales/{serial}/reintentar-imile", response_model=TulaSerialRead)
async def reintentar(tula_id: int, serial: str, db: AsyncSession = Depends(get_db), _=_auth):
    """Vuelve a ingresar en iMile un paquete ya leído (si la primera vez falló)."""
    try:
        return _serial_read(await reintentar_imile(db, tula_id, serial))
    except TulaNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{tula_id}/cerrar", response_model=TulaDetalle)
async def cerrar(tula_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    try:
        r = await cerrar_tula(db, tula_id)
    except TulaNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _detalle(db, r)


@router.get("/{tula_id}", response_model=TulaDetalle)
async def detalle(tula_id: int, db: AsyncSession = Depends(get_db), _=_auth):
    try:
        tula = await obtener_tula(db, tula_id)
    except TulaNoEncontradaError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return await _detalle(db, await resumen(db, tula))


@router.get("/", response_model=list[TulaRead])
async def listar(fecha: date, db: AsyncSession = Depends(get_db), _=_auth):
    return [_tula_read(r) for r in await listar_tulas(db, fecha)]
