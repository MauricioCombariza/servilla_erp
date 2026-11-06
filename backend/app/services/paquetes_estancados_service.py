"""Paquetes estancados: leídos al ingresar en una tula y todavía sin entregar después de N días.

- Ingreso: el primer `tula_seriales.fecha_escaneo` del serial.
- Entregado: el serial ya está en `seriales_gestion` (la descarga diaria de envíos con que se
  calculan las ventas). Mientras no aparezca ahí, sigue circulando en las instalaciones.
- Días: calendario, contados en hora de Bogotá desde el día del primer ingreso.
- Zona: la del último escaneo en tula; si no tiene, la de `paquetes_despacho`.
- Devoluciones: si el serial está en `devoluciones` ya va de vuelta al cliente, no espera
  entrega; se marca con su estado y por defecto no se lista.
- Lecturas descartadas: lo leído como paquete que no puede ser uno (código de tula, serial
  cortado o dos lecturas pegadas, o algo que iMile rechazó y no está en la base). Se marca
  con el motivo y por defecto no se lista. Ver `motivo_descarte`.
- Asignado a: el último día (desde el ingreso) con asignación. La reasignación serial por
  serial gana sobre la zona, igual que `_mensajero_actual` en asignacion_zonas_service.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.excel_utils import construir_excel_multi
from app.services.seriales_formato import RE_SERIAL_VALIDO, parece_codigo_tula

TZ = ZoneInfo("America/Bogota")
SIN_ASIGNAR = "Sin asignar"

DESCARTE_TULA = "Código de tula"
DESCARTE_FORMATO = "Serial incompleto o mal leído"
DESCARTE_RECHAZADO = "Rechazado por iMile y no está en la base"


def motivo_descarte(serial: str, es_codigo_tula: bool, en_base: bool, rechazado_imile: bool | None) -> str | None:
    """Por qué una lectura no es un paquete real; None si parece un paquete."""
    if es_codigo_tula or parece_codigo_tula(serial):
        return DESCARTE_TULA
    if not RE_SERIAL_VALIDO.match(serial):
        return DESCARTE_FORMATO
    if not en_base and rechazado_imile:
        return DESCARTE_RECHAZADO
    return None

_SQL = text("""
WITH ingreso AS (
    SELECT ts.serial,
           MIN(ts.fecha_escaneo) AS primer_ingreso,
           (MIN(ts.fecha_escaneo) AT TIME ZONE 'America/Bogota')::date AS dia_ingreso,
           COUNT(DISTINCT ts.tula_id) AS lecturas,
           bool_and(ts.imile_estado IN ('error', 'bloqueado')) AS rechazado_imile
    FROM tula_seriales ts
    GROUP BY ts.serial
),
pendientes AS (
    SELECT i.*, (CAST(:hoy AS date) - i.dia_ingreso) AS dias
    FROM ingreso i
    WHERE (CAST(:hoy AS date) - i.dia_ingreso) > :dias_min
      AND NOT EXISTS (SELECT 1 FROM seriales_gestion sg WHERE sg.serial = i.serial)
)
SELECT p.serial, p.primer_ingreso, p.dias, p.lecturas,
       COALESCE(ult.zona, pd.zona) AS zona,
       pd.localidad, pd.direccion, pd.nombre AS destinatario, pd.f_emi,
       asg_s.fecha AS fecha_serial, ps.codigo AS codigo_serial, ps.nombre_completo AS nombre_serial,
       asg_z.fecha AS fecha_zona, pz.codigo AS codigo_zona, pz.nombre_completo AS nombre_zona,
       im.estado AS imile_estado, dv.estado AS devolucion,
       pd.serial IS NOT NULL AS en_base, p.rechazado_imile,
       EXISTS (SELECT 1 FROM tulas t WHERE t.codigo = p.serial) AS es_codigo_tula
