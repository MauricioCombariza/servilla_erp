"""
Estandarización de direcciones + dirección numérica (dir_num)
==============================================================
La estandarización viene de app.services.estandarizar_direcciones (copia de
dashboard/dirnum/estandarizar_direcciones_v3.py, la misma que usa la
sectorización); aquí solo se porta generar_direccion_numerica de ese archivo.
Es la misma dir_num de 18 dígitos del sistema legacy (histo.dir_num, C18).

A diferencia de direcciones_service.ajustar_dir_leonisa (formato KRA/CLL que
conserva complementos), aquí la dirección ajustada queda en el formato
"CL/CR/DG/TR via1 via2 placa [CARDINAL]" sin complementos, que es la entrada
que necesita generar_direccion_numerica.

Formato dirección numérica (18 dígitos):
  [1]     Cardinal: NORTE/nada=1, SUR=2, SUR ESTE=3, ESTE=4
  [2]     Tipo vía: CL/DG=1, CR/TR=3
  [3-5]   Número vía principal (zero-padded)
  [6-8]   Letras vía principal (codificadas)
  [9]     Separador: CL/DG + placa par=3, impar=1; CR/TR + placa par=1, impar=3
  [10-12] Número vía secundaria (zero-padded)
  [13-15] Letras vía secundaria (codificadas)
  [16-18] Placa (zero-padded)
"""

from __future__ import annotations

import io

import pandas as pd

from app.schemas.direcciones import AjusteDirNumResult, FilaDirNum
from app.services.estandarizar_direcciones import (
    codificar_letras,
    estandarizar_direccion,
    parsear_componente_via,
)



def generar_direccion_numerica(dir_estandarizada):
    """
    Genera la dirección numérica de 18 dígitos.

    Formato:
      [1]     Cardinal: NORTE/nada=1, SUR=2, SUR ESTE=3, ESTE=4
      [2]     Tipo vía: CL/DG=1, CR/TR=3
      [3-5]   Numero vía principal (3 dígitos, zero-padded)
      [6-8]   Letras vía principal (3 dígitos, codificadas)
      [9]     Separador: CL/DG + placa par=3, impar=1; CR/TR + placa par=1, impar=3
      [10-12] Numero vía secundaria (3 dígitos, zero-padded)
      [13-15] Letras vía secundaria (3 dígitos, codificadas)
      [16-18] Placa (3 dígitos, zero-padded)
    """
    if not dir_estandarizada:
        return None

    partes = dir_estandarizada.upper().split()

    # --- Extraer cardinal al final ---
    cardinal = None
    cardinales_compuestos = {'SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE'}
    if len(partes) >= 2 and ' '.join(partes[-2:]) in cardinales_compuestos:
        cardinal = ' '.join(partes[-2:])
        partes = partes[:-2]
    elif len(partes) >= 1 and partes[-1] in ('SUR', 'NORTE', 'ESTE', 'OESTE', 'SUL'):
        cardinal = partes[-1]
        if cardinal == 'SUL':
            cardinal = 'SUR'
        partes = partes[:-1]

    # Codificar cardinal
    if cardinal is None or cardinal == 'NORTE':
        d_cardinal = 1
    elif cardinal == 'SUR':
        d_cardinal = 2
    elif cardinal in ('SUR ESTE', 'SURESTE'):
        d_cardinal = 3
    elif cardinal == 'ESTE':
        d_cardinal = 4
    else:
        d_cardinal = 1

    # --- Tipo y componentes ---
    if len(partes) < 4:
        return None

    tipo = partes[0]
    via1_str = partes[1]
    via2_str = partes[2]
    placa_str = partes[3]

    # Codificar tipo de vía (CL/DG=1, CR/TR=3)
    tipo_map = {'CL': 1, 'DG': 1, 'CR': 3, 'TR': 3}
    d_tipo = tipo_map.get(tipo)
    if d_tipo is None:
        return None

    # Separador según tipo y paridad de la placa
    # CL/DG: placa par→3, placa impar→1
    # CR/TR: placa par→1, placa impar→3
    placa_num_tmp, _ = parsear_componente_via(placa_str)
    placa_es_par = (placa_num_tmp % 2 == 0) if placa_num_tmp is not None else True
    if tipo in ('CL', 'DG'):
        d_sep = 3 if placa_es_par else 1
    else:
        d_sep = 1 if placa_es_par else 3

    # --- Parsear componentes ---
    via1_num, via1_let = parsear_componente_via(via1_str)
    via2_num, via2_let = parsear_componente_via(via2_str)
    placa_num, _ = parsear_componente_via(placa_str)

    if via1_num is None or via2_num is None or placa_num is None:
        return None

    # --- Codificar letras ---
    d_via1_let = codificar_letras(via1_let)
    d_via2_let = codificar_letras(via2_let)

    # --- Construir dirección numérica ---
    dir_num = (
        f"{d_cardinal}"
        f"{d_tipo}"
        f"{via1_num:03d}"
        f"{d_via1_let:03d}"
        f"{d_sep}"
        f"{via2_num:03d}"
        f"{d_via2_let:03d}"
        f"{placa_num:03d}"
    )

    return dir_num


