"""Sectorización de direcciones: dirección → código postal → localidad, y zona específica.

Una sola tabla (`sectorizacion_limites`) guarda dos tipos de fila:
  - tipo 'codigo_postal': límites de calle/carrera de cada código postal de Bogotá
    y su localidad (antes limites_estandarizados.xlsx + localidad_codigo_postal_bogota.xlsx).
  - tipo 'zona': las 33 zonas específicas, con la paridad de placa que pertenece a
    la zona sobre cada vía límite (antes zonas_especificas.xlsx).

Los helpers de límites, coordenadas y paridad son copia sin cambios de
`dirnum/estandarizar_direcciones_v3.py`, y el índice se arma desde filas de la
tabla en vez de leer los Excel.

Cambio respecto a dirnum (aprobado por el usuario el 2026-10-08): en las zonas, la
paridad de placa solo se revisa en la vía principal de la dirección; la vía que
cruza se evalúa por cuadras (ver _cumple_limite_cruce).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sectorizacion import SectorizacionLimite
from app.services.estandarizar_direcciones import (
    codificar_letras,
    estandarizar_direccion,
    parsear_componente_via,
)

TIPO_CODIGO_POSTAL = "codigo_postal"
TIPO_ZONA = "zona"


# ========== HELPERS DE LÍMITES (copia de dirnum) ==========

def _parsear_via_limite(via_str):
    """
    Parsea una vía de límite estandarizada en (tipo, num, letras_code, cardinal).
    Ej: 'CL 63'      → ('CL', 63, 100, None)
        'CL 49 SUR'  → ('CL', 49, 100, 'SUR')
        'CR 30 ESTE' → ('CR', 30, 100, 'ESTE')
    """
    if not via_str or (isinstance(via_str, float) and pd.isna(via_str)):
        return None, None, None, None
    partes = str(via_str).upper().split()

    cardinal = None
    compuestos = {'SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE'}
    if len(partes) >= 3 and ' '.join(partes[-2:]) in compuestos:
        cardinal = ' '.join(partes[-2:])
        partes = partes[:-2]
    elif len(partes) >= 2 and partes[-1] in ('SUR', 'NORTE', 'ESTE', 'OESTE'):
        cardinal = partes[-1]
        partes = partes[:-1]

    if len(partes) < 2:
        return None, None, None, cardinal

    tipo = partes[0]
    m = re.match(r'^(\d+)(.*)', partes[1])
    if not m:
        return tipo, None, None, cardinal

    num = int(m.group(1))
    letras_code = codificar_letras(m.group(2).strip())
    return tipo, num, letras_code, cardinal


def _posicion_cl(tipo, num, letras_code, cardinal):
    """
    Posición N-S como entero comparable.
    Positivo = Norte (mayor = más al norte).
    Negativo = Sur  (más negativo = más al sur).
    Válido para tipos CL y DG.
    """
    if tipo not in ('CL', 'DG') or num is None:
        return None
    pos = num * 10000 + (letras_code - 100)
    return -pos if cardinal == 'SUR' else pos


def _posicion_cr(tipo, num, letras_code, cardinal=None):
    """
    Posición E-O como entero comparable (mayor = más al Oeste).
    Válido para tipos CR y TR.
    Cardinal ESTE → posición negativa (al oriente del eje CR 1).
    """
    if tipo not in ('CR', 'TR') or num is None:
        return None
    pos = num * 10000 + (letras_code - 100)
    return -pos if cardinal == 'ESTE' else pos


def _coordenadas_dir(dir_estandarizada):
    """
    Extrae (cl_pos, cr_pos) de una dirección estandarizada.
      cl_pos : posición N-S (int, positivo=Norte, negativo=Sur)
      cr_pos : posición E-O (int, mayor=Oeste)
    Para CL/DG: via1=calle (cl_pos), via2=carrera (cr_pos).
    Para CR/TR: via1=carrera (cr_pos), via2=calle (cl_pos).
    """
    if not dir_estandarizada:
        return None, None

    partes = dir_estandarizada.upper().split()

    cardinal = None
    compuestos = {'SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE'}
    if len(partes) >= 2 and ' '.join(partes[-2:]) in compuestos:
        cardinal = ' '.join(partes[-2:])
        partes = partes[:-2]
    elif partes and partes[-1] in ('SUR', 'NORTE', 'ESTE', 'OESTE', 'SUL'):
        cardinal = partes[-1]
        if cardinal == 'SUL':
            cardinal = 'SUR'
        partes = partes[:-1]

    if len(partes) < 4:
        return None, None

    tipo = partes[0]
    m1 = re.match(r'^(\d+)(.*)', partes[1])
    m2 = re.match(r'^(\d+)(.*)', partes[2])
    if not m1 or not m2:
        return None, None

    via1_num = int(m1.group(1))
    via1_let = codificar_letras(m1.group(2).strip())
    via2_num = int(m2.group(1))
    via2_let = codificar_letras(m2.group(2).strip())

    if tipo in ('CL', 'DG'):
        cl_p = via1_num * 10000 + (via1_let - 100)
        if cardinal == 'SUR':
            cl_p = -cl_p
        cr_p = via2_num * 10000 + (via2_let - 100)
        return cl_p, cr_p

    if tipo in ('CR', 'TR'):
        cr_p = via1_num * 10000 + (via1_let - 100)
        if cardinal == 'ESTE':
            cr_p = -cr_p
        cl_p = via2_num * 10000 + (via2_let - 100)
        if cardinal == 'SUR':
            cl_p = -cl_p
        return cl_p, cr_p

    return None, None


def _texto_paridad(valor):
    """'PAR'/'IMPAR' (cualquier mayúscula/espacio) -> True/False. Vacío -> None (sin restricción)."""
    # Note 1: pd.isna() detecta tanto None como NaN (celda vacía en el Excel leído por pandas).
    # Una comparación normal como "valor is None" no atraparía el NaN de pandas, por eso se
    # usa la función de pandas en vez del chequeo nativo de Python.
    if pd.isna(valor):
        return None
    v = str(valor).strip().upper()
    if v == 'PAR':
        return True
    if v == 'IMPAR':
        return False
    return None


def _extraer_placa(dir_estandarizada):
    """
    Extrae el número de placa (última componente de la dirección estandarizada),
    la misma que usa generar_direccion_numerica() para decidir el lado de la vía.
    Retorna int o None.
    """
    if not dir_estandarizada:
        return None
    partes = dir_estandarizada.upper().split()
    # Note 2: el cardinal ("SUR", "SUR ESTE", ...) va pegado al final de la dirección
    # estandarizada y no es parte de los 4 componentes tipo/via1/via2/numero, así que
    # hay que quitarlo antes de poder indexar partes[3] como la placa con seguridad.
    # Este mismo patrón de "separar cardinal, luego tomar partes[3]" ya se repite en
    # generar_direccion_numerica() y en _coordenadas_dir(); se duplica aquí en vez de
    # extraerlo a una función compartida para mantener el mismo estilo del archivo,
    # donde cada función de esta sección es autosuficiente.
    compuestos = {'SUR ESTE', 'SUR OESTE', 'NORTE ESTE', 'NORTE OESTE'}
    if len(partes) >= 2 and ' '.join(partes[-2:]) in compuestos:
        partes = partes[:-2]
    elif partes and partes[-1] in ('SUR', 'NORTE', 'ESTE', 'OESTE', 'SUL'):
        partes = partes[:-1]
    if len(partes) < 4:
        return None
    # partes[3] es siempre el numero/placa final, sin importar si la dirección
    # empieza con CL/DG (calle) o CR/TR (carrera) — ver extraer_componentes().
    placa_num, _ = parsear_componente_via(partes[3])
    return placa_num


def _cumple_limite(pos, minimo, par_en_min, maximo, par_en_max, placa_par):
    """
    True si `pos` (posición CL o CR de la dirección) cae dentro de [minimo, maximo].
    Si `pos` cae EXACTAMENTE sobre uno de los bordes y ese borde exige una paridad
    de placa (par_en_min/par_en_max), solo pasa si la placa de la dirección coincide.
    Un límite en None significa "sin restricción de ese lado".
    """
    # Note 7: pos=None ocurre cuando la dirección solo tiene componente de calle
    # (o solo de carrera) — por ejemplo direcciones donde _coordenadas_dir no pudo
    # calcular una de las dos coordenadas. Se retorna True (no descarta la zona
    # por esa dimensión) para no bloquear la otra dimensión, que sí se evaluará.
    if pos is None:
        return True

    if minimo is not None:
        if pos < minimo:
            return False
        # Note 8: pos == minimo es el caso "la dirección está sobre la calle/carrera
        # límite exacta". Ahí es donde entra la regla de paridad: si el límite exige
        # una paridad concreta (par_en_min no es None) y la placa de la dirección
        # también se pudo determinar (placa_par no es None), deben coincidir con !=
        # — si son iguales, placa_par != par_en_min es False y NO se rechaza la zona.
        if pos == minimo and par_en_min is not None and placa_par is not None and placa_par != par_en_min:
            return False

    if maximo is not None:
        if pos > maximo:
            return False
        # Note 9: mismo chequeo de Note 8, mirrorado para el límite superior (norte u oeste).
        if pos == maximo and par_en_max is not None and placa_par is not None and placa_par != par_en_max:
            return False

    # Si pos no violó ni el mínimo ni el máximo (incluyendo la paridad en los bordes),
    # la dirección cae dentro de esta dimensión de la zona.
    return True


def _cumple_limite_cruce(pos, minimo, maximo):
    """
    Límite sobre la vía que CRUZA (no la vía principal de la dirección).

    `CR 20 # 66-15` está en la cuadra entre la CL 66 y la CL 67: pertenece a la zona
    que empieza en la CL 66 y no a la que termina en ella, sea la placa par o impar.
    Con SUR / ESTE las posiciones son negativas y la cuadra va hacia valores más
    negativos (`# 20-15 SUR` está entre CL 20 SUR y CL 21 SUR).
    """
    if pos is None:
        return True
    if pos >= 0:
        return (minimo is None or pos >= minimo) and (maximo is None or pos < maximo)
    return (minimo is None or pos > minimo) and (maximo is None or pos <= maximo)


# ========== ÍNDICE DESDE LA TABLA ==========

@dataclass(frozen=True)
class LimiteSector:
    """Una fila de `sectorizacion_limites`, desacoplada de SQLAlchemy para poder probarla sin BD."""
    tipo: str
    nombre: str
    localidad: str | None
    limite_norte: str | None
    placas_norte: str | None
    limite_sur: str | None
    placas_sur: str | None
    limite_oriente: str | None
    placas_oriente: str | None
    limite_occidente: str | None
    placas_occidente: str | None
    orden: int


@dataclass(frozen=True)
class IndiceSectorizacion:
    zonas_postales: list[tuple]   # (n_dims, codigo_postal, cl_min, cl_max, cr_min, cr_max)
    zonas_especificas: list[dict]
    localidades: dict[str, str]   # codigo_postal -> localidad


@dataclass(frozen=True)
class ResultadoSectorizacion:
    direccion_estandarizada: str | None
    codigo_postal: str | None
    localidad: str | None
    zona: str | None


def _zona_postal(limite: LimiteSector) -> tuple | None:
    # Mismo criterio que _inicializar_zonas_postales de dirnum: se juntan las
    # posiciones CL/DG y CR/TR de los 4 límites sin importar en qué columna vengan,
    # y una dimensión solo restringe si tiene al menos 2 posiciones distintas.
    all_lim = [
        _parsear_via_limite(limite.limite_norte),
        _parsear_via_limite(limite.limite_sur),
        _parsear_via_limite(limite.limite_oriente),
        _parsear_via_limite(limite.limite_occidente),
    ]
    cl_vals = sorted({_posicion_cl(t, n, l, c) for t, n, l, c in all_lim} - {None})
    cr_vals = sorted({_posicion_cr(t, n, l, c) for t, n, l, c in all_lim} - {None})

    cl_valid = len(cl_vals) >= 2 and cl_vals[-1] > cl_vals[0]
    cr_valid = len(cr_vals) >= 2 and cr_vals[-1] > cr_vals[0]
    n_dims = (1 if cl_valid else 0) + (1 if cr_valid else 0)
    if n_dims == 0:
        return None  # Sin restricciones útiles: descartar

    return (
        n_dims,
        limite.nombre,
        cl_vals[0] if cl_valid else None,
        cl_vals[-1] if cl_valid else None,
        cr_vals[0] if cr_valid else None,
        cr_vals[-1] if cr_valid else None,
    )


def _zona_especifica(limite: LimiteSector) -> dict:
    # Mismo criterio que _inicializar_zonas_especificas de dirnum: la columna
    # "norte" no siempre trae la calle más al norte, así que se ordenan comparando
    # posiciones; oriente/occidente sí se toman tal cual vienen.
    t_n, n_n, l_n, c_n = _parsear_via_limite(limite.limite_norte)
    t_s, n_s, l_s, c_s = _parsear_via_limite(limite.limite_sur)
    t_e, n_e, l_e, c_e = _parsear_via_limite(limite.limite_oriente)
    t_o, n_o, l_o, c_o = _parsear_via_limite(limite.limite_occidente)

    pos_col_norte = _posicion_cl(t_n, n_n, l_n, c_n)
    par_col_norte = _texto_paridad(limite.placas_norte)
    pos_col_sur = _posicion_cl(t_s, n_s, l_s, c_s)
    par_col_sur = _texto_paridad(limite.placas_sur)

    if pos_col_norte is not None and pos_col_sur is not None and pos_col_norte < pos_col_sur:
        calle_norte, calle_norte_par = pos_col_sur, par_col_sur
        calle_sur, calle_sur_par = pos_col_norte, par_col_norte
    else:
        calle_norte, calle_norte_par = pos_col_norte, par_col_norte
        calle_sur, calle_sur_par = pos_col_sur, par_col_sur

    return {
        "nombre": limite.nombre,
        "calle_norte": calle_norte,
        "calle_norte_par": calle_norte_par,
        "calle_sur": calle_sur,
        "calle_sur_par": calle_sur_par,
        "carrera_este": _posicion_cr(t_e, n_e, l_e, c_e),
        "carrera_este_par": _texto_paridad(limite.placas_oriente),
        "carrera_oeste": _posicion_cr(t_o, n_o, l_o, c_o),
        "carrera_oeste_par": _texto_paridad(limite.placas_occidente),
    }


def construir_indice(limites: Iterable[LimiteSector]) -> IndiceSectorizacion:
    ordenados = sorted(limites, key=lambda lim: (lim.tipo, lim.orden))

    zonas_postales = []
    zonas_especificas = []
    localidades = {}
    for lim in ordenados:
        if lim.tipo == TIPO_CODIGO_POSTAL:
            if lim.localidad:
                localidades[lim.nombre] = lim.localidad
            zona = _zona_postal(lim)
            if zona is not None:
                zonas_postales.append(zona)
        elif lim.tipo == TIPO_ZONA:
            zonas_especificas.append(_zona_especifica(lim))

    # Más restrictivas primero (sort estable: a igual restricción manda el orden de la tabla)
    zonas_postales.sort(key=lambda z: -z[0])
    return IndiceSectorizacion(zonas_postales, zonas_especificas, localidades)


# ========== BÚSQUEDAS ==========

def buscar_codigo_postal(dir_estandarizada: str | None, indice: IndiceSectorizacion) -> str | None:
    addr_cl, addr_cr = _coordenadas_dir(dir_estandarizada)
    if addr_cl is None and addr_cr is None:
        return None

    for _, cp, cl_min, cl_max, cr_min, cr_max in indice.zonas_postales:
        cl_ok = True
        if addr_cl is not None and cl_min is not None:
            cl_ok = cl_min <= addr_cl <= cl_max

        cr_ok = True
        if addr_cr is not None and cr_min is not None:
            cr_ok = cr_min <= addr_cr <= cr_max

        if cl_ok and cr_ok:
            return cp

    return None


def buscar_localidad(dir_estandarizada: str | None, indice: IndiceSectorizacion) -> str | None:
    cp = buscar_codigo_postal(dir_estandarizada, indice)
    if cp is None:
        return None
    return indice.localidades.get(cp)


def buscar_zona(dir_estandarizada: str | None, indice: IndiceSectorizacion) -> str | None:
    """Nombre de la zona específica de la dirección, o None. Gana la primera zona (por orden)."""
    cl_pos, cr_pos = _coordenadas_dir(dir_estandarizada)
    if cl_pos is None and cr_pos is None:
        return None

    placa = _extraer_placa(dir_estandarizada)
    placa_par = (placa % 2 == 0) if placa is not None else None

    # La placa solo dice de qué lado de la VÍA PRINCIPAL está la dirección; la paridad
    # de los límites se revisa únicamente en esa dimensión (decisión 2026-10-08).
    via_principal_es_calle = dir_estandarizada.upper().split()[0] in ("CL", "DG")

    for z in indice.zonas_especificas:
        if via_principal_es_calle:
            cl_ok = _cumple_limite(cl_pos, z["calle_sur"], z["calle_sur_par"],
                                   z["calle_norte"], z["calle_norte_par"], placa_par)
        else:
            cl_ok = _cumple_limite_cruce(cl_pos, z["calle_sur"], z["calle_norte"])
        if not cl_ok:
            continue
        if via_principal_es_calle:
            cr_ok = _cumple_limite_cruce(cr_pos, z["carrera_este"], z["carrera_oeste"])
        else:
            cr_ok = _cumple_limite(cr_pos, z["carrera_este"], z["carrera_este_par"],
                                   z["carrera_oeste"], z["carrera_oeste_par"], placa_par)
        if not cr_ok:
            continue
        return z["nombre"]

    return None


def sectorizar(direccion: str | None, indice: IndiceSectorizacion) -> ResultadoSectorizacion:
    """Dirección tal como llega en la base de despacho → localidad y zona."""
    dir_std = estandarizar_direccion(direccion) if direccion else None
    if not dir_std:
        return ResultadoSectorizacion(None, None, None, None)

    cp = buscar_codigo_postal(dir_std, indice)
    return ResultadoSectorizacion(
        direccion_estandarizada=dir_std,
        codigo_postal=cp,
        localidad=indice.localidades.get(cp) if cp is not None else None,
        zona=buscar_zona(dir_std, indice),
    )


# ========== CARGA DESDE LA BD ==========

_indice_cache: IndiceSectorizacion | None = None


def limite_desde_modelo(fila: SectorizacionLimite) -> LimiteSector:
    return LimiteSector(
        tipo=fila.tipo,
        nombre=fila.nombre,
        localidad=fila.localidad,
        limite_norte=fila.limite_norte,
        placas_norte=fila.placas_norte,
        limite_sur=fila.limite_sur,
        placas_sur=fila.placas_sur,
        limite_oriente=fila.limite_oriente,
        placas_oriente=fila.placas_oriente,
        limite_occidente=fila.limite_occidente,
        placas_occidente=fila.placas_occidente,
        orden=fila.orden,
    )


async def obtener_indice(db: AsyncSession) -> IndiceSectorizacion:
    """Índice armado desde `sectorizacion_limites` activos; se cachea en memoria."""
    global _indice_cache
    if _indice_cache is None:
        result = await db.execute(
            select(SectorizacionLimite).where(SectorizacionLimite.activo.is_(True))
        )
        _indice_cache = construir_indice(limite_desde_modelo(f) for f in result.scalars().all())
    return _indice_cache


def invalidar_indice() -> None:
    """Llamar cuando se editen filas de `sectorizacion_limites`."""
    global _indice_cache
    _indice_cache = None
