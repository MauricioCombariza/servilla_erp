from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.auth.dependencies import require_page
from app.schemas.imagenes import ImagenGuia, ImagenListItem
from app.services.bases_web import buscar_histo, buscar_histo_serial_exacto
from app.services.imagenes import construir_image_url, fetch_imagen_bytes

router = APIRouter(prefix="/api/imagenes", tags=["imagenes"])
_auth = Depends(require_page("imagenes"))


def _fmt(v) -> str | None:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


@router.get("", response_model=list[ImagenListItem])
async def buscar_imagenes(
    q: str = Query(min_length=2, max_length=200),
    modo: str = Query(default="nombre", pattern="^(nombre|direccion)$"),
    _=_auth,
):
    rows = await buscar_histo(q.strip(), modo)
    return [
        ImagenListItem(
            serial=str(row["serial"]),
            nombred=_fmt(row.get("nombred")),
            dirdes1=_fmt(row.get("dirdes1")),
            ciudad1=_fmt(row.get("ciudad1")),
            f_emi=_fmt(row.get("f_emi")),
            cod_men=_fmt(row.get("cod_men")),
            ret_esc=_fmt(row.get("ret_esc")),
            motivo=_fmt(row.get("motivo")),
        )
        for row in rows
        if row.get("serial")
    ]


@router.get("/{serial}", response_model=ImagenGuia)
async def obtener_imagen_guia(
    serial: str = Path(min_length=1, max_length=20),
    _=_auth,
):
    serial = serial.strip()
    row = await buscar_histo_serial_exacto(serial)
    image_url = construir_image_url(serial)

    if row is None:
        return ImagenGuia(serial=serial, encontrado=False, image_url=image_url)

    return ImagenGuia(
        serial=serial,
        encontrado=True,
        image_url=image_url,
        no_entidad=_fmt(row.get("no_entidad")),
        servicio=_fmt(row.get("servicio")),
        nombred=_fmt(row.get("nombred")),
        dirdes1=_fmt(row.get("dirdes1")),
        ciudad1=_fmt(row.get("ciudad1")),
        cod_sec=_fmt(row.get("cod_sec")),
        retorno=_fmt(row.get("retorno")),
        ret_esc=_fmt(row.get("ret_esc")),
        orden=_fmt(row.get("orden")),
        planilla=_fmt(row.get("planilla")),
        f_emi=_fmt(row.get("f_emi")),
        f_lleva=_fmt(row.get("f_lleva")),
        cod_men=_fmt(row.get("cod_men")),
        dir_num=_fmt(row.get("dir_num")),
        comentario=_fmt(row.get("comentario")),
    )


@router.get("/{serial}/foto")
async def obtener_foto_guia(
    serial: str = Path(min_length=1, max_length=20),
    _=_auth,
):
    serial = serial.strip()
    resultado = await fetch_imagen_bytes(serial)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Imagen no disponible en el servidor de guías")
    contenido, content_type = resultado
    return Response(content=contenido, media_type=content_type)
