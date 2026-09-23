import base64
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.auth.dependencies import require_page
from app.schemas.generar_dat import GenerarDatResult, SerialError
from app.services.bases_web import fetch_histo_orden
from app.services.generar_dat_service import construir_excel_errores, generar_dat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generar-dat", tags=["generar-dat"])
_auth = Depends(require_page("generar_dat"))

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ARCHIVOS = 5


def _normalizar_fecha(fecha: str) -> str:
    """Acepta AAAA-MM-DD (input date) o AAAAMMDD y devuelve AAAAMMDD."""
    fecha = fecha.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(fecha, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Fecha inicial inválida (use AAAA-MM-DD)")


@router.post("", response_model=GenerarDatResult)
async def generar(
    orden: str = Form(...),
    fecha_ini: str = Form(...),
    files: list[UploadFile] = File(...),
    _=_auth,
):
    orden = orden.strip()
    if not re.fullmatch(r"\d{1,10}", orden):
        raise HTTPException(status_code=400, detail="Número de orden inválido")
    fecha = _normalizar_fecha(fecha_ini)

    if not files:
        raise HTTPException(status_code=400, detail="Sube al menos un archivo Excel")
    if len(files) > MAX_ARCHIVOS:
        raise HTTPException(status_code=400, detail=f"Máximo {MAX_ARCHIVOS} archivos")

    archivos: list[tuple[str, bytes]] = []
    for f in files:
        nombre = f.filename or "archivo"
        if not nombre.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail=f"{nombre}: solo se aceptan archivos .xlsx")
        contenido = await f.read()
        if len(contenido) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{nombre}: demasiado grande (máximo {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        archivos.append((nombre, contenido))

    try:
        filas_histo = await fetch_histo_orden(orden)
    except Exception as exc:
        logger.error("Error consultando la orden %s en bases_web.histo: %s", orden, exc)
        raise HTTPException(status_code=502, detail="No se pudo consultar bases_web")

    try:
        resultado = generar_dat(orden, fecha, archivos, filas_histo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    errores_b64 = None
    nombre_errores = None
    if resultado.errores:
        nombre_errores = f"errores_dat_{orden}_{fecha}.xlsx"
        errores_b64 = base64.b64encode(construir_excel_errores(orden, resultado.errores)).decode()

    return GenerarDatResult(
        orden=orden,
        fecha_ini=fecha,
        registros=resultado.registros,
        seriales_excel=resultado.seriales_excel,
        seriales_orden=resultado.seriales_orden,
        nombre_dat=resultado.nombre_dat,
        dat_base64=base64.b64encode(resultado.contenido_dat).decode(),
        errores=[SerialError(**e) for e in resultado.errores],
        nombre_errores=nombre_errores,
        errores_base64=errores_b64,
        no_encontrados_en_orden=resultado.no_encontrados_en_orden,
        duplicados_en_excel=resultado.duplicados_en_excel,
    )
