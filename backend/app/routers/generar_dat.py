import base64
import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from app.auth.dependencies import require_page
from app.schemas.generar_dat import (
    FormatoServillaResult,
    GenerarDatResult,
    SerialError,
    SerialPorRevisar,
)
from app.services.bases_web import fetch_histo_orden
from app.services.excel_utils import XLSX_MEDIA_TYPE
from app.services.formato_servilla_service import generar_formato_servilla
from app.services.generar_dat_service import (
    INFORME_DEFAULT,
    TIPOS_INFORME,
    construir_excel_errores,
    construir_formato_excel,
    generar_dat,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generar-dat", tags=["generar-dat"])
_auth = Depends(require_page("generar_dat"))

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ARCHIVOS = 5


def _validar_orden(orden: str) -> str:
    orden = orden.strip()
    if not re.fullmatch(r"\d{1,10}", orden):
        raise HTTPException(status_code=400, detail="Número de orden inválido")
    return orden


async def _consultar_orden(orden: str) -> list[dict]:
    try:
        return await fetch_histo_orden(orden)
    except Exception as exc:
        logger.error("Error consultando la orden %s en bases_web.histo: %s", orden, exc)
        raise HTTPException(status_code=502, detail="No se pudo consultar bases_web")


def _normalizar_fecha(fecha: str) -> str:
    """Acepta AAAA-MM-DD (input date) o AAAAMMDD y devuelve AAAAMMDD."""
    fecha = fecha.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(fecha, fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail="Fecha inicial inválida (use AAAA-MM-DD)")


@router.get("/formato")
async def descargar_formato(_=_auth):
    return Response(
        content=construir_formato_excel(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="formato_generar_dat.xlsx"'},
    )


@router.post("/formato-servilla", response_model=FormatoServillaResult)
async def formato_servilla(
    orden: str = Form(...),
    _=_auth,
):
    orden = _validar_orden(orden)
    filas_histo = await _consultar_orden(orden)
    try:
        resultado = generar_formato_servilla(orden, filas_histo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FormatoServillaResult(
        orden=orden,
        filas=resultado.filas,
        excluidos=resultado.excluidos,
        nombre=resultado.nombre,
        excel_base64=base64.b64encode(resultado.contenido).decode(),
        por_revisar=[SerialPorRevisar(**s) for s in resultado.por_revisar],
    )


@router.post("", response_model=GenerarDatResult)
async def generar(
    orden: str = Form(...),
    fecha_ini: str = Form(...),
    tipo: str = Form("centralizado"),
    informe: str = Form(INFORME_DEFAULT),
    files: list[UploadFile] = File(...),
    _=_auth,
):
    orden = _validar_orden(orden)
    fecha = _normalizar_fecha(fecha_ini)
    tipo = tipo.strip().lower()
    if tipo not in TIPOS_INFORME:
        raise HTTPException(status_code=400, detail="Tipo de informe inválido (centralizado o terceros)")
    informe = informe.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", informe):
        raise HTTPException(status_code=400, detail="El nombre del informe debe tener 3 letras (p. ej. CON, CLP)")

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

    filas_histo = await _consultar_orden(orden)

    try:
        resultado = generar_dat(orden, fecha, archivos, filas_histo, tipo, informe)
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
        tipo=tipo,
        informe=informe,
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
