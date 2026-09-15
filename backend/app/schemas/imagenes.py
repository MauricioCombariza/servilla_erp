from pydantic import BaseModel


class ImagenListItem(BaseModel):
    serial: str
    nombred: str | None = None
    dirdes1: str | None = None
    ciudad1: str | None = None
    f_emi: str | None = None
    cod_men: str | None = None
    ret_esc: str | None = None
    motivo: str | None = None


class ImagenGuia(BaseModel):
    serial: str
    encontrado: bool
    image_url: str
    no_entidad: str | None = None
    servicio: str | None = None
    nombred: str | None = None
    dirdes1: str | None = None
    ciudad1: str | None = None
    cod_sec: str | None = None
    retorno: str | None = None
    ret_esc: str | None = None
    orden: str | None = None
    planilla: str | None = None
    f_emi: str | None = None
    f_lleva: str | None = None
    cod_men: str | None = None
    dir_num: str | None = None
    comentario: str | None = None