# ========== EXCEL serial/direccion → direccion_ajustada + dir_num ==========

COLUMNAS_SALIDA = ["serial", "direccion", "direccion_ajustada", "dir_num"]


def calcular_fila(serial: str, direccion: str) -> FilaDirNum:
    ajustada = estandarizar_direccion(direccion) or ""
    return FilaDirNum(
        serial=serial,
        direccion=direccion,
        direccion_ajustada=ajustada,
        dir_num=generar_direccion_numerica(ajustada) or "",
    )


def _buscar_columna(df: pd.DataFrame, nombre: str):
    return next((c for c in df.columns if str(c).strip().lower() == nombre), None)


def procesar_excel_dirnum(contenido: bytes) -> AjusteDirNumResult:
    """Lee un Excel con columnas 'serial' y 'direccion' (sin importar
    mayúsculas/espacios en el encabezado) y calcula la dirección ajustada y la
    dir_num de cada fila. Lanza ValueError si falta alguna de las columnas."""
    df = pd.read_excel(io.BytesIO(contenido), dtype=str)

    col_serial = _buscar_columna(df, "serial")
    col_direccion = _buscar_columna(df, "direccion")
    faltantes = [n for n, c in (("serial", col_serial), ("direccion", col_direccion)) if c is None]
    if faltantes:
        raise ValueError(
            "El archivo debe tener las columnas 'serial' y 'direccion' "
            f"(falta: {', '.join(faltantes)})"
        )

    df = df.fillna("")
    filas = [
        calcular_fila(str(s).strip(), str(d).strip())
        for s, d in zip(df[col_serial], df[col_direccion])
    ]
    return AjusteDirNumResult(
        total_filas=len(filas),
        sin_dir_num=sum(1 for f in filas if not f.dir_num),
        filas=filas,
    )


def generar_excel_dirnum(filas: list[FilaDirNum]) -> bytes:
    """Genera el .xlsx de salida. La dir_num se recalcula desde la
    direccion_ajustada (el usuario pudo editarla en pantalla). Todas las
    columnas van como texto para que Excel no convierta la dir_num de 18
    dígitos a notación científica ni pierda ceros a la izquierda."""
    registros = [
        {
            "serial": f.serial,
            "direccion": f.direccion,
            "direccion_ajustada": f.direccion_ajustada.strip().upper(),
            "dir_num": generar_direccion_numerica(f.direccion_ajustada.strip().upper()) or "",
        }
        for f in filas
    ]
    df = pd.DataFrame(registros, columns=COLUMNAS_SALIDA)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="direcciones")
        ws = writer.sheets["direcciones"]
        for fila in ws.iter_rows(min_row=2):
            for celda in fila:
                celda.number_format = "@"
        for col, ancho in zip("ABCD", (18, 50, 35, 22)):
            ws.column_dimensions[col].width = ancho
    return buffer.getvalue()
