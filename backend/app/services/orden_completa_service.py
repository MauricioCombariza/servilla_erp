"""
Genera los .dat de BCS (centralizado y terceros) directamente desde el Excel de la
orden completa (export de histo con la columna `estado` = motivo final del serial),
sin Excel de gestión ni consulta a bases_web.

Del archivo salen los datos del destinatario (identdes, oficina, nombred, dir_pred,
barrd1, ciudad1, dpto1, courrier, orden) y la gestión se deduce como en el Formato
Servilla: causal desde `estado`, F_recepcio = f_emi, F_GESTION = f_emi + 2..6 días
al azar. Los seriales sin causal reconocida o sin f_emi válida no van al .dat y se
devuelven para revisión.
"""
from __future__ import annotations

import io
import random
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from app.services.excel_utils import construir_excel
from app.services.formato_servilla_service import (
    DIAS_GESTION_MAX,
    DIAS_GESTION_MIN,
    _normalizar,
    causal_de_motivo,
    fecha_f_emi,
)
from app.services.generar_dat_service import (
    COLUMNAS_EXCEL,
    TIPOS_INFORME,
    armar_dat,
    nombre_dat,
    normalizar_serial,
)

COLUMNAS_ORDEN = [
    "serial", "estado", "f_emi", "orden", "identdes", "oficina",
    "nombred", "dir_pred", "barrd1", "ciudad1", "dpto1", "courrier",
]

# En el export de la orden `estado` se corta a 20 caracteres; estos no los reconoce
# causal_de_motivo (que trata "Destinatario De…" como ambiguo) pero no son ambiguos
_CAUSAL_ESTADO = {"destinatario descono": "01"}


def causal_de_estado(estado: str) -> str:
    return _CAUSAL_ESTADO.get(_normalizar(estado)) or causal_de_motivo(estado)


@dataclass
class DatGenerado:
    tipo: str
    informe: str
    nombre: str
    contenido: bytes
    registros: int


@dataclass
class ResultadoOrdenCompleta:
    orden: str
    seriales: int
    dats: list[DatGenerado]
    # [{serial, courrier, motivo, falta}] de los seriales que no entraron al .dat
    por_revisar: list[dict] = field(default_factory=list)
    duplicados: list[str] = field(default_factory=list)


def _columna(nombre: object) -> str:
    texto = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return texto.strip().lower()


def leer_orden(nombre: str, contenido: bytes) -> pd.DataFrame:
    """Primera hoja del Excel que tenga las columnas de la orden, todo como texto."""
    try:
        hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, dtype=str)
    except Exception as exc:
        raise ValueError(f"{nombre}: no se pudo leer el Excel ({exc})") from exc

    faltantes: list[str] = COLUMNAS_ORDEN
    for df in hojas.values():
        df.columns = [_columna(c) for c in df.columns]
        falta = [c for c in COLUMNAS_ORDEN if c not in df.columns]
        if not falta:
            df = df.loc[:, ~df.columns.duplicated()][COLUMNAS_ORDEN].fillna("")
            return df.apply(lambda s: s.astype(str).str.strip())
        if len(falta) < len(faltantes):
            faltantes = falta
    raise ValueError(f"{nombre}: ninguna hoja tiene las columnas de la orden (faltan {', '.join(faltantes)})")


def _orden_unica(df: pd.DataFrame) -> str:
    ordenes = sorted({o.removesuffix(".0") for o in df["orden"] if o})
    if not ordenes:
        raise ValueError("El archivo no trae el número de orden (columna orden)")
    if len(ordenes) > 1:
        raise ValueError(f"El archivo trae varias órdenes ({', '.join(ordenes)}): sube una orden por archivo")
    return ordenes[0]


def generar_dats_orden_completa(
    nombre_archivo: str,
    contenido: bytes,
    fecha_ini: str,
    informes: dict[str, str],
    rng: random.Random | None = None,
) -> ResultadoOrdenCompleta:
    """fecha_ini en AAAAMMDD; informes = {tipo: nombre de 3 letras} para cada .dat a generar."""
    rng = rng or random.Random()
    df = leer_orden(nombre_archivo, contenido)
    df["serial"] = normalizar_serial(df["serial"])
    df = df[df["serial"] != ""]
    if df.empty:
        raise ValueError(f"{nombre_archivo}: no trae seriales")
    orden = _orden_unica(df)
    df["orden"] = orden
    duplicados = sorted(df.loc[df.duplicated("serial", keep=False), "serial"].unique())
    df = df.drop_duplicates(subset=["serial"], keep="last")

    gestion: list[dict] = []
    por_revisar: list[dict] = []
    for fila in df.to_dict("records"):
        causal = causal_de_estado(fila["estado"])
        # Si la celda es fecha de Excel llega como 'AAAA-MM-DD 00:00:00'
        recepcion = fecha_f_emi(fila["f_emi"].split(" ")[0])
        falta = [c for c, v in (("Causal_Dev", causal), ("F_recepcio", recepcion)) if not v]
        if falta:
            por_revisar.append({"serial": fila["serial"], "courrier": fila["courrier"],
                                "motivo": fila["estado"], "falta": ", ".join(falta)})
            continue
        gestion.append({
            "serial": fila["serial"],
            "Estado": "ENT" if causal == "00" else "DEV",
            "Causal_Dev": causal,
            "F_recepcio": recepcion.strftime("%Y%m%d"),
            "guias": fila["serial"],
            "F_GESTION": (recepcion + timedelta(days=rng.randint(DIAS_GESTION_MIN, DIAS_GESTION_MAX)))
            .strftime("%Y%m%d"),
        })
    if not gestion:
        raise ValueError(f"Ningún serial de la orden {orden} tiene un estado reconocido y f_emi válida")

    df_gestion = pd.DataFrame(gestion, columns=COLUMNAS_EXCEL)
    dats = []
    for tipo in TIPOS_INFORME:
        if tipo not in informes:
            continue
        datos, registros = armar_dat(df_gestion, df, fecha_ini, tipo, informes[tipo])
        dats.append(DatGenerado(tipo, informes[tipo], nombre_dat(informes[tipo], fecha_ini), datos, registros))

    return ResultadoOrdenCompleta(
        orden=orden,
        seriales=len(df),
        dats=dats,
        por_revisar=sorted(por_revisar, key=lambda f: f["serial"]),
        duplicados=duplicados,
    )


def construir_excel_por_revisar(orden: str, por_revisar: list[dict]) -> bytes:
    return construir_excel(
        f"Seriales de la orden {orden} que no entraron al .dat",
        ["serial", "courrier", "motivo", "falta"],
        por_revisar,
        [20, 20, 25, 25],
    )
