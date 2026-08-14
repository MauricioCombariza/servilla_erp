from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personal import Personal
from app.services.bases_web import fetch_pendientes_courier
from app.services.excel_utils import construir_excel

_MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

COLUMNAS_EXCEL = [
    "serial", "orden", "cod_men", "f_emi", "no_entidad", "nombred",
    "dirdes1", "cod_sec", "ciudad1", "dpto1", "retorno", "ret_esc", "motivo",
]

COLUMNAS_EXCEL_MENSUAL = ["tipo_personal", "courier", *COLUMNAS_EXCEL]

TIPOS_PERSONAL = ("courier_externo", "mensajero")

_NOMBRE_INVALIDO_RE = re.compile(r"[^A-Za-z0-9_-]")


def _slug_archivo(nombre: str) -> str:
    normalizado = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    return _NOMBRE_INVALIDO_RE.sub("", normalizado.replace(" ", "_")) or "courier"


async def _get_personal_activo(db: AsyncSession, tipo_personal: str) -> list[Personal]:
    result = await db.execute(
        select(Personal)
        .where(Personal.tipo_personal == tipo_personal, Personal.activo == True)  # noqa: E712
        .order_by(Personal.nombre_completo)
    )
    return list(result.scalars().all())


async def _get_personal_activo_todos(db: AsyncSession) -> dict[str, list[Personal]]:
    result = await db.execute(
        select(Personal)
        .where(Personal.tipo_personal.in_(TIPOS_PERSONAL), Personal.activo == True)  # noqa: E712
        .order_by(Personal.nombre_completo)
    )
    por_tipo: dict[str, list[Personal]] = defaultdict(list)
    for persona in result.scalars().all():
        por_tipo[persona.tipo_personal].append(persona)
    return por_tipo


def _codigos_numericos(personas: list[Personal]) -> dict[int, Personal]:
    """Mapea codigo numérico -> Personal, descartando códigos no numéricos
    (ej. 'CE99'), igual que updateDashboard.py::cargar_courier_externo."""
    out: dict[int, Personal] = {}
    for p in personas:
        try:
            out[int(p.codigo)] = p
        except (TypeError, ValueError):
            continue
    return out


def _agrupar_por_cod_men(rows: list[dict]) -> dict[str, list[dict]]:
    """Agrupa filas de histo por cod_men y deduplica por serial dentro de cada
    grupo (igual a drop_duplicates('serial', keep='first') del script original)."""
    agrupado: dict[str, list[dict]] = defaultdict(list)
    vistos: dict[str, set] = defaultdict(set)
    for row in rows:
        cod_men = str(row["cod_men"])
        serial = row["serial"]
        if serial in vistos[cod_men]:
            continue
        vistos[cod_men].add(serial)
        agrupado[cod_men].append(row)
    return agrupado


def _anomes_valido(anomes: str) -> bool:
    return len(anomes) == 7 and anomes[4] == "."


def mes_label_desde_anomes(anomes: str) -> str | None:
    if not _anomes_valido(anomes):
        return None
    anio, mes = anomes.split(".")
    try:
        return f"{_MESES_ES[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return None


def calcular_desglose_mensual(rows: list[dict]) -> list[dict]:
    conteo: dict[str, int] = defaultdict(int)
    for row in rows:
        anomes = (row.get("f_emi") or "")[:7]  # 'YYYY.MM'
        if not _anomes_valido(anomes):
            continue
        conteo[anomes] += 1

    desglose = []
    for anomes in sorted(conteo):
        etiqueta = mes_label_desde_anomes(anomes)
        if etiqueta is None:
            continue
        desglose.append({"mes": etiqueta, "pendientes": conteo[anomes]})
    return desglose


async def get_pendientes_por_personal(
    db: AsyncSession, tipo_personal: str, dias_corte: int = 60,
) -> list[dict]:
    personas = await _get_personal_activo(db, tipo_personal)
    codigos_map = _codigos_numericos(personas)
    if not codigos_map:
        return []

    rows = await fetch_pendientes_courier(list(codigos_map.keys()), dias_corte)
    agrupado = _agrupar_por_cod_men(rows)

    resultado = []
    for codigo, persona in codigos_map.items():
        filas = agrupado.get(str(codigo), [])
        if not filas:
            continue
        email = persona.email
        resultado.append({
            "cod_men": persona.codigo,
            "nombre": persona.nombre_completo,
            "email": email,
            "tiene_email": bool(email and "@" in email),
            "pendientes": len(filas),
            "desglose_mensual": calcular_desglose_mensual(filas),
        })
    resultado.sort(key=lambda r: r["nombre"])
    return resultado


