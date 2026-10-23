"""Asignación de zonas y seriales a mensajeros (Pasos 3.1 y 3.2).

Las mismas acciones están disponibles de dos formas (decisión del usuario 2026-10-08):
  - /api/asignacion-zonas/…        con sesión del ERP (administrador / logística)
  - /api/asignacion-qr/{token}/…   sin sesión, con el QR del día que genera quien escanea;
                                   lo hecho así queda registrado como "qr:<usuario del enlace>"
"""
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.asignacion_zonas import (
    AsignacionSerialRead,
    EnvioImileRead,
    NombreImileRequest,
    AsignarSerialRequest,
    AsignarZonasRequest,
    MensajeroRead,
    SerialDelMensajeroRead,
    TotalMensajeroRead,
    ZonaDelDiaRead,
    ZonasMensajeroRead,
)
from app.services.asignacion_imile_service import (
    EnvioEnCursoError,
    ImileAsignacionApagadaError,
    envio_de,
    fijar_nombre_imile,
    iniciar_envio,
    seriales_con_imile,
)
from app.services.asignacion_zonas_service import (
    MensajeroNoEncontradoError,
    ZonasInvalidasError,
    ZonasOcupadasError,
    asignar_serial,
    asignar_zonas,
    buscar_mensajero,
    hoy,
    quitar_serial,
    tablero,
    totales_por_mensajero,
    zonas_de,
)
from app.services.vista_zonas_service import EnlaceInvalidoError, validar_enlace

_auth = Depends(require_page("asignacion_zonas"))


async def _usuario_qr(token: str, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        enlace = await validar_enlace(db, token)
    except EnlaceInvalidoError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"username": f"qr:{enlace.usuario}"}


_auth_qr = Depends(_usuario_qr)


async def _mensajero_o_404(db: AsyncSession, codigo: str):
    try:
        return await buscar_mensajero(db, codigo)
    except MensajeroNoEncontradoError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _envio_read(e) -> EnvioImileRead:
    return EnvioImileRead(nombre_imile=e.nombre_imile, total=e.total, hechos=e.hechos, asignados=e.asignados,
                          fallidos=e.fallidos, en_curso=e.en_curso, error=e.error)


