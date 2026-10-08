"""Guarda los paquetes de una base de despacho en `paquetes_despacho`, ya sectorizados.

Un serial que ya existe se reemplaza con los datos nuevos y vuelve a 'sin gestión'
(llega en un despacho nuevo, así que es un ingreso nuevo).
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paquetes_despacho import ESTADO_SIN_GESTION, PaqueteDespacho
from app.services.excel_utils import construir_excel
from app.services.sectorizacion_service import obtener_indice, sectorizar

# PostgreSQL acepta hasta 32.767 parámetros por sentencia; 1.000 filas x 10 columnas cabe holgado
_TAMANO_LOTE = 1000


# Nombres aceptados por columna interna (iMile exporta en inglés o en español);
# los mismos del sistema anterior (dashboard/pages_home/Ingreso_paquetes.py)
COL_ALIASES = {
    "serial": ["Waybill number", "Número de Guía"],
    "nombre": ["Recipient's name", "El nombre del destinatario"],
    "telefono": ["Customer phone", "Teléfono entrante"],
    "direccion": ["Address2", "Dirección detallada del destinatario"],
}

COLUMNAS_EXPORTAR = [
    "serial", "nombre", "telefono", "direccion", "direccion_estandarizada",
    "codigo_postal", "localidad", "zona", "f_emi", "estado",
]


class ColumnasFaltantesError(ValueError):
    def __init__(self, faltantes: list[str], columnas_archivo: list[str]):
        self.faltantes = faltantes
        self.columnas_archivo = columnas_archivo
        super().__init__(f"Columnas requeridas no encontradas: {', '.join(faltantes)}")


@dataclass(frozen=True)
class PaqueteEntrada:
    serial: str
    nombre: str | None = None
    telefono: str | None = None
    direccion: str | None = None


@dataclass
class ResultadoGuardado:
    creados: int = 0
    reemplazados: int = 0
    seriales_sin_sector: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.creados + self.reemplazados


def _texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


async def guardar_paquetes(
    db: AsyncSession, paquetes: list[PaqueteEntrada], f_emi: date
) -> ResultadoGuardado:
    # Si el mismo serial viene varias veces en el archivo, se queda el último
    # (además, un INSERT ... ON CONFLICT no puede tocar dos veces la misma fila).
    por_serial: dict[str, PaqueteEntrada] = {}
    for p in paquetes:
        serial = _texto(p.serial)
        if serial:
            por_serial[serial] = p

    resultado = ResultadoGuardado()
    if not por_serial:
        return resultado

    indice = await obtener_indice(db)
    filas = []
    for serial, p in por_serial.items():
        direccion = _texto(p.direccion)
        sector = sectorizar(direccion, indice)
        if sector.localidad is None:
            resultado.seriales_sin_sector.append(serial)
        filas.append({
            "serial": serial,
            "nombre": _texto(p.nombre),
            "telefono": _texto(p.telefono),
            "direccion": direccion,
            "direccion_estandarizada": sector.direccion_estandarizada,
            "codigo_postal": sector.codigo_postal,
            "localidad": sector.localidad,
            "zona": sector.zona,
            "f_emi": f_emi,
            "estado": ESTADO_SIN_GESTION,
        })

    for i in range(0, len(filas), _TAMANO_LOTE):
        lote = filas[i:i + _TAMANO_LOTE]
        stmt = insert(PaqueteDespacho).values(lote)
        reemplazar = {c: stmt.excluded[c] for c in lote[0] if c != "serial"}
        stmt = stmt.on_conflict_do_update(
            index_elements=[PaqueteDespacho.serial],
            set_={**reemplazar, "fecha_modificacion": func.now()},
        ).returning(literal_column("(xmax = 0)").label("creado"))  # xmax = 0 → fila recién insertada
        creados = (await db.execute(stmt)).scalars().all()
        resultado.creados += sum(1 for c in creados if c)
        resultado.reemplazados += sum(1 for c in creados if not c)

    # Un solo commit: o se guarda todo el despacho o nada
    await db.commit()
    return resultado


# ========== LECTURA DEL EXCEL ==========

def leer_excel_despacho(contenido: bytes) -> list[PaqueteEntrada]:
    """Excel de despacho → paquetes. Lanza ColumnasFaltantesError o ValueError (archivo ilegible/vacío)."""
    try:
        # dtype=str: los seriales numéricos no deben pasar por float ("3671050719461.0")
        df = pd.read_excel(io.BytesIO(contenido), engine="openpyxl", dtype=str)
    except Exception as e:  # cualquier archivo corrupto o que no sea Excel llega aquí
        raise ValueError(f"No se pudo leer el archivo Excel: {e}") from e
    if df.empty:
        raise ValueError("El archivo Excel está vacío.")

    columnas = [str(c).strip() for c in df.columns]
    df.columns = columnas
    col_map, faltantes = {}, []
    for interno, aliases in COL_ALIASES.items():
        encontrada = next((a for a in aliases if a in columnas), None)
        if encontrada:
            col_map[interno] = encontrada
        else:
            faltantes.append(f"{interno} (esperado: {' o '.join(aliases)})")
    if faltantes:
        raise ColumnasFaltantesError(faltantes, columnas)

    df = df.astype(object).where(df.notna(), None)
    return [
        PaqueteEntrada(
            serial=fila[col_map["serial"]],
            nombre=fila[col_map["nombre"]],
            telefono=fila[col_map["telefono"]],
            direccion=fila[col_map["direccion"]],
        )
        for _, fila in df.iterrows()
    ]


# ========== CONSULTA, CORRECCIÓN Y EXPORTACIÓN ==========

AVISO_NO_ESTA = "No está en la tabla"
AVISO_FUERA_DE_ZONA = "Fuera de zona"


@dataclass(frozen=True)
class Destino:
    serial: str
    ultimos_4: str
    en_tabla: bool
    direccion: str | None = None
    direccion_estandarizada: str | None = None
    localidad: str | None = None
    zona: str | None = None
    fuera_de_zona: bool = False
    aviso: str | None = None


async def buscar_destino(db: AsyncSession, serial: str) -> Destino:
    """Paso 2.6: serial escaneado → últimos 4 dígitos, dirección, localidad y zona.

    Un serial que no está en la tabla se informa, pero no es un error: el ingreso en
    iMile (2.5) se hace igual. Un paquete sin zona específica es "Fuera de zona" (2.7).
    """
    serial = serial.strip()
    ultimos_4 = serial[-4:]
    result = await db.execute(select(PaqueteDespacho).where(PaqueteDespacho.serial == serial))
    paquete = result.scalar_one_or_none()
    if paquete is None:
        return Destino(serial=serial, ultimos_4=ultimos_4, en_tabla=False, aviso=AVISO_NO_ESTA)

    fuera = paquete.zona is None
    return Destino(
        serial=serial,
        ultimos_4=ultimos_4,
        en_tabla=True,
        direccion=paquete.direccion,
        direccion_estandarizada=paquete.direccion_estandarizada,
        localidad=paquete.localidad,
        zona=paquete.zona,
        fuera_de_zona=fuera,
        aviso=AVISO_FUERA_DE_ZONA if fuera else None,
    )

async def listar_paquetes(
    db: AsyncSession,
    f_emi: date,
    zona: str | None = None,
    solo_sin_sector: bool = False,
) -> list[PaqueteDespacho]:
    q = select(PaqueteDespacho).where(PaqueteDespacho.f_emi == f_emi)
    if zona:
        q = q.where(PaqueteDespacho.zona == zona)
    if solo_sin_sector:
        q = q.where(PaqueteDespacho.localidad.is_(None))
    q = q.order_by(PaqueteDespacho.zona.nulls_first(), PaqueteDespacho.serial)
    return list((await db.execute(q)).scalars().all())


async def corregir_direccion(db: AsyncSession, serial: str, direccion: str) -> PaqueteDespacho | None:
    """Corrección manual de una dirección que no se pudo sectorizar; se vuelve a sectorizar."""
    result = await db.execute(select(PaqueteDespacho).where(PaqueteDespacho.serial == serial.strip()))
    paquete = result.scalar_one_or_none()
    if paquete is None:
        return None

    sector = sectorizar(direccion, await obtener_indice(db))
    paquete.direccion = direccion.strip()
    paquete.direccion_estandarizada = sector.direccion_estandarizada
    paquete.codigo_postal = sector.codigo_postal
    paquete.localidad = sector.localidad
    paquete.zona = sector.zona
    paquete.fecha_modificacion = func.now()
    await db.commit()
    await db.refresh(paquete)
    return paquete


def _filas_exportar(paquetes: list[PaqueteDespacho]) -> list[dict]:
    return [
        {c: (getattr(p, c).isoformat() if c == "f_emi" else getattr(p, c)) for c in COLUMNAS_EXPORTAR}
        for p in paquetes
    ]


def exportar_excel(paquetes: list[PaqueteDespacho], f_emi: date) -> bytes:
    return construir_excel(
        f"Paquetes sectorizados — {f_emi.isoformat()}",
        COLUMNAS_EXPORTAR,
        _filas_exportar(paquetes),
        [18, 28, 14, 45, 22, 12, 18, 8, 12, 16],
    )


def exportar_csv(paquetes: list[PaqueteDespacho]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNAS_EXPORTAR)
    writer.writeheader()
    writer.writerows(_filas_exportar(paquetes))
    # utf-8-sig: Excel abre bien tildes y ñ
    return buffer.getvalue().encode("utf-8-sig")
