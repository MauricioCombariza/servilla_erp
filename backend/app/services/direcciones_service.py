"""
Ajuste de direcciones (Leonisa, Banco Vehigrupo)
==================================================
Normaliza direcciones colombianas al formato estándar (KRA/CLL/DG/TV,
cardinales, complementos como TORRE/APTO/PISO). La misma función de
normalización (`ajustar_dir_leonisa`) se reutiliza para ambos clientes;
lo que cambia es el formato del archivo:

- Leonisa: .txt separado por | (sin encabezado, latin-1), dirección en
  la columna 6 (índice 5).
- Banco Vehigrupo: .txt de ancho fijo (288 caracteres por línea, CRLF,
  latin-1, sin encabezado), dirección en las columnas 106-170
  (índice 105:170).

Puerto directo de la herramienta Streamlit
dashboard/pages_home/AjusteDireccionesLeonisa.py — misma lógica de
normalización, sin cambios de comportamiento.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from app.schemas.direcciones import AjusteDireccionesResult

ENCODING = "latin-1"
COL_DIRECCION = 5  # columna 6 del archivo Leonisa (índice 0-based)
COL_NOMBRE = 4  # columna 5 del archivo Leonisa (índice 0-based), precede a la dirección

# ── Layout de ancho fijo del archivo Banco Vehigrupo ─────────────────────────
VHG_LINE_LEN = 288
VHG_FIELDS = [(0, 40), (40, 105), (105, 170), (170, 216), (216, 251), (251, 280), (280, 288)]
VHG_COL_DIRECCION = 2  # índice del campo dirección dentro de VHG_FIELDS/filas
VHG_COL_NOMBRE = 1  # índice del campo "Nombre" dentro de VHG_FIELDS/filas

# ── Tabla de abreviaciones de tipo de vía ────────────────────────────────────
# El orden importa: los patrones más largos primero para evitar reemplazos parciales
_VIA_MAP = [
    # ── Avenidas con nombre propio que en realidad son una carrera numerada ────
    # Debe ir antes de la regla simple "AVENIDA" → "AV" (si no, "AVENIDA" ya se
    # habría reemplazado por "AV" y este patrón nunca matchearía).
    (r"\bAV(?:ENIDA)?\s+CARACAS\b", "KRA 14"),
    # ── Compuestos (AV CARRERA → KRA, AV CALLE → CLL) ──────────────────────────
    (r"\bAV(?:ENIDA)?\s+(?:CARRERA|CARERA|CARR|CRA|CR|KRA|KR)\b", "KRA"),
    (r"\bAV(?:ENIDA)?\s+(?:CALLE|CALE|CALL|CLL|CL)\b",            "CLL"),
    (r"\bAV(?:ENIDA)?\s+(?:DIAGONAL|DIAG|DG)\b",                  "DG"),
    (r"\bAV(?:ENIDA)?\s+(?:TRANSVERSAL|TRANSV|TV|TR)\b",          "TV"),
    # ── Simples ─────────────────────────────────────────────────────────────────
    (r"\bCALLE\b",       "CLL"),
    (r"\bCALL\b",        "CLL"),
    (r"\bCALE\b",        "CLL"),   # typo (una L)
    (r"\bCLLE\b",        "CLL"),   # typo (letras invertidas)
    (r"\bCLL\b",         "CLL"),
    (r"\bCL\b",          "CLL"),
    (r"\bCARRERA\b",     "KRA"),
    (r"\bCARERA\b",      "KRA"),   # typo frecuente (una R)
    (r"\bCARRETERA\b",   "KRA"),
    (r"\bCARR\b",        "KRA"),
    (r"\bKRR\b",         "KRA"),   # typo frecuente (tres letras)
    (r"\bCRA\b",         "KRA"),
    (r"\bCR\b",          "KRA"),
    (r"\bKR\b",          "KRA"),
    (r"\bCA\b",          "KRA"),   # abreviatura de Carrera usada en archivos bancarios (Vehigrupo)
    (r"\bAK\b",          "KRA"),   # Autopista / Avenida Carrera abreviada
    (r"\bDIAGONAL\b",    "DG"),
    (r"\bDIAG\b",        "DG"),
    (r"\bTRANSVERSAL\b", "TV"),
    (r"\bTRANSV\b",      "TV"),
    (r"\bTR\b",          "TV"),
    (r"\bAVENIDA\b",     "AV"),
]

# ── Tipo de vía pegado al final de la palabra/número anterior ───────────────
# Frecuente en nombres de barrio/conjunto sin espacio antes del tipo de vía:
# "GUAYACAN DE LA PLAZACL 48 SUR 39 57" (falta el espacio entre "PLAZA" y
# "CL") o pegado a un número de complemento: "AP 1916CR 61 33 51". En ambos
# casos "\bCL\b"/"\bCR\b" (usados en _VIA_MAP) nunca matchean porque no hay
# límite de palabra antes del tipo de vía (está pegado a la letra o dígito
# anterior). Se detecta con un lookbehind de letra o dígito (en vez de \b) y
# se inserta el espacio faltante para que _VIA_MAP sí pueda reconocerlo
# después. Los patrones más largos van primero por la misma razón que en
# _VIA_MAP (evitar matches parciales).
_VIA_TOKENS_SIMPLES = (
    "CARRETERA", "CARRERA", "CARERA", "CARR", "KRR", "CRA", "CR", "KRA", "KR", "CA", "AK",
    "CALLE", "CALE", "CLLE", "CLL", "CALL", "CL",
    "DIAGONAL", "DIAG", "DG",
    "TRANSVERSAL", "TRANSV", "TR", "TV",
    "AVENIDA", "AV",
)
_VIA_PEGADA_RE = re.compile(
    r"(?<=[A-Z0-9])(" + "|".join(sorted(_VIA_TOKENS_SIMPLES, key=len, reverse=True)) + r")\b"
)

# ── Parser por tokens ────────────────────────────────────────────────────────
# Abreviaciones canónicas para keywords de complemento
_COMP_ABBREV: dict[str, str] = {
    'APARTAMENTO': 'APTO', 'APTO': 'APTO', 'AP': 'APTO', 'APT': 'APTO',
    'TORRE': 'TO', 'TRR': 'TO', 'TO': 'TO',
    'PISO': 'PS', 'PS': 'PS', 'P': 'PS',
    'BLOQUE': 'BL', 'BLQ': 'BL', 'BL': 'BL',
    'INTERIOR': 'INT', 'INT': 'INT',
    'LOCAL': 'LC', 'LC': 'LC',
    'CASA': 'CS', 'CS': 'CS',
    'MZA': 'MZA', 'MZ': 'MZA',
    'EDIFICIO': 'ED', 'EDIF': 'ED', 'ED': 'ED',
    'OFICINA': 'OF', 'OFI': 'OF', 'OF': 'OF',
    'CONSULTORIO': 'CONS', 'CONSUL': 'CONS', 'CONS': 'CONS',
}

_CARDINALS_COMPOUND = ('SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE')
_CARDINALS_SIMPLE   = ('SUR', 'NORTE', 'ESTE', 'OESTE')

_VIA_TYPE_RE   = re.compile(r'^(KRA|CLL|DG|TV|AV)$')
_COORD_TOK_RE  = re.compile(r'^\d+[A-Z]*$')  # número con letras opcionales: 54C, 88I, 65, 79FBIS
_COMP_VAL_RE   = re.compile(r'^\d+[A-Z]*$|^[A-Z]$')  # valor tras keyword: 1106, 4, A
_NAME_TOK_RE   = re.compile(r'^[A-Z]+$')  # token alfabético (posible palabra de nombre propio)


def _next_cardinal(tokens: list[str], i: int) -> tuple[str | None, int]:
    """Devuelve (cardinal, nuevo_índice) o (None, i) si no hay cardinal en posición i."""
    if i >= len(tokens):
        return None, i
    if i + 1 < len(tokens):
        comp = tokens[i] + ' ' + tokens[i + 1]
        if comp in _CARDINALS_COMPOUND:
            return comp, i + 2
    if tokens[i] in _CARDINALS_SIMPLE:
        return tokens[i], i + 1
    return None, i


_SPLIT_COORD_RE = re.compile(r'^\d{4,5}$')  # bloque numérico de 4-5 dígitos → partir


def _parse_y_limpiar(text: str) -> tuple[str, int]:
    """
    Parsea la dirección token a token.
    Retorna (resultado, coord_count) donde coord_count es el número de tokens
    de coordenada encontrados (necesitamos al menos 3 para una dirección válida).

      1. Busca el tipo de vía (KRA/CLL/…) en cualquier posición — descarta lo anterior
         (barrios, localidades, etc. que preceden a la dirección)
      2. Hasta 3 tokens de coordenada (\\d+[A-Z]*), con cardinales intercalados
         • Si un token es un bloque de 4-5 dígitos puros, lo divide: últimos 2 = placa,
           el resto = número de cruce  ("4977" → "49" + "77")
      3. Cardinal final opcional
      4. Solo keywords de complemento + su valor (TORRE 4, APTO 1106, PS 1…)
         — el resto (nombres de conjuntos, instrucciones) se descarta
    """
    tokens = text.split()
    if not tokens:
        return text, 0

    # Encontrar la posición del tipo de vía (puede venir precedida de barrio/localidad)
    via_start = next((idx for idx, t in enumerate(tokens) if _VIA_TYPE_RE.match(t)), None)
    if via_start is None:
        return text, 0  # sin tipo de vía reconocido → no modificar

    parts: list[str] = [tokens[via_start]]
    i = via_start + 1

    # Si quedaron dos tipos de vía consecutivos (p.ej. "AV" + "KRA"), usar el segundo
    while i < len(tokens) and _VIA_TYPE_RE.match(tokens[i]):
        parts[0] = tokens[i]
        i += 1

    coord_count = 0

    # Leer coordenadas (máx 3 números) con cardinales intercalados
    while i < len(tokens) and coord_count < 3:
        card, new_i = _next_cardinal(tokens, i)
        if card:
            parts.append(card)
            i = new_i
            continue
        if _COORD_TOK_RE.match(tokens[i]):
            tok = tokens[i]
            # Bloque de 4-5 dígitos puros → cruce + placa concatenados, separar
            if _SPLIT_COORD_RE.match(tok):
                parts.append(tok[:-2])      # primeros dígitos → número de cruce
                coord_count += 1
                if coord_count < 3:
                    parts.append(tok[-2:])  # últimos 2 → placa
                    coord_count += 1
            else:
                parts.append(tok)
                coord_count += 1
            i += 1
        else:
            break  # token no reconocido → fin del bloque de coordenadas

    # Cardinal trailing (después del 3.er número)
    card, i = _next_cardinal(tokens, i)
    if card:
        parts.append(card)

    # Extraer solo complementos conocidos; ignorar el resto
    complementos: list[str] = []
    nombre_edificio: str | None = None
    while i < len(tokens):
        tok = tokens[i]
        if tok in _COMP_ABBREV:
            abbrev = _COMP_ABBREV[tok]
            i += 1
            if i < len(tokens) and _COMP_VAL_RE.match(tokens[i]):
                complementos.append(f"{abbrev} {tokens[i]}")
                i += 1
            else:
                complementos.append(abbrev)
                # "EDIFICIO" sin número después suele venir seguido del nombre
                # propio del edificio ("EDIFICIO CALLEJA PARK"), no de ruido a
                # descartar. Se captura y se agrega al final de la dirección.
                # Letras sueltas (torres/bloques en numeración romana, p.ej.
                # "PARK I") se descartan por ambiguas; se corta al llegar a
                # otro complemento conocido (p.ej. "APT").
                if abbrev == 'ED':
                    nombre_tokens: list[str] = []
                    while i < len(tokens) and _NAME_TOK_RE.match(tokens[i]) and tokens[i] not in _COMP_ABBREV:
                        if len(tokens[i]) > 1:
                            nombre_tokens.append(tokens[i])
                        i += 1
                    if nombre_tokens:
                        nombre_edificio = ' '.join(nombre_tokens)
        else:
            i += 1  # descartar: nombre de conjunto, instrucción, etc.

    # APTO siempre primero entre los complementos (antes de bloque, torre,
    # piso, etc.), sin importar en qué orden aparecieron en el texto original.
    # sort() es estable: preserva el orden relativo entre los demás complementos.
    complementos.sort(key=lambda c: 0 if c.split()[0] == 'APTO' else 1)
    parts.extend(complementos)
    if nombre_edificio:
        parts.append(nombre_edificio)

    return ' '.join(parts), coord_count


def ajustar_dir_leonisa(raw: str) -> str:
    """
    Transforma una dirección al formato Leonisa (mínimo espacio, sin ruido).

    Es independiente de mayúsculas/minúsculas/Title Case en la entrada: todo se
    normaliza a mayúsculas desde el primer paso.

    Ejemplos:
      "carrera 78 K  # 50   53 casa"                                        → "KRA 78K 50 53 CS"
      "Kra.81H 51C-81 sur"                                                  → "KRA 81H 51C 81 SUR"
      "cll 54C sur 88I 65 Conjunto Residencial Tangara 1 Torre 4 Apto 1106" → "CLL 54C SUR 88I 65 APTO 1106 TO 4"
      "CLL 51 SUR 87D-79 PISO 1 ENTREGAR DE LUNES A VIERNES 8 AM A 5 PM"   → "CLL 51 SUR 87D 79 PS 1"
      "carretera 80 45 30"                                                  → "KRA 80 45 30"
      "avenida caracas 53 20 sur"                                           → "KRA 14 53 20 SUR"
      "carrera 15 40 20 bloque 2 apto 501"                                  → "KRA 15 40 20 APTO 501 BL 2"
      "carrera 15 40 20 edificio 5 apto 302"                                → "KRA 15 40 20 APTO 302 ED 5"
      "cll 80 45"  (sin placa: solo 2 coordenadas)                          → "CLL 80 45" (mayúsculas, sin reordenar)
      "GUAYACAN DE LA PLAZACL 48 SUR 39 57 AP 566"  (tipo de vía pegado
       al nombre del conjunto, sin espacio)                                → "CLL 48 SUR 39 57 APTO 566"
    """
    if not isinstance(raw, str) or not raw.strip():
        return ""

    text = raw.upper().strip()

    # 1. Comas, puntos y símbolos de grado → espacio  ("KRA.81H" → "KRA 81H", "N°" → "N ")
    text = text.replace(",", " ").replace(".", " ").replace("°", " ").replace("º", " ")

    # 2. # → espacio
    text = text.replace("#", " ")

    # 2b. Indicadores de "número" usados como separador → eliminar
    #     NO., NRO, NUM, NUMERO son equivalentes a #. "N" suelto (con espacios
    #     a ambos lados, no pegado a un dígito) también se usa así en algunos
    #     archivos — se elimina aquí, ANTES del paso 8 (unir letra suelta), para
    #     que no se confunda con una letra de coordenada real como "78 K"→"78K".
    text = re.sub(r'\b(?:NUMERO|NRO|NUM|NR|NO|N)\b', ' ', text)

    # 3. Guión entre cualquier par alfanumérico → espacio
    #    "50-53"→"50 53",  "87D-79"→"87D 79",  "81-J"→"81 J",  "86C-69-A"→"86C 69 A"
    #    Lookahead/lookbehind (zero-width) para no consumir los vecinos y así
    #    resolver cadenas como "93-B-08" en un solo paso sin perder el segundo guión.
    text = re.sub(r'(?<=[A-Z0-9])\s*-\s*(?=[A-Z0-9])', ' ', text)

    # 4. Insertar espacio entre letra y dígito contiguos
    #    ("CALLE56F" → "CALLE 56F", "99D19" → "99D 19", "49C27" → "49C 27")
    text = re.sub(r'([A-Z])(\d)', r'\1 \2', text)

    # 4b. Separar tipo de vía pegado al final de la palabra anterior
    #     ("GUAYACAN DE LA PLAZACL 48 SUR" → "GUAYACAN DE LA PLAZA CL 48 SUR")
    text = _VIA_PEGADA_RE.sub(r' \1', text)

    # 5. Sustituir tipo de vía
    for pattern, repl in _VIA_MAP:
        text = re.sub(pattern, repl, text)

    # 6. Separar dígito pegado a cardinal: "27SUR" → "27 SUR", "16NORTE" → "16 NORTE"
    text = re.sub(
        r'(\d+)(SUR\s+ESTE|SUR\s+OESTE|NORTE\s+ESTE|NORTE\s+OESTE|SUR|NORTE|ESTE|OESTE)\b',
        r'\1 \2', text,
    )

    # 7. Mover dígito antepuesto a keyword de complemento: "3PISO" → "PISO 3", "4TORRE" → "TORRE 4"
    _KW_PATTERN = r'APARTAMENTO|APTO|APT|TORRE|TRR|PISO|BLOQUE|BLQ|INTERIOR|INT|LOCAL|CASA|MZA|EDIFICIO|EDIF|OFICINA|OFI|CONSULTORIO|CONSUL|CONS'
    text = re.sub(rf'(\d+)({_KW_PATTERN})\b', r'\2 \1', text)

    # 8. Unir número + letra suelta: "78 K" → "78K", "87 D" → "87D"
    #    Excluye "P": es la abreviatura de "PISO" (ver _COMP_ABBREV) y debe
    #    quedar como token de complemento separado, no fundirse en la
    #    coordenada anterior ("60 P 7" → "60 P 7", no "60P 7").
    text = re.sub(r'(\d+)\s+([A-OQ-Z])(?!\w)', r'\1\2', text)

    # 8b. Unir número + token "letras+BIS": "81 GBIS" → "81GBIS"
    #     Cubre el caso donde el BIS viene pegado a la letra del número ("GBis" como un token)
    text = re.sub(r'(\d+)\s+([A-Z]+BIS)\b', r'\1\2', text)

    # 9. Unir BIS al token anterior cuando BIS es un token separado: "87D BIS" → "87DBIS".
    #    La letra es opcional: "14 BIS" → "14BIS" (sin letra de por medio, el
    #    coordinador de tokens no reconocía "BIS" suelto y abortaba todo el
    #    parseo, dejando la dirección completa sin normalizar).
    text = re.sub(r'(\d+[A-Z]*)\s+BIS\b', r'\1BIS', text)

    # 10. Unir alfanumérico + letra suelta: "88IBIS A"→"88IBISA", "57ABIS B"→"57ABISB"
    #     Corre después de BIS para capturar la letra que le sigue al BIS.
    #     Excluye "P" por la misma razón que el paso 8.
    text = re.sub(r'(\d+[A-Z]+)\s+([A-OQ-Z])(?!\w)', r'\1\2', text)

    # 11. Colapsar espacios
    text = re.sub(r'\s+', ' ', text).strip()

    # 12. Parser de tokens: coordenadas + complementos, descarta ruido
    result, coord_count = _parse_y_limpiar(text)

    # Validación: una dirección válida necesita vía + 3 coords (número, cruce, placa).
    # Si el parser extrajo menos de 3, no reordenamos con confianza — pero se
    # devuelve `text` (ya en mayúsculas, con tipo de vía y cardinales ya
    # sustituidos) en vez del `raw` original, para que el resultado nunca
    # quede en minúsculas aunque no se pueda validar la estructura completa.
    if coord_count < 3:
        return text

    return result


def procesar_archivo_leonisa(contenido: bytes) -> AjusteDireccionesResult:
    """Lee un .txt separado por | (sin encabezado, latin-1) y normaliza la columna
    de dirección (índice COL_DIRECCION). Lanza ValueError si el archivo no tiene
    suficientes columnas."""
    df = pd.read_csv(
        io.BytesIO(contenido), sep="|", header=None, encoding=ENCODING, dtype=str
    )

    if df.shape[1] <= COL_DIRECCION:
        raise ValueError(
            f"El archivo solo tiene {df.shape[1]} columna(s). "
            f"Se necesitan al menos {COL_DIRECCION + 1}."
        )

    df[COL_DIRECCION] = df[COL_DIRECCION].apply(ajustar_dir_leonisa)
    df = df.fillna("")

    return AjusteDireccionesResult(
        total_filas=len(df),
        total_columnas=df.shape[1],
        col_direccion=COL_DIRECCION,
        col_nombre=COL_NOMBRE if df.shape[1] > COL_NOMBRE else None,
        filas=df.astype(str).values.tolist(),
    )


def generar_txt_leonisa(filas: list[list[str]]) -> bytes:
    """Reconstruye el .txt separado por | (sin encabezado, latin-1) a partir de
    las filas (ya editadas por el usuario)."""
    df = pd.DataFrame(filas)
    buffer = io.StringIO()
    df.to_csv(buffer, sep="|", header=False, index=False)
    return buffer.getvalue().encode(ENCODING)


def procesar_archivo_vehigrupo(contenido: bytes) -> AjusteDireccionesResult:
    """Lee un .txt de ancho fijo (288 caracteres/línea, CRLF, latin-1, sin
    encabezado) del Banco Vehigrupo y normaliza el campo dirección
    (columnas 106-170). Lanza ValueError si alguna línea es más corta de lo
    esperado."""
    lineas = contenido.decode(ENCODING).splitlines()

    filas: list[list[str]] = []
    for n, linea in enumerate(lineas, start=1):
        if len(linea) < VHG_LINE_LEN:
            raise ValueError(
                f"La línea {n} tiene {len(linea)} caracteres; se esperaban "
                f"al menos {VHG_LINE_LEN} (formato de ancho fijo Vehigrupo)."
            )

        campos = [linea[inicio:fin] for inicio, fin in VHG_FIELDS]
        campos[VHG_COL_DIRECCION] = ajustar_dir_leonisa(campos[VHG_COL_DIRECCION].strip())
        filas.append(campos)

    return AjusteDireccionesResult(
        total_filas=len(filas),
        total_columnas=len(VHG_FIELDS),
        col_direccion=VHG_COL_DIRECCION,
        col_nombre=VHG_COL_NOMBRE,
        filas=filas,
    )


def generar_txt_vehigrupo(filas: list[list[str]]) -> bytes:
    """Reconstruye el .txt de ancho fijo (288 caracteres/línea, CRLF, latin-1)
    del Banco Vehigrupo a partir de las filas (ya editadas por el usuario). El
    campo dirección se rellena con espacios hasta su ancho original (65); si
    quedó más largo no se trunca (la línea resultante queda más larga)."""
    ancho_direccion = VHG_FIELDS[VHG_COL_DIRECCION][1] - VHG_FIELDS[VHG_COL_DIRECCION][0]

    lineas: list[str] = []
    for fila in filas:
        campos = list(fila)
        direccion = campos[VHG_COL_DIRECCION].strip()
        campos[VHG_COL_DIRECCION] = direccion.ljust(ancho_direccion)
        lineas.append("".join(campos))

    return ("\r\n".join(lineas) + "\r\n").encode(ENCODING)
