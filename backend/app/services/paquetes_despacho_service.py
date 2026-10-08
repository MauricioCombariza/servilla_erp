"""Guarda los paquetes de una base de despacho en `paquetes_despacho`, ya sectorizados.

Un serial que ya existe se reemplaza con los datos nuevos y vuelve a 'sin gestión'
(llega en un despacho nuevo, así que es un ingreso nuevo).
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, literal_column
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paquetes_despacho import ESTADO_SIN_GESTION, PaqueteDespacho
from app.services.sectorizacion_service import obtener_indice, sectorizar

# PostgreSQL acepta hasta 32.767 parámetros por sentencia; 1.000 filas x 10 columnas cabe holgado
_TAMANO_LOTE = 1000


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
