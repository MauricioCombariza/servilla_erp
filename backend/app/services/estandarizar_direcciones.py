"""Estandarización de direcciones colombianas (CL/CR/DG/TR + placa).

Copia sin cambios de la lógica de `dirnum/estandarizar_direcciones_v3.py` del
dashboard de Streamlit (la que usa `Devoluciones_iMile.py` para sacar la
localidad). Se trae tal cual para que la sectorización del ERP dé exactamente
los mismos resultados; la parte que dependía de archivos Excel quedó en
`sectorizacion_service.py`, que ahora lee la tabla `sectorizacion_limites`.

Cambios respecto a dirnum (aprobados por el usuario):
  - 2026-10-08: "CLLL" (error de digitación frecuente) se acepta como calle.
  - 2026-10-08: "Carretera" y "Carera" se aceptan como carrera.
"""

import re

import pandas as pd

# ========== FUNCIONES DE ESTANDARIZACION ==========

def preprocesar_direccion(direccion):
    """
    Preprocesamiento: limpia ruido antes de la estandarizacion.
    - Corta en ~~~ (toma primera parte)
    - Elimina parentesis y su contenido
    - Elimina puntos
    - Maneja tipos compuestos (AVDA calle, AC, AK)
    - Reemplaza No/No./numero por espacio
    - Maneja formato invertido (nums antes del tipo)
    - Descarta prefijos de ciudad
    """
    # Normalizar tildes/acentos en tipos de via
    # No se quita la tilde de 'é' a propósito: "esté" (verbo) es una palabra
    # distinta de "este" (cardinal) y quitarle la tilde las volvía indistinguibles,
    # causando falsos positivos de cardinal ESTE en frases como "la persona que esté".
    tildes = {'á': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u',
              'Á': 'A', 'Í': 'I', 'Ó': 'O', 'Ú': 'U'}
    for t, s in tildes.items():
        direccion = direccion.replace(t, s)

    # Cortar en ~~~ (toma primera parte)
    if '~~~' in direccion:
        direccion = direccion.split('~~~')[0]

    # Eliminar contenido entre parentesis
    direccion = re.sub(r'\([^)]*\)', ' ', direccion)

    # Eliminar puntos
    direccion = re.sub(r'\.', ' ', direccion)

    # Avenidas con nombre propio → equivalente numérico
    nombres_vias = {
        r'\bAV\w*\s+(?:EL\s+)?DORADO\b': 'CL 26',
        r'\bAV\w*\s+(?:DE\s+LAS\s+|LAS\s+)?AMERICAS\b': 'CL 6',
        r'\bAV\w*\s+BOYACA\b': 'CR 72',
        r'\bAV\w*\s+CIUDAD\s+DE\s+CALI\b': 'CR 86',
        r'\bAV\w*\s+CARACAS\b': 'CR 14',
    }
    for patron, reemplazo in nombres_vias.items():
        direccion = re.sub(patron, reemplazo, direccion, flags=re.IGNORECASE)

    # AV + número (sin nombre) → CR (Avenida/Carrera): "AV 9" → "CR 9"
    direccion = re.sub(r'\b(?:AV|AVENIDA)\s+(\d)', r'CR \1', direccion, flags=re.IGNORECASE)

    # Tipos compuestos: AVDA calle/call → CL (eliminar AVDA antes de calle/call)
    direccion = re.sub(r'\bAVDA\s+', '', direccion, flags=re.IGNORECASE)
    # AC (Avenida Calle) → CL, AK (Avenida Carrera) → CR
    direccion = re.sub(r'\bAC\b', 'CL', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\bAK\b', 'CR', direccion, flags=re.IGNORECASE)

    # No / No. / numero / n (antes de digito) → espacio (equivalentes a #)
    direccion = re.sub(r'\bnumero\b', ' ', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\b(No|Nu|Nom)\b', ' ', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\bn(?=\d)', ' ', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\bn\b(?=\s*\d)', ' ', direccion, flags=re.IGNORECASE)

    # Normalizar espacios
    direccion = re.sub(r'\s+', ' ', direccion).strip()

    # Separar tipo pegado a numero antes de buscar: "call100" → "call 100"
    direccion = re.sub(
        r'\b(calle|call|cl|cll|clll|clle|carrera|carretera|carera|carre|crra|crr|cr|kr|kra|cra|car|diagonal|dig|dg|transversal|trasversal|transv|trv|tv|tr|avenida|av)(\d)',
        r'\1 \2', direccion, flags=re.IGNORECASE
    )

    # Buscar primer tipo de via reconocido
    tipo_pattern = (
        r'\b(calle|call|cl|cll|clll|clle|carrera|carretera|carera|carre|crra|crr|cr|kr|kra|cra|car|'
        r'diagonal|dig|dg|transversal|trasversal|transv|trv|tv|tr|avenida|av)\b'
    )
    match = re.search(tipo_pattern, direccion, flags=re.IGNORECASE)

    if match:
        before = direccion[:match.start()].strip()
        from_type = direccion[match.start():]

        # Extraer numeros del texto antes del tipo
        nums = re.findall(r'\d+[A-Za-z]?', before)

        if nums and not re.search(r'[a-zA-Z]{3,}', re.sub(r'\d+[A-Za-z]?', '', before).strip()):
            # Formato invertido: "28B-21 Calle 74" → "Calle 74 28B 21"
            nums_str = ' '.join(nums)
            # Insertar nums despues del tipo+via
            tipo_via_match = re.match(
                r'(\w+\s+\d+[A-Za-z]*(?:\s*bis\s*[A-Za-z]?)?)(.*)',
                from_type, re.IGNORECASE
            )
            if tipo_via_match:
                tipo_via = tipo_via_match.group(1)
                resto = tipo_via_match.group(2)
                direccion = f"{tipo_via} {nums_str}{resto}"
            else:
                direccion = f"{from_type} {nums_str}"
        else:
            # Prefijo de ciudad/texto → descartar
            direccion = from_type

    direccion = re.sub(r'\s+', ' ', direccion).strip()
    return direccion


def normalizar_tipo_via(direccion):
    tipos_via = {
        r'\b(calle|call|cl|cll|clll|clle)\b': 'CL',
        r'\b(carrera|carretera|carera|carre|crra|crr|cr|kr|kra|cra|car)\b': 'CR',
        r'\b(diagonal|dig|dg)\b': 'DG',
        r'\b(transversal|trasversal|transv|trv|tv|tr)\b': 'TR',
        r'\b(avenida|av)\b': 'AV'
    }
    for patron, reemplazo in tipos_via.items():
        direccion = re.sub(patron, reemplazo, direccion, flags=re.IGNORECASE)
    return direccion


def separar_componentes_pegados(direccion):
    # Separar tipo pegado a numero: "calle75" → "calle 75", "call100" → "call 100"
    direccion = re.sub(
        r'\b(calle|call|cl|cll|clll|clle|carrera|carretera|carera|carre|crra|crr|cr|kr|kra|cra|car|diagonal|dig|dg|transversal|trasversal|transv|trv|tv|tr|avenida|av)(\d)',
        r'\1 \2', direccion, flags=re.IGNORECASE
    )
    # Separar # pegado: "#67" → "# 67"
    direccion = re.sub(r'#(\d)', r'# \1', direccion)
    # Eliminar "NO" pegado a numero+letra (NO = #): "23GNO" → "23G"
    direccion = re.sub(r'(\d+[A-Za-z]?)NO\b', r'\1', direccion, flags=re.IGNORECASE)
    # Separar cardinal pegado a numero: "16sur" → "16 sur", "20este" → "20 este"
    direccion = re.sub(
        r'(\d+)(sur\s*este|sureste|sur\s*oeste|suroeste|norte\s*este|noreste|'
        r'norte\s*oeste|noroeste|sur|norte|este|oeste)\b',
        r'\1 \2', direccion, flags=re.IGNORECASE
    )
    # Separar bis pegado: "79Fbis" → "79F bis"
    direccion = re.sub(r'(\d+[A-Za-z]?)(bis)\b', r'\1 \2', direccion, flags=re.IGNORECASE)
    # Separar letra+digitos: "28b17" → "28b 17" (loop para cascadas: "75A27a28" → "75A 27a 28")
    while True:
        nueva = re.sub(r'(\d+[A-Za-z])(\d+)', r'\1 \2', direccion)
        if nueva == direccion:
            break
        direccion = nueva
    # Separar 5+ digitos: ultimos 2 son placa: "11537" → "115 37"
    direccion = re.sub(r'(?<!\d)(\d{3,})(\d{2})(?!\d)', r'\1 \2', direccion)
    # Separar 4 digitos en pares: "3539" → "35 39"
    direccion = re.sub(r'(?<!\d)(\d{2})(\d{2})(?!\d)', r'\1 \2', direccion)
    return direccion


def limpiar_caracteres_especiales(direccion):
    direccion = re.sub(r'[#\-():/+]', ' ', direccion)
    direccion = re.sub(r'[,~]', ' ', direccion)
    direccion = re.sub(r'\s+', ' ', direccion)
    return direccion.strip()


def extraer_punto_cardinal(direccion):
    # Primero: extraer cardinal del medio entre dos números: "48B Sur 40 ..." → "48B 40 ..."
    # No requiere $ al final, funciona con texto adicional después
    m_mid = re.search(
        r'(\d+[A-Za-z]*)\s+(Sur\s*Este|Sureste|Sur\s*Oeste|Suroeste|'
        r'Norte\s*Este|Noreste|Norte\s*Oeste|Noroeste|Sur|Norte|Este|Oeste)\s+(\d+[A-Za-z]*)',
        direccion, flags=re.IGNORECASE
    )
    cardinal_medio = None
    if m_mid:
        cardinal_medio = m_mid.group(2)
        # Remover el cardinal del medio, mantener todo lo demás
        direccion = (direccion[:m_mid.start()] + m_mid.group(1) + ' ' +
                     m_mid.group(3) + direccion[m_mid.end():])
        direccion = re.sub(r'\s+', ' ', direccion).strip()

    # Cardinal después de número seguido de texto no-numérico (ruido):
    # "61 sur Multifamiliar Choco" → extraer "sur", quitar del string
    # El texto que sigue NO debe ser otro cardinal (para no romper "SUR ESTE" compuesto)
    m_post = re.search(
        r'(\d+[A-Za-z]*)\s+(Sur\s*Este|Sureste|Sur\s*Oeste|Suroeste|'
        r'Norte\s*Este|Noreste|Norte\s*Oeste|Noroeste|Sur|Norte|Este|Oeste)'
        r'\s+(?!Este\b|Oeste\b|Sur\b|Norte\b)([A-Za-z]{3,})',
        direccion, flags=re.IGNORECASE
    )
    if m_post and not cardinal_medio:
        cardinal_medio = m_post.group(2)
        # Remover solo el cardinal, mantener el número antes y el texto después
        direccion = (direccion[:m_post.start()] + m_post.group(1) + ' ' +
                     m_post.group(3) + direccion[m_post.end():])
        direccion = re.sub(r'\s+', ' ', direccion).strip()

    patron = (
        r'\b(SUR\s*ESTE|SUREST|SURESTE|SUR\s*OESTE|SUROESTE|'
        r'NORTE\s*ESTE|NORESTE|NOREST|NORTE\s*OESTE|NOROESTE|'
        r'SUR|NORTE|ESTE|OESTE|EST|SUL)\s*$'
    )
    match = re.search(patron, direccion, flags=re.IGNORECASE)
    if match:
        cardinal = match.group(1).upper().strip()
        if cardinal in ('EST', 'ESTE'):
            cardinal = 'ESTE'
        elif cardinal in ('SURESTE', 'SUREST'):
            cardinal = 'SUR ESTE'
        elif cardinal == 'SUROESTE':
            cardinal = 'SUR OESTE'
        elif cardinal in ('NORESTE', 'NOREST'):
            cardinal = 'NORTE ESTE'
        elif cardinal == 'NOROESTE':
            cardinal = 'NORTE OESTE'
        cardinal = re.sub(r'\s+', ' ', cardinal)
        direccion_sin_cardinal = direccion[:match.start()].strip()
        return direccion_sin_cardinal, cardinal

    # Si se encontró cardinal en el medio (entre números), usarlo
    if cardinal_medio:
        cardinal_medio = cardinal_medio.upper().strip()
        if cardinal_medio in ('EST', 'ESTE'):
            cardinal_medio = 'ESTE'
        elif cardinal_medio in ('SURESTE', 'SUREST'):
            cardinal_medio = 'SUR ESTE'
        elif cardinal_medio == 'SUROESTE':
            cardinal_medio = 'SUR OESTE'
        elif cardinal_medio in ('NORESTE', 'NOREST'):
            cardinal_medio = 'NORTE ESTE'
        elif cardinal_medio == 'NOROESTE':
            cardinal_medio = 'NORTE OESTE'
        cardinal_medio = re.sub(r'\s+', ' ', cardinal_medio)
        return direccion, cardinal_medio

    return direccion, None


def eliminar_info_adicional(direccion):
    palabras_eliminar = [
        r'\bAP\b.*', r'\bAPO\b.*', r'\bapto\w*.*', r'\bapartamento\w*.*',
        r'\bBL\d*\b', r'\bbloque\w*.*',
        r'\bTO\b.*', r'\btorre\w*.*',
        r'\bMZ\b.*', r'\bmanzana\b.*',
        r'\bCA\b.*', r'\bcasa\b.*',
        r'\bLC\b.*', r'\blocal\b.*',
        r'\bED\b.*', r'\bedificio\b.*',
        r'\bOF\b.*', r'\boficina\b.*',
        r'\bCONJ\b.*', r'\bconjunto\b.*',
        r'\bBarrios?\b.*', r'\bBogota.*', r'\bCundinamarca.*',
        r'\b(?:primer|segundo|tercer|cuarto|quinto)\b.*',
        r'\bPiso.*', r'\bPS\b.*',
        r'\bINT\b.*', r'\binterior\b.*',
        r'\bEST\b.*',
        r'\bSUPERMANZANA.*', r'\bSUPER\s*MANZ.*',
        r'\bSU\s*$',
        r'\bTRR\b.*', r'\bCS\b.*',
        r'\bTORRES\b.*', r'\bARBOLEDA\b.*',
        r'\bBUZON\b.*', r'\bPAQUETES\b.*',
        r'\bUnidad\b.*', r'\bmetropolis\b.*',
        r'\bCc\b.*', r'\bMac\b.*',
        r'\bvilla\b.*',
        r'\bSalamanca\b.*', r'\bresidencial\b.*',
        r'\bparque\b.*',
        r'\bbodega\b.*',
        r'\bpeluqueria\b.*',
        r'\betapa\b.*',
        r'\b\d+er\b', r'\b\d+do\b', r'\b\d+ro\b',
        r'\bD\s*C\b',
    ]
    for patron in palabras_eliminar:
        direccion = re.sub(patron, '', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\s+', ' ', direccion).strip()
    return direccion


def pegar_letras_a_numeros(direccion):
    # Pegar bis a numeros: "79F bis" → "79Fbis"
    direccion = re.sub(r'(\d+[A-Za-z]?)\s+(bis)\b', r'\1\2', direccion, flags=re.IGNORECASE)
    # Pegar letra suelta que sigue a un "bis" ya pegado: "67fBis A" → "67fBisA"
    direccion = re.sub(r'(\d+[A-Za-z]?bis)\s+([A-Za-z])\b', r'\1\2', direccion, flags=re.IGNORECASE)
    # Letra suelta seguida de OTRO numero: "66 C30" → "66C 30" (la letra es del
    # numero anterior; los digitos que la siguen son un componente aparte -la
    # placa- y deben quedar separados, no pegados a la letra)
    direccion = re.sub(r'(\d+)\s+([A-Za-z])(\d+)', r'\1\2 \3', direccion)
    # Pegar letras sueltas a numeros: "21 A" → "21A"
    direccion = re.sub(r'(\d+)\s+([A-Za-z])(?=\s|$)', r'\1\2', direccion)
    # Re-pegar bis despues de letra: "63D bis" → "63Dbis" (para "63 D bis" → "63D" → "63Dbis")
    direccion = re.sub(r'(\d+[A-Za-z])\s+(bis)\b', r'\1\2', direccion, flags=re.IGNORECASE)
    # Simplificar letras repetidas: "102AA" → "102A"
    direccion = re.sub(r'(\d+)([A-Za-z])\2+', r'\1\2', direccion)
    return direccion


def convertir_mayusculas(direccion):
    return direccion.upper()


def extraer_componentes(direccion):
    patron = r'\b(CL|CR|DG|TR|AV)\s+(\d+[A-Za-z]*(?:BIS)?[A-Za-z]?)\s+(\d+[A-Za-z]*)\s+(\d+[A-Za-z]*)'
    match = re.search(patron, direccion, flags=re.IGNORECASE)
    if match:
        return (match.group(1).upper(), match.group(2).upper(),
                match.group(3).upper(), match.group(4).upper())
    return None, None, None, None


def reconstruir_direccion(tipo, via1, via2, numero, cardinal=None):
    if all([tipo, via1, via2, numero]):
        base = f"{tipo} {via1} {via2} {numero}"
        return f"{base} {cardinal}" if cardinal else base
    return None


def estandarizar_direccion(direccion_original):
    if pd.isna(direccion_original) or direccion_original == '':
        return None
    direccion = direccion_original

    # Paso 0: Preprocesamiento (~~~, parentesis, puntos, No, formato invertido)
    direccion = preprocesar_direccion(direccion)

    # Paso 1: Separar componentes pegados
    direccion = separar_componentes_pegados(direccion)

    # Paso 2: Limpiar caracteres especiales
    direccion = limpiar_caracteres_especiales(direccion)

    # Paso 3: Simplificar letras repetidas sueltas
    direccion = re.sub(r'\b([A-Z])\1+\b', r'\1', direccion, flags=re.IGNORECASE)

    # Paso 3.5: Eliminar "D C" / "DC" (Distrito Capital) antes de extraer cardinal
    direccion = re.sub(r'\bD\s*C\b', '', direccion, flags=re.IGNORECASE)
    direccion = re.sub(r'\s+', ' ', direccion).strip()

    # Paso 3.7: pegar letra suelta a número precedente cuando va seguida de cardinal
    # "52 b sur" → "52b sur"  para que extraer_punto_cardinal lo reconozca
    direccion = re.sub(
        r'(\d+)\s+([A-Za-z])\s+(sur\s*este|sur\s*oeste|norte\s*este|norte\s*oeste|sur|norte|este|oeste)\b',
        r'\1\2 \3', direccion, flags=re.IGNORECASE
    )
    direccion = re.sub(r'\s+', ' ', direccion).strip()

    # Paso 4: Extraer punto cardinal (tambien maneja cardinal en medio)
    direccion, cardinal = extraer_punto_cardinal(direccion)

    # Paso 5: Eliminar info adicional
    direccion = eliminar_info_adicional(direccion)

    # Paso 6: Pegar letras a numeros y bis
    direccion = pegar_letras_a_numeros(direccion)

    # Paso 7: Normalizar tipo de via
    direccion = normalizar_tipo_via(direccion)

    # Paso 7.5: Eliminar segundo tipo de via
    # Primero: quitar TYPE+NUM duplicado: "CR 52 CR 52 78" → "CR 52 78"
    direccion = re.sub(
        r'(\b(?:CL|CR|DG|TR|AV)\s+(\d+[A-Za-z]*))\s+(?:CL|CR|DG|TR|AV)\s+\2(?=\s|$)',
        r'\1', direccion, flags=re.IGNORECASE
    )
    # Luego: quitar TYPE separador no duplicado: "CL 71A CR 29B 14" → "CL 71A 29B 14"
    direccion = re.sub(
        r'(\b(?:CL|CR|DG|TR|AV)\s+\d+[A-Za-z]*(?:BIS[A-Za-z]?)?)\s+(?:CL|CR|DG|TR|AV)\s+',
        r'\1 ', direccion, flags=re.IGNORECASE
    )

    # Paso 8: Mayusculas
    direccion = convertir_mayusculas(direccion)

    # Paso 9: Extraer componentes
    tipo, via1, via2, numero = extraer_componentes(direccion)

    # Paso 10: Reconstruir
    return reconstruir_direccion(tipo, via1, via2, numero, cardinal)


# ========== FUNCIONES DE DIRECCION NUMERICA ==========

def codificar_letras(letras):
    """
    Codifica combinaciones de letras a 3 dígitos.

    Tabla de codificación (ordenada, BIS es el menor, A la letra mas pequeña):
      Sin letras     -> 100
      BIS            -> 101
      BIS+Y          -> 101 + pos(Y)         [A=1..Z=26]
      X              -> 129 + 29*pos(X)       [A=0..Z=25]
      X+BIS          -> 129 + 29*pos(X) + 1
      X+BIS+Y        -> 129 + 29*pos(X) + 1 + pos(Y)  [A=1..Z=26]
    """
    if not letras:
        return 100

    letras = letras.upper().strip()
    if not letras:
        return 100

    # BIS solo
    if letras == 'BIS':
        return 101

    # BIS + letra (ej: BISA, BISB)
    m = re.match(r'^BIS([A-Z])$', letras)
    if m:
        return 101 + (ord(m.group(1)) - ord('A') + 1)

    # Letra sola (ej: A, F, D)
    m = re.match(r'^([A-Z])$', letras)
    if m:
        return 129 + 29 * (ord(m.group(1)) - ord('A'))

    # Letra + BIS (ej: DBIS, FBIS)
    m = re.match(r'^([A-Z])BIS$', letras)
    if m:
        return 129 + 29 * (ord(m.group(1)) - ord('A')) + 1

    # Letra + BIS + letra (ej: CBISA, DBISB)
    m = re.match(r'^([A-Z])BIS([A-Z])$', letras)
    if m:
        return (129 + 29 * (ord(m.group(1)) - ord('A'))
                + 1 + (ord(m.group(2)) - ord('A') + 1))

    # Fallback: primera letra
    if letras[0].isalpha():
        return 129 + 29 * (ord(letras[0]) - ord('A'))

    return 100


def parsear_componente_via(componente):
    """
    Separa un componente de vía en (número, letras).
    Ej: '41F' -> (41, 'F'), '51DBIS' -> (51, 'DBIS'), '33' -> (33, '')
    """
    m = re.match(r'^(\d+)(.*)', componente.upper())
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, ''


def extraer_componentes_completos(dir_estandarizada):
    """
    Descompone una dirección YA ESTANDARIZADA (salida de estandarizar_direccion)
    en sus componentes tipados: tipo de vía, número/letras de cada vía, placa y
    cardinal. Es el punto de entrada pensado para que otros módulos del proyecto
    (ej. utils/sectores_finales.py, utils/direcciones.py) dejen de tener su propio
    regex de limpieza y solo consuman esta descomposición ya hecha por dirnum.

    Retorna un dict:
      {'tipo': 'CL', 'via1_num': 78, 'via1_letras': 'K',
       'via2_num': 50, 'via2_letras': '', 'placa': 53, 'cardinal': None}
    o None si la dirección no se pudo descomponer en los 4 componentes básicos.
    """
    if not dir_estandarizada:
        return None

    partes = dir_estandarizada.upper().split()
    # Mismo patrón de separar el cardinal del final que usan _coordenadas_dir,
    # generar_direccion_numerica y _extraer_placa — se repite aquí en vez de
    # extraerlo a una función compartida para no alterar esas funciones ya
    # probadas; ver Note 2 en _extraer_placa() para la justificación completa.
    compuestos = {'SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE'}
    cardinal = None
    if len(partes) >= 2 and ' '.join(partes[-2:]) in compuestos:
        cardinal = ' '.join(partes[-2:])
        partes = partes[:-2]
    elif partes and partes[-1] in ('SUR', 'NORTE', 'ESTE', 'OESTE', 'SUL'):
        cardinal = 'SUR' if partes[-1] == 'SUL' else partes[-1]
        partes = partes[:-1]

    if len(partes) < 4:
        return None

    tipo = partes[0]
    via1_num, via1_letras = parsear_componente_via(partes[1])
    via2_num, via2_letras = parsear_componente_via(partes[2])
    placa_num, _          = parsear_componente_via(partes[3])

    return {
        'tipo':        tipo,
        'via1_num':    via1_num,
        'via1_letras': via1_letras,
        'via2_num':    via2_num,
        'via2_letras': via2_letras,
        'placa':       placa_num,
        'cardinal':    cardinal,
    }

