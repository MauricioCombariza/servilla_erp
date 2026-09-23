"""
Genera el informe .dat de BCS (ancho fijo, latin-1) cruzando los Excel de gestión
con los registros de la orden en bases_web.histo.

Formato tomado del archivo BCS_CON_EXT_02_<fecha>.dat existente: encabezado de 312
caracteres, registros de 375 (centralizado) o de 44 (terceros: solo el bloque
de gestión) y pie con el conteo + 'NOC'.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from app.services.excel_utils import construir_excel

TIPO_DOC = "NI"
MARCA_NOC = "NOC1"
ANCHO_REGISTRO = 375
ANCHO_TERCEROS = 44
TIPO_CENTRALIZADO = "centralizado"
TIPO_TERCEROS = "terceros"
TIPOS_INFORME = (TIPO_CENTRALIZADO, TIPO_TERCEROS)
ANCHO_ENCABEZADO = 312
COLUMNAS_EXCEL = ["serial", "Estado", "Causal_Dev", "F_recepcio", "guias", "F_GESTION"]


@dataclass
class ResultadoDat:
    nombre_dat: str
    contenido_dat: bytes
    registros: int
    seriales_excel: int
    seriales_orden: int
    # Seriales de la orden que no vinieron en ningún Excel (van al archivo de errores)
    errores: list[dict] = field(default_factory=list)
    # Seriales de los Excel que no pertenecen a la orden
    no_encontrados_en_orden: list[str] = field(default_factory=list)
    duplicados_en_excel: list[str] = field(default_factory=list)


def normalizar_serial(serie: pd.Series) -> pd.Series:
    """Serial como texto, sin espacios, sin '.0' ni ceros a la izquierda."""
    return (
        serie.astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.lstrip("0")
    )


def leer_excels(archivos: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, list[str]]:
    """Une los Excel de gestión. Devuelve el DataFrame y los seriales repetidos entre archivos."""
    marcos = []
    for nombre, contenido in archivos:
        try:
            df = pd.read_excel(io.BytesIO(contenido), dtype=str)
        except Exception as exc:
            raise ValueError(f"{nombre}: no se pudo leer el Excel ({exc})") from exc
        df.columns = [str(c).strip() for c in df.columns]
        faltantes = [c for c in COLUMNAS_EXCEL if c not in df.columns]
        if faltantes:
            raise ValueError(f"{nombre}: faltan columnas {', '.join(faltantes)}")
        marcos.append(df[COLUMNAS_EXCEL])

    df = pd.concat(marcos, ignore_index=True).fillna("")
    for col in COLUMNAS_EXCEL:
        df[col] = df[col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["serial"] = normalizar_serial(df["serial"])
    df = df[df["serial"] != ""]
    df["Causal_Dev"] = df["Causal_Dev"].str.zfill(2)
    duplicados = sorted(df.loc[df.duplicated("serial", keep=False), "serial"].unique())
    return df.drop_duplicates(subset=["serial"], keep="last"), duplicados


def campo(valor, ancho: int, alinear: str = "izq", relleno: str = " ") -> str:
    """Ajusta un valor a un ancho fijo: rellena y trunca."""
    valor = "" if valor is None or pd.isna(valor) else str(valor).strip()
    if alinear == "der":
        return valor.rjust(ancho, relleno)[-ancho:]
    return valor.ljust(ancho, relleno)[:ancho]


def _bloque_gestion(reg: dict, fecha_ini: str) -> str:
    """fecha_ini + Estado + Causal_Dev + F_recepcio + guía (15) + F_GESTION: 44 caracteres."""
    return "".join([
        campo(fecha_ini, 8),
        campo(reg["Estado"], 3),
        campo(reg["Causal_Dev"], 2, "der", "0"),
        campo(reg["F_recepcio"], 8),
        campo(reg["guias"], 15, "der", "0"),
        campo(reg["F_GESTION"], 8),
    ])


def construir_linea(reg: dict, fecha_ini: str, tipo: str = TIPO_CENTRALIZADO) -> str:
    """Centralizado: registro completo de 375 caracteres.
    Terceros: solo el bloque de gestión (de fecha_ini hasta F_GESTION)."""
    if tipo == TIPO_TERCEROS:
        linea = _bloque_gestion(reg, fecha_ini)
        ancho = ANCHO_TERCEROS
    else:
        linea = "".join([
            TIPO_DOC,
            campo(reg["identdes"], 32, "der", "0"),
            campo(reg["oficina"], 6, "der", "0"),
            campo(reg["nombred"], 65),
            campo(reg["dir_pred"], 65),
            campo(reg["barrd1"], 35),
            "0" * 11,
            campo(reg["ciudad1"], 35),
            campo(reg["dpto1"], 35),
            _bloque_gestion(reg, fecha_ini),
            MARCA_NOC,
            campo(reg["courrier"], 35),
            campo(reg["orden"], 6, "der"),
        ])
        ancho = ANCHO_REGISTRO
    if len(linea) != ancho:
        raise ValueError(f"Registro de {len(linea)} caracteres para el serial {reg.get('serial')}")
    return linea


def generar_dat(
    orden: str,
    fecha_ini: str,
    archivos: list[tuple[str, bytes]],
    filas_histo: list[dict],
    tipo: str = TIPO_CENTRALIZADO,
) -> ResultadoDat:
    """Cruza los Excel con histo y arma el contenido del .dat. fecha_ini en AAAAMMDD."""
    if tipo not in TIPOS_INFORME:
        raise ValueError(f"Tipo de informe inválido: {tipo}")
    if not filas_histo:
        raise ValueError(f"La orden {orden} no tiene registros en histo")

    df_excel, duplicados = leer_excels(archivos)
    df_histo = pd.DataFrame(filas_histo).astype(str).replace({"None": ""})
    df_histo["serial"] = normalizar_serial(df_histo["serial"])
    df_histo = df_histo.drop_duplicates(subset=["serial"], keep="last")

    df = df_excel.merge(df_histo, on="serial", how="inner").sort_values("oficina")

    lineas = [campo(f"*BCSEXTCON02{fecha_ini}", ANCHO_ENCABEZADO)]
    lineas += [construir_linea(reg, fecha_ini, tipo) for reg in df.to_dict("records")]
    lineas.append(campo(f"*{str(len(df)).zfill(8)}", ANCHO_ENCABEZADO) + "NOC")
    contenido = ("\n".join(lineas) + "\n").encode("latin-1", errors="replace")

    seriales_excel = set(df_excel["serial"])
    faltantes = df_histo[~df_histo["serial"].isin(seriales_excel)].sort_values(["courrier", "serial"])
    errores = [
        {"serial": r["serial"], "courrier": r["courrier"].strip()}
        for r in faltantes.to_dict("records")
    ]

    return ResultadoDat(
        nombre_dat=f"BCS_CON_EXT_02_{fecha_ini}.dat",
        contenido_dat=contenido,
        registros=len(df),
        seriales_excel=len(df_excel),
        seriales_orden=len(df_histo),
        errores=errores,
        no_encontrados_en_orden=sorted(seriales_excel - set(df_histo["serial"])),
        duplicados_en_excel=duplicados,
    )


def construir_excel_errores(orden: str, errores: list[dict]) -> bytes:
    return construir_excel(
        f"Seriales de la orden {orden} que no se generaron en el .dat",
        ["serial", "courrier"],
        errores,
        [20, 30],
    )
