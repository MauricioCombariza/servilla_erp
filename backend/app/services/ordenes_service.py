"""
Lógica de negocio para carga masiva de órdenes desde CSV.

Formato esperado del CSV:
  Columnas requeridas: orden, serial, fecha_recepcion, nombre_cliente, tipo_servicio, ambito
  Columnas opcionales: planilla, cod_men, f_emi

Reglas de procesamiento:
  - Solo se procesan filas con fecha_recepcion >= 2026-01-01.
  - Paso 1: un serial por fila → seriales_gestion.
      · Serial nuevo       → INSERT.
      · Serial existente, estado = 'pendiente' → UPDATE campos operativos.
      · Serial existente, otro estado          → no se toca.
  - Paso 2: agrupar por orden → ordenes (crear o actualizar totales).
"""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clientes import Cliente, PrecioCliente
from app.models.personal import Personal
from app.schemas.ordenes import CargaMasivaResult

logger = logging.getLogger(__name__)

COLUMNAS_REQUERIDAS = {"orden", "serial", "fecha_recepcion", "nombre_cliente", "tipo_servicio", "ambito"}
DATE_CORTE = date(2026, 1, 1)


async def _cargar_maestros(db: AsyncSession) -> tuple[dict, dict, dict, dict]:
    """Devuelve (clientes_by_name, precios_cli, precios_men, personal_by_code).

    clientes_by_name:  {nombre_lower -> cliente_id}
    precios_cli:       {(cliente_id, tipo_servicio, ambito) -> precio_entrega}
    precios_men:       {(cliente_id, tipo_servicio, ambito) -> costo_mensajero_entrega}
    personal_by_code:  {codigo_upper -> personal_id}
    """
    rows_c = (await db.execute(select(Cliente.id, Cliente.nombre_empresa))).all()
    clientes_by_name = {r.nombre_empresa.strip().lower(): r.id for r in rows_c}

    rows_p = (
        await db.execute(
            select(
                PrecioCliente.cliente_id,
                PrecioCliente.tipo_servicio,
                PrecioCliente.ambito,
                PrecioCliente.precio_entrega,
                PrecioCliente.costo_mensajero_entrega,
            ).where(PrecioCliente.activo == True)  # noqa: E712
        )
    ).all()

    precios_cli: dict = {}
    precios_men: dict = {}
    for r in rows_p:
        key = (r.cliente_id, r.tipo_servicio.lower(), r.ambito.lower())
        precios_cli[key] = float(r.precio_entrega or 0)
        precios_men[key] = float(r.costo_mensajero_entrega or 0)

    rows_per = (
        await db.execute(
            select(Personal.id, Personal.codigo).where(Personal.activo == True)  # noqa: E712
        )
    ).all()
    personal_by_code = {r.codigo.strip().upper(): r.id for r in rows_per}

    return clientes_by_name, precios_cli, precios_men, personal_by_code