FROM pendientes p
LEFT JOIN paquetes_despacho pd ON pd.serial = p.serial
LEFT JOIN devoluciones dv ON dv.serial = p.serial
LEFT JOIN LATERAL (
    SELECT ts.zona FROM tula_seriales ts
    WHERE ts.serial = p.serial AND ts.zona IS NOT NULL
    ORDER BY ts.fecha_escaneo DESC LIMIT 1
) ult ON TRUE
LEFT JOIN LATERAL (
    SELECT a.fecha, a.personal_id FROM asignaciones_serial a
    WHERE a.serial = p.serial AND a.fecha >= p.dia_ingreso AND a.fecha <= CAST(:hoy AS date)
    ORDER BY a.fecha DESC LIMIT 1
) asg_s ON TRUE
LEFT JOIN personal ps ON ps.id = asg_s.personal_id
LEFT JOIN LATERAL (
    SELECT a.fecha, a.personal_id FROM asignaciones_zona a
    WHERE a.zona = COALESCE(ult.zona, pd.zona)
      AND a.fecha >= p.dia_ingreso AND a.fecha <= CAST(:hoy AS date)
    ORDER BY a.fecha DESC LIMIT 1
) asg_z ON TRUE
LEFT JOIN personal pz ON pz.id = asg_z.personal_id
LEFT JOIN LATERAL (
    SELECT a.estado FROM asignaciones_imile a
    WHERE a.serial = p.serial
    ORDER BY a.fecha DESC, a.fecha_envio DESC LIMIT 1
) im ON TRUE
ORDER BY p.dias DESC, zona, p.serial
""")


@dataclass(frozen=True)
class PaqueteEstancado:
    serial: str
    zona: str | None
    localidad: str | None
    direccion: str | None
    destinatario: str | None
    f_emi: date | None
    primer_ingreso: datetime
    dias: int
    lecturas: int  # en cuántas tulas se leyó
    codigo: str | None  # mensajero asignado; None = sin asignar
    mensajero: str | None
    fecha_asignacion: date | None
    origen_asignacion: str | None  # "serial" | "zona"
    imile_estado: str | None
    devolucion: str | None  # estado en `devoluciones`; None = no está en devolución
    motivo_descarte: str | None  # None = parece un paquete real


@dataclass(frozen=True)
class ListadoEstancados:
    paquetes: list[PaqueteEstancado]
    devoluciones_ocultas: int  # en devolución, no listados porque no se pidieron
    descartados_ocultos: int  # lecturas que no son paquetes, no listadas porque no se pidieron


@dataclass(frozen=True)
class GrupoEstancados:
    clave: str  # código del mensajero o nombre de la zona
    nombre: str
    paquetes: int
    max_dias: int


def hoy_bogota() -> date:
    return datetime.now(TZ).date()


def _resolver_asignacion(r) -> tuple[str | None, str | None, date | None, str | None]:
    if r.fecha_serial is not None and (r.fecha_zona is None or r.fecha_serial >= r.fecha_zona):
        return r.codigo_serial, r.nombre_serial, r.fecha_serial, "serial"
    if r.fecha_zona is not None:
        return r.codigo_zona, r.nombre_zona, r.fecha_zona, "zona"
    return None, None, None, None


async def listar_estancados(
    db: AsyncSession,
    dias_min: int = 2,
    zona: str | None = None,
    codigo: str | None = None,
    hoy: date | None = None,
    incluir_devoluciones: bool = False,
    incluir_descartados: bool = False,
) -> ListadoEstancados:
    """Paquetes con más de `dias_min` días desde su primer ingreso y aún sin entregar.
    `codigo` filtra por mensajero; `codigo=""` deja solo los sin asignar."""
    hoy = hoy or hoy_bogota()
    filas = (await db.execute(_SQL, {"hoy": hoy, "dias_min": dias_min})).all()
    paquetes = []
    for r in filas:
        cod, nombre, fecha_asig, origen = _resolver_asignacion(r)
        paquetes.append(PaqueteEstancado(
            serial=r.serial, zona=r.zona, localidad=r.localidad, direccion=r.direccion,
            destinatario=r.destinatario, f_emi=r.f_emi, primer_ingreso=r.primer_ingreso,
            dias=r.dias, lecturas=r.lecturas, codigo=cod, mensajero=nombre,
            fecha_asignacion=fecha_asig, origen_asignacion=origen, imile_estado=r.imile_estado,
            devolucion=r.devolucion,
            motivo_descarte=motivo_descarte(r.serial, r.es_codigo_tula, r.en_base, r.rechazado_imile),
        ))
    if zona is not None:
        paquetes = [p for p in paquetes if p.zona == zona]
    if codigo is not None:
        paquetes = [p for p in paquetes if (p.codigo or "") == codigo.strip()]
    descartados = 0
    if not incluir_descartados:
        descartados = sum(1 for p in paquetes if p.motivo_descarte is not None)
        paquetes = [p for p in paquetes if p.motivo_descarte is None]
    devoluciones = 0
    if not incluir_devoluciones:
        devoluciones = sum(1 for p in paquetes if p.devolucion is not None)
        paquetes = [p for p in paquetes if p.devolucion is None]
    return ListadoEstancados(paquetes, devoluciones, descartados)


def _agrupar(paquetes: list[PaqueteEstancado], clave, nombre) -> list[GrupoEstancados]:
    grupos: dict[str, GrupoEstancados] = {}
    for p in paquetes:
        k = clave(p)
        g = grupos.get(k)
        grupos[k] = GrupoEstancados(
            clave=k, nombre=nombre(p),
            paquetes=(g.paquetes if g else 0) + 1,
            max_dias=max(g.max_dias if g else 0, p.dias),
        )
    return sorted(grupos.values(), key=lambda g: (-g.paquetes, -g.max_dias, g.clave))


def por_mensajero(paquetes: list[PaqueteEstancado]) -> list[GrupoEstancados]:
    return _agrupar(paquetes, lambda p: p.codigo or "", lambda p: p.mensajero or SIN_ASIGNAR)


def por_zona(paquetes: list[PaqueteEstancado]) -> list[GrupoEstancados]:
    return _agrupar(paquetes, lambda p: p.zona or "", lambda p: p.zona or "Sin zona")


_COLUMNAS = ["Serial", "Días", "Primer ingreso", "Zona", "Localidad", "Dirección", "Destinatario",
             "F. emisión", "Código", "Mensajero", "Asignado el", "Asignado por", "Estado iMile", "Devolución", "Descarte", "Tulas"]
_WIDTHS = [22, 7, 18, 12, 18, 40, 28, 12, 8, 30, 12, 12, 14, 12, 30, 7]


def construir_excel(paquetes: list[PaqueteEstancado], dias_min: int, hoy: date) -> bytes:
    filas = [{
        "Serial": p.serial,
        "Días": p.dias,
        "Primer ingreso": p.primer_ingreso.astimezone(TZ).strftime("%Y-%m-%d %H:%M"),
        "Zona": p.zona,
        "Localidad": p.localidad,
        "Dirección": p.direccion,
        "Destinatario": p.destinatario,
        "F. emisión": p.f_emi.isoformat() if p.f_emi else None,
        "Código": p.codigo,
        "Mensajero": p.mensajero or SIN_ASIGNAR,
        "Asignado el": p.fecha_asignacion.isoformat() if p.fecha_asignacion else None,
        "Asignado por": p.origen_asignacion,
        "Estado iMile": p.imile_estado,
        "Devolución": p.devolucion,
        "Descarte": p.motivo_descarte,
        "Tulas": p.lecturas,
    } for p in paquetes]
    resumen = [{"Mensajero": g.nombre, "Código": g.clave, "Paquetes": g.paquetes, "Máx. días": g.max_dias}
               for g in por_mensajero(paquetes)]
    zonas = [{"Zona": g.nombre, "Paquetes": g.paquetes, "Máx. días": g.max_dias} for g in por_zona(paquetes)]
    titulo = f"Paquetes con más de {dias_min} días sin entregar — corte {hoy.isoformat()}"
    return construir_excel_multi([
        ("Detalle", titulo, _COLUMNAS, filas, _WIDTHS),
        ("Por mensajero", titulo, ["Mensajero", "Código", "Paquetes", "Máx. días"], resumen, [30, 8, 10, 10]),
        ("Por zona", titulo, ["Zona", "Paquetes", "Máx. días"], zonas, [14, 10, 10]),
    ])
