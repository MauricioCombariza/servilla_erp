import re

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth.dependencies import require_role
from app.schemas.direcciones import AjusteDireccionesResult, DescargarDireccionesRequest
from app.services.direcciones_service import (
    generar_txt_leonisa,
    generar_txt_vehigrupo,
    procesar_archivo_leonisa,
    procesar_archivo_vehigrupo,
)

router = APIRouter(prefix="/api/direcciones", tags=["direcciones"])
_auth = Depends(require_role("administrador", "logistica"))

# Un lote de órdenes cabe en unos pocos MB; no es un dashboard completo, así que
# se lee entero en memoria (sin streaming a disco).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_NOMBRE_INVALIDO_RE = re.compile(r"[^A-Za-z0-9_-]")
_CLIENTES_VALIDOS = ("leonisa", "vehigrupo")


@router.post("/ajustar", response_model=AjusteDireccionesResult)
async def ajustar(file: UploadFile, cliente: str = Form(...), _=_auth):
    if cliente not in _CLIENTES_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Cliente no soportado: {cliente}")

    fname = (file.filename or "").lower()
    if not fname.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .txt")

    contenido = await file.read()
    if len(contenido) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máximo {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
        )

    try:
        if cliente == "leonisa":
            return procesar_archivo_leonisa(contenido)
        return procesar_archivo_vehigrupo(contenido)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/descargar")
async def descargar(body: DescargarDireccionesRequest, _=_auth):
    nombre = _NOMBRE_INVALIDO_RE.sub("", body.nombre_archivo).strip() or "direcciones"
    contenido = (
        generar_txt_leonisa(body.filas)
        if body.cliente == "leonisa"
        else generar_txt_vehigrupo(body.filas)
    )
    return Response(
        content=contenido,
        # application/octet-stream evita que FastAPI anexe "; charset=utf-8" al
        # Content-Type (lo hace para cualquier media_type "text/*"), lo cual sería
        # engañoso: los bytes están codificados en latin-1, no utf-8.
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{nombre}.txt"'},
    )