def _crear_router(prefix: str, auth, tag: str) -> APIRouter:
    r = APIRouter(prefix=prefix, tags=[tag])

    @r.get("/mensajero/{codigo}", response_model=ZonasMensajeroRead)
    async def mensajero(codigo: str, fecha: date | None = None,
                        db: AsyncSession = Depends(get_db), _=auth):
        """Paso 3.1: código → nombre del mensajero, con las zonas que ya tiene en el día."""
        m = await _mensajero_o_404(db, codigo)
        fecha = fecha or hoy()
        return ZonasMensajeroRead(codigo=m.codigo, nombre=m.nombre, fecha=fecha, nombre_imile=m.nombre_imile,
                                  zonas=await zonas_de(db, codigo, fecha))

    @r.put("/mensajero/{codigo}", response_model=ZonasMensajeroRead)
    async def asignar(codigo: str, body: AsignarZonasRequest,
                      db: AsyncSession = Depends(get_db), usuario: dict = auth):
        """Paso 3.2: deja al mensajero con exactamente esas zonas en el día. Si alguna la
        tiene otro mensajero responde 409 con los choques; con reasignar=true se le pasa."""
        m = await _mensajero_o_404(db, codigo)
        fecha = body.fecha or hoy()
        try:
            zonas = await asignar_zonas(db, codigo, body.zonas, fecha, usuario["username"], body.reasignar)
        except ZonasInvalidasError as e:
            raise HTTPException(status_code=400, detail={"mensaje": str(e), "zonas": e.zonas})
        except ZonasOcupadasError as e:
            raise HTTPException(status_code=409, detail={
                "mensaje": str(e),
                "choques": [{"zona": c.zona, "codigo": c.codigo, "nombre": c.nombre} for c in e.choques],
            })
        return ZonasMensajeroRead(codigo=m.codigo, nombre=m.nombre, fecha=fecha, zonas=zonas,
                                  nombre_imile=m.nombre_imile)

    @r.get("/", response_model=list[ZonaDelDiaRead])
    async def tablero_del_dia(fecha: date | None = None, db: AsyncSession = Depends(get_db), _=auth):
        """Las 33 zonas del día con su mensajero y los paquetes leídos en cada una."""
        return [
            ZonaDelDiaRead(
                zona=z.zona,
                paquetes_leidos=z.paquetes_leidos,
                mensajero=MensajeroRead(codigo=z.mensajero.codigo, nombre=z.mensajero.nombre)
                if z.mensajero else None,
            )
            for z in await tablero(db, fecha or hoy())
        ]

    @r.get("/mensajeros", response_model=list[TotalMensajeroRead])
    async def totales(fecha: date | None = None, db: AsyncSession = Depends(get_db), _=auth):
        """Cuántos paquetes lleva cada mensajero en el día (por sus zonas + reasignados)."""
        return [asdict(t) for t in await totales_por_mensajero(db, fecha or hoy())]

    @r.post("/mensajero/{codigo}/seriales", response_model=AsignacionSerialRead)
    async def asignar_un_serial(codigo: str, body: AsignarSerialRequest,
                                db: AsyncSession = Depends(get_db), usuario: dict = auth):
        """Con el mensajero ya ingresado, cada serial escaneado queda asignado a él aunque
        su zona sea de otro mensajero. Devuelve a quién lo tenía."""
        await _mensajero_o_404(db, codigo)
        return asdict(await asignar_serial(db, codigo, body.serial, body.fecha or hoy(), usuario["username"]))

    @r.delete("/mensajero/{codigo}/seriales/{serial}", status_code=204)
    async def quitar_un_serial(codigo: str, serial: str, fecha: date | None = None,
                               db: AsyncSession = Depends(get_db), _=auth):
        """Deshace la reasignación: el paquete vuelve al mensajero de su zona."""
        await _mensajero_o_404(db, codigo)
        if not await quitar_serial(db, codigo, serial, fecha or hoy()):
            raise HTTPException(status_code=404, detail="Ese serial no estaba reasignado a este mensajero")

    @r.get("/mensajero/{codigo}/seriales", response_model=list[SerialDelMensajeroRead])
    async def seriales(codigo: str, fecha: date | None = None,
                       db: AsyncSession = Depends(get_db), _=auth):
        """Los paquetes que le tocan al mensajero en el día (por sus zonas + reasignados),
        con lo que pasó con cada uno en iMile (Paso 3.3)."""
        await _mensajero_o_404(db, codigo)
        return [asdict(s) for s in await seriales_con_imile(db, codigo, fecha or hoy())]

    @r.put("/mensajero/{codigo}/nombre-imile", response_model=ZonasMensajeroRead)
    async def nombre_imile(codigo: str, body: NombreImileRequest, fecha: date | None = None,
                           db: AsyncSession = Depends(get_db), _=auth):
        """Paso 3.3: el nombre con que el mensajero aparece en iMile, si no es igual al del ERP."""
        await _mensajero_o_404(db, codigo)
        m = await fijar_nombre_imile(db, codigo, body.nombre_imile)
        fecha = fecha or hoy()
        return ZonasMensajeroRead(codigo=m.codigo, nombre=m.nombre, fecha=fecha, nombre_imile=m.nombre_imile,
                                  zonas=await zonas_de(db, codigo, fecha))

    @r.post("/mensajero/{codigo}/imile", response_model=EnvioImileRead, status_code=202)
    async def asignar_en_imile(codigo: str, fecha: date | None = None,
                               db: AsyncSession = Depends(get_db), usuario: dict = auth):
        """Paso 3.3: manda a iMile ("Asignar repartidor"), en segundo plano, los paquetes del
        mensajero que todavía no quedaron asignados a él. El avance se consulta con GET."""
        await _mensajero_o_404(db, codigo)
        try:
            envio = await iniciar_envio(db, codigo, fecha or hoy(), usuario["username"])
        except EnvioEnCursoError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ImileAsignacionApagadaError as e:
            raise HTTPException(status_code=503, detail=str(e))
        return _envio_read(envio)

    @r.get("/mensajero/{codigo}/imile", response_model=EnvioImileRead | None)
    async def envio_imile(codigo: str, fecha: date | None = None, db: AsyncSession = Depends(get_db), _=auth):
        """Avance del último envío a iMile del mensajero en el día (None si no se ha mandado)."""
        envio = envio_de(await _mensajero_o_404(db, codigo), fecha or hoy())
        return _envio_read(envio) if envio else None

    return r


router = _crear_router("/api/asignacion-zonas", _auth, "asignacion-zonas")
router_qr = _crear_router("/api/asignacion-qr/{token}", _auth_qr, "asignacion-qr")