def _parse_date(val: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime as dt
            return dt.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


async def procesar_csv(
    contenido: bytes,
    db: AsyncSession,
) -> CargaMasivaResult:
    # ── Leer CSV ──────────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(contenido), dtype=str, low_memory=False).dropna(how="all")
    except Exception as e:
        return CargaMasivaResult(
            total_filas=0, filas_ignoradas=0, seriales_nuevos=0, seriales_actualizados=0,
            ordenes_nuevas=0, ordenes_actualizadas=0, errores=[f"Error leyendo CSV: {e}"]
        )

    faltantes = COLUMNAS_REQUERIDAS - set(df.columns)
    if faltantes:
        return CargaMasivaResult(
            total_filas=len(df), filas_ignoradas=0, seriales_nuevos=0, seriales_actualizados=0,
            ordenes_nuevas=0, ordenes_actualizadas=0,
            errores=[f"Columnas faltantes: {', '.join(sorted(faltantes))}"],
        )

    # ── Normalizar ────────────────────────────────────────────────────────────
    df["_orden"] = df["orden"].str.strip().str.replace(r"\.0$", "", regex=True)
    df["_es_local"] = df["ambito"].str.lower().str.strip().str.contains("bog", na=False)

    # Columnas opcionales
    df["_planilla"] = df["planilla"].str.strip() if "planilla" in df.columns else ""
    df["_cod_men"] = df["cod_men"].str.strip().str.upper() if "cod_men" in df.columns else ""

    # ── Filtro de fecha de corte ──────────────────────────────────────────────
    df["_fecha_parsed"] = df["fecha_recepcion"].apply(lambda x: _parse_date(str(x).strip()))
    total_filas = len(df)
    df = df[df["_fecha_parsed"].apply(lambda d: d is not None and d >= DATE_CORTE)].copy()
    filas_ignoradas = total_filas - len(df)

    errores: list[str] = []
    clientes_by_name, precios_cli, precios_men, personal_by_code = await _cargar_maestros(db)

    # ── Paso 1: seriales_gestion ──────────────────────────────────────────────
    sg_nuevos = 0
    sg_actualizados = 0

    for i, fila in df.iterrows():
        try:
            cliente_nom = str(fila["nombre_cliente"]).strip()
            id_cliente = clientes_by_name.get(cliente_nom.lower())
            if not id_cliente:
                errores.append(f"Fila {int(i)+2}: cliente '{cliente_nom}' no encontrado")  # type: ignore[arg-type]
                continue

            serial = str(fila["serial"]).strip()
            num_orden = str(fila["_orden"])
            fecha_parsed: date = fila["_fecha_parsed"]  # ya filtrada arriba

            tipo_ser = str(fila["tipo_servicio"]).lower().strip()
            ambito_val = "bogota" if fila["_es_local"] else "nacional"
            planilla_val = str(fila["_planilla"]) if fila["_planilla"] else ""
            cod_men_val = str(fila["_cod_men"]) if fila["_cod_men"] else ""

            precio_cli = precios_cli.get((id_cliente, tipo_ser, ambito_val), 0.0)
            precio_men = precios_men.get((id_cliente, tipo_ser, ambito_val), 0.0)
            mensajero_id = personal_by_code.get(cod_men_val) if cod_men_val else None

            # Nuevo → INSERT; existente con estado='pendiente' → UPDATE; otro estado → no-op
            result = await db.execute(
                text("""
                    INSERT INTO seriales_gestion
                        (serial, orden, planilla, f_emi, f_esc, cod_men, mensajero_id,
                         cliente_id, tipo_gestion, tipo_envio, ambito,
                         precio_cliente, precio_mensajero, estado, origen)
                    VALUES
                        (:serial, :orden, :planilla, :fecha, :fecha, :cod_men, :mensajero_id,
                         :cliente_id, 'Entrega', :tipo_envio, :ambito,
                         :precio_cli, :precio_men, 'pendiente', 'manual')
                    ON CONFLICT (serial) DO UPDATE SET
                        orden            = EXCLUDED.orden,
                        planilla         = EXCLUDED.planilla,
                        f_esc            = EXCLUDED.f_esc,
                        cod_men          = EXCLUDED.cod_men,
                        mensajero_id     = EXCLUDED.mensajero_id,
                        precio_cliente   = EXCLUDED.precio_cliente,
                        precio_mensajero = EXCLUDED.precio_mensajero,
                        origen           = EXCLUDED.origen
                    WHERE seriales_gestion.estado = 'pendiente'
                    RETURNING (xmax = 0) AS es_nuevo
                """),
                {
                    "serial": serial,
                    "orden": num_orden,
                    "planilla": planilla_val,
                    "fecha": fecha_parsed,
                    "cod_men": cod_men_val,
                    "mensajero_id": mensajero_id,
                    "cliente_id": id_cliente,
                    "tipo_envio": tipo_ser,
                    "ambito": ambito_val,
                    "precio_cli": precio_cli,
                    "precio_men": precio_men,
                },
            )
            row = result.fetchone()
            if row is not None:
                if row[0]:  # xmax = 0 → INSERT nuevo
                    sg_nuevos += 1
                else:       # xmax != 0 → UPDATE de pendiente
                    sg_actualizados += 1

        except Exception as e:
            errores.append(f"Fila {int(i)+2}: {e}")  # type: ignore[arg-type]

    # ── Paso 2: ordenes (agrupar por número de orden) ─────────────────────────
    resumen = (
        df.groupby(["_orden", "fecha_recepcion", "nombre_cliente", "tipo_servicio"])
        .agg(cant_local=("_es_local", "sum"), cant_nac=("_es_local", lambda x: (~x.astype(bool)).sum()))
        .reset_index()
    )

    ordenes_nuevas = 0
    ordenes_actualizadas = 0

    for _, grp in resumen.iterrows():
        try:
            cliente_nom = str(grp["nombre_cliente"]).strip()
            id_cliente = clientes_by_name.get(cliente_nom.lower())
            if not id_cliente:
                continue  # ya reportado en paso 1

            num_orden = str(grp["_orden"])
            fecha_parsed = _parse_date(str(grp["fecha_recepcion"]).strip())
            if not fecha_parsed:
                continue

            tipo_ser = str(grp["tipo_servicio"]).lower().strip()
            c_local = int(grp["cant_local"])
            c_nac = int(grp["cant_nac"])
            c_total = c_local + c_nac

            p_local = precios_cli.get((id_cliente, tipo_ser, "bogota"), 0.0)
            p_nac = precios_cli.get((id_cliente, tipo_ser, "nacional"), 0.0)
            v_total = (c_local * p_local) + (c_nac * p_nac)

            existing = (
                await db.execute(
                    text("SELECT id FROM ordenes WHERE numero_orden = :n"),
                    {"n": num_orden},
                )
            ).fetchone()

            if existing:
                await db.execute(
                    text("""
                        UPDATE ordenes
                        SET cantidad_total    = :total,
                            cantidad_recibido = :total,
                            valor_total       = :valor
                        WHERE id = :id
                    """),
                    {"total": c_total, "valor": v_total, "id": existing[0]},
                )
                ordenes_actualizadas += 1
            else:
                await db.execute(
                    text("""
                        INSERT INTO ordenes
                            (numero_orden, cliente_id, fecha_recepcion, tipo_servicio,
                             cantidad_total, cantidad_recibido, valor_total, estado)
                        VALUES
                            (:num, :cli, :fecha, :tipo, :total, :total, :valor, 'activa')
                    """),
                    {
                        "num": num_orden,
                        "cli": id_cliente,
                        "fecha": fecha_parsed,
                        "tipo": tipo_ser,
                        "total": c_total,
                        "valor": v_total,
                    },
                )
                ordenes_nuevas += 1

        except Exception as e:
            errores.append(f"Orden {grp.get('_orden', '?')}: {e}")

    await db.commit()
    logger.info(
        "Carga masiva: órdenes_nuevas=%d actualizadas=%d "
        "seriales_nuevos=%d actualizados=%d ignoradas=%d errores=%d",
        ordenes_nuevas, ordenes_actualizadas, sg_nuevos, sg_actualizados,
        filas_ignoradas, len(errores),
    )
    return CargaMasivaResult(
        total_filas=total_filas,
        filas_ignoradas=filas_ignoradas,
        seriales_nuevos=sg_nuevos,
        seriales_actualizados=sg_actualizados,
        ordenes_nuevas=ordenes_nuevas,
        ordenes_actualizadas=ordenes_actualizadas,
        errores=errores[:50],
    )