async def get_resumen_mensual(db: AsyncSession, dias_corte: int = 60) -> list[dict]:
    """Total de pendientes por mes, combinando courier_externo + mensajero."""
    por_tipo = await _get_personal_activo_todos(db)
    codigos_map: dict[int, Personal] = {}
    for tipo in TIPOS_PERSONAL:
        codigos_map.update(_codigos_numericos(por_tipo.get(tipo, [])))
    if not codigos_map:
        return []

    rows = await fetch_pendientes_courier(list(codigos_map.keys()), dias_corte)
    agrupado = _agrupar_por_cod_men(rows)

    conteo: dict[str, dict[str, int]] = defaultdict(lambda: {"courier_externo": 0, "mensajero": 0})
    for codigo, persona in codigos_map.items():
        for fila in agrupado.get(str(codigo), []):
            anomes = (fila.get("f_emi") or "")[:7]
            if not _anomes_valido(anomes):
                continue
            conteo[anomes][persona.tipo_personal] += 1

    resultado = []
    for anomes in sorted(conteo):
        etiqueta = mes_label_desde_anomes(anomes)
        if etiqueta is None:
            continue
        c = conteo[anomes]
        resultado.append({
            "anomes": anomes,
            "mes": etiqueta,
            "courier_externo": c["courier_externo"],
            "mensajero": c["mensajero"],
            "total": c["courier_externo"] + c["mensajero"],
        })
    return resultado


async def get_pendientes_mes(db: AsyncSession, anomes: str, dias_corte: int = 60) -> list[dict]:
    """Pendientes de un mes específico, combinando courier_externo + mensajero."""
    por_tipo = await _get_personal_activo_todos(db)
    codigos_map: dict[int, Personal] = {}
    for tipo in TIPOS_PERSONAL:
        codigos_map.update(_codigos_numericos(por_tipo.get(tipo, [])))
    if not codigos_map:
        return []

    rows = await fetch_pendientes_courier(list(codigos_map.keys()), dias_corte)
    agrupado = _agrupar_por_cod_men(rows)

    resultado = []
    for codigo, persona in codigos_map.items():
        for fila in agrupado.get(str(codigo), []):
            if (fila.get("f_emi") or "")[:7] != anomes:
                continue
            enriquecida = dict(fila)
            enriquecida["tipo_personal"] = persona.tipo_personal
            enriquecida["courier"] = persona.nombre_completo
            resultado.append(enriquecida)

    resultado.sort(key=lambda r: (r["tipo_personal"], r["courier"], r.get("f_emi") or ""))
    return resultado


async def get_pendientes_courier_individual(
    db: AsyncSession, codigo: str, tipo_personal: str, dias_corte: int = 60,
) -> tuple[Personal, list[dict]] | None:
    result = await db.execute(
        select(Personal).where(
            Personal.codigo == codigo,
            Personal.tipo_personal == tipo_personal,
            Personal.activo == True,  # noqa: E712
        )
    )
    persona = result.scalar_one_or_none()
    if persona is None:
        return None
    try:
        codigo_int = int(persona.codigo)
    except (TypeError, ValueError):
        return persona, []

    rows = await fetch_pendientes_courier([codigo_int], dias_corte)
    agrupado = _agrupar_por_cod_men(rows)
    return persona, agrupado.get(str(codigo_int), [])


def nombre_archivo_excel(persona: Personal) -> str:
    return f"pendientes_{persona.codigo}_{_slug_archivo(persona.nombre_completo)}.xlsx"


def construir_excel_courier(nombre: str, filas: list[dict]) -> bytes:
    titulo = "Pendientes de entrega" + (f" - {nombre}" if nombre else "")
    widths = [16, 10, 10, 12, 26, 26, 30, 10, 16, 12, 10, 10, 20]
    return construir_excel(titulo, COLUMNAS_EXCEL, filas, widths)


def construir_excel_mensual(mes_label: str, filas: list[dict]) -> bytes:
    titulo = f"Pendientes de entrega - {mes_label}"
    widths = [16, 26, 16, 10, 10, 12, 26, 26, 30, 10, 16, 12, 10, 10, 20]
    return construir_excel(titulo, COLUMNAS_EXCEL_MENSUAL, filas, widths)
