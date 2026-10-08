from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_page
from app.database import get_db
from app.schemas.paquetes_despacho import (
    CargaDespachoResult,
    CorregirDireccionRequest,
    DestinoPaquete,
    PaqueteDespachoRead,
    PaqueteSinSector,
)
from app.services.excel_utils import XLSX_MEDIA_TYPE
from app.services.paquetes_despacho_service import (
    ColumnasFaltantesError,
    buscar_destino,
    corregir_direccion,
    exportar_csv,
    exportar_excel,
    guardar_paquetes,
    leer_excel_despacho,
    listar_paquetes,
)

router = APIRouter(prefix="/api/paquetes-despacho", tags=["paquetes-despacho"])
_auth = Depends(require_page("paquetes_despacho"))

# Una base de despacho diaria pesa unos cientos de KB; el límite solo evita abusos
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("/cargar", response_model=CargaDespachoResult)
async def cargar(
    file: UploadFile,
    f_emi: date = Form(...),
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    nombre = file.filename or ""
    if not nombre.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos Excel (.xlsx)")

    contenido = await file.read()
    if len(contenido) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máximo {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    try:
        paquetes = leer_excel_despacho(contenido)
    except ColumnasFaltantesError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "mensaje": str(e),
                "faltantes": e.faltantes,
                "columnas_archivo": e.columnas_archivo,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    resultado = await guardar_paquetes(db, paquetes, f_emi)
    direccion_por_serial = {(p.serial or "").strip(): p.direccion for p in paquetes}
    return CargaDespachoResult(
        archivo=nombre,
        f_emi=f_emi,
        total=resultado.total,
        creados=resultado.creados,
        reemplazados=resultado.reemplazados,
        sin_sector=[
            PaqueteSinSector(serial=s, direccion=direccion_por_serial.get(s))
            for s in resultado.seriales_sin_sector
        ],
    )


@router.get("/", response_model=list[PaqueteDespachoRead])
async def listar(
    f_emi: date,
    zona: str | None = None,
    solo_sin_sector: bool = False,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    return await listar_paquetes(db, f_emi, zona=zona, solo_sin_sector=solo_sin_sector)


@router.get("/destino/{serial}", response_model=DestinoPaquete)
async def destino(serial: str, db: AsyncSession = Depends(get_db), _=_auth):
    """Al escanear un paquete: últimos 4 dígitos, dirección, localidad y zona (Paso 2.6)."""
    return asdict(await buscar_destino(db, serial))


@router.patch("/{serial}/direccion", response_model=PaqueteDespachoRead)
async def corregir(
    serial: str,
    body: CorregirDireccionRequest,
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    paquete = await corregir_direccion(db, serial, body.direccion)
    if paquete is None:
        raise HTTPException(status_code=404, detail="Serial no encontrado")
    return paquete


@router.get("/exportar")
async def exportar(
    f_emi: date,
    formato: Literal["xlsx", "csv"] = "xlsx",
    db: AsyncSession = Depends(get_db),
    _=_auth,
):
    paquetes = await listar_paquetes(db, f_emi)
    nombre = f"paquetes_sectorizados_{f_emi.isoformat()}.{formato}"
    if formato == "csv":
        contenido, media_type = exportar_csv(paquetes), "text/csv"
    else:
        contenido, media_type = exportar_excel(paquetes, f_emi), XLSX_MEDIA_TYPE
    return Response(
        content=contenido,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
