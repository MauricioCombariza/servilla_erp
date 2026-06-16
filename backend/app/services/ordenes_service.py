"""
Lógica de negocio para carga masiva de órdenes desde CSV.

Soporta dos formatos de origen:

  Flujo 1 — CSV manual:
    Columnas: orden, serial, fecha_recepcion, nombre_cliente, tipo_servicio, ambito
    tipo_servicio y ambito vienen del archivo (se normalizan).
    Opcionales: planilla, cod_men

  Flujo 2 — iMile escáner (detectado por columna 'Waybill No.'):
    Columnas origen: 'Scan time', 'Waybill No.', 'DA'
    Transformaciones:
      - serial          = Waybill No.
      - fecha_recepcion = fecha de Scan time
      - orden           = "IM" + YYYYMMDD  (generado desde Scan time)
      - planilla        = mismo valor que orden
      - nombre_cliente  = 'Imile SAS' (fijo)
      - tipo_servicio   = 'paquete' (fijo)
      - ambito          = 'bogota' (fijo)
      - cod_men         = resuelto desde DA vía tabla personal (por nombre)

Reglas comunes:
  - Solo se procesan filas con fecha >= 2026-01-01.
  - Serial nuevo → INSERT; existente con estado='pendiente' → UPDATE; otro estado → no-op.
  - Al finalizar seriales, upsert en ordenes agrupando por número de orden.
"""
from __future__ import annotations

import io
import logging
from datetime import date

import pandas as pd
from sqlalchemy import ARRAY, String, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clientes import Cliente, MapeoCliente, PrecioCliente
from app.models.personal import Personal
from app.schemas.ordenes import CargaMasivaResult

logger = logging.getLogger(__name__)

DATE_CORTE = date(2026, 1, 1)
_CLIENTE_IMILE = "imile sas"
_COURIERS_EXCLUIDOS = {"LECTA", "PRINDEL"}


def _es_flujo_imile(df: pd.DataFrame) -> bool:
    return "Waybill No." in df.columns and "Scan time" in df.columns


def _transformar_imile(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_scan_dt"] = pd.to_datetime(df["Scan time"], errors="coerce", dayfirst=False)
    df["serial"] = df["Waybill No."].str.strip()
    df["fecha_recepcion"] = df["_scan_dt"].dt.date.astype(str)
    df["orden"] = "IM" + df["_scan_dt"].dt.strftime("%Y%m%d")
    df["planilla"] = df["orden"]
    df["nombre_cliente"] = "Imile SAS"
    df["tipo_servicio"]  = "paquete"
    df["ambito"]         = "bogota"
    df["_da_nombre"] = df["DA"].str.strip() if "DA" in df.columns else ""
    return df


async def _cargar_maestros(
    db: AsyncSession,
) -> tuple[dict, dict, dict, dict, dict]:
    """Devuelve (clientes_by_name, precios_cli, precios_men, personal_by_code, personal_by_name)."""
    rows_c = (await db.execute(select(Cliente.id, Cliente.nombre_empresa))).all()
    clientes_by_name = {r.nombre_empresa.strip().lower(): r.id for r in rows_c}

    rows_m = (await db.execute(select(MapeoCliente.nombre_csv, MapeoCliente.cliente_id))).all()
    for r in rows_m:
        alias = r.nombre_csv.strip().lower()
        if alias not in clientes_by_name and r.cliente_id:
            clientes_by_name[alias] = r.cliente_id

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
            select(Personal.id, Personal.codigo, Personal.nombre_completo, Personal.tipo_personal).where(
                Personal.activo == True  # noqa: E712
            )
        )
    ).all()
    personal_by_code = {
        r.codigo.strip().upper(): {
            'id':            r.id,
            'tipo_personal': r.tipo_personal or 'mensajero',
        }
        for r in rows_per if r.codigo
    }
    personal_by_name = {
        r.nombre_completo.strip().lower(): r.id for r in rows_per if r.nombre_completo
    }

    return clientes_by_name, precios_cli, precios_men, personal_by_code, personal_by_name


def _parse_date(val: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            from datetime import datetime as dt
            return dt.strptime(val.strip(), fmt).date()
        except ValueError:
            continue
    return None


_SERIAL_UPSERT = text("""
    INSERT INTO seriales_gestion
        (serial, orden, planilla, f_emi, f_esc, cod_men, mensajero_id,
         cliente_id, tipo_gestion, tipo_envio, ambito,
         precio_cliente, precio_mensajero, estado, origen)
    VALUES
        (:serial, :orden, :planilla, :fecha, :fecha, :cod_men, :mensajero_id,
         :cliente_id, :tipo_gestion, :tipo_envio, :ambito,
         :precio_cli, :precio_men, :db_estado, 'manual')
    ON CONFLICT (serial) DO UPDATE SET
        orden            = EXCLUDED.orden,
        planilla         = EXCLUDED.planilla,
        f_esc            = EXCLUDED.f_esc,
        cod_men          = EXCLUDED.cod_men,
        mensajero_id     = EXCLUDED.mensajero_id,
        tipo_gestion     = EXCLUDED.tipo_gestion,
        estado           = EXCLUDED.estado,
        precio_cliente   = EXCLUDED.precio_cliente,
        precio_mensajero = EXCLUDED.precio_mensajero,
        origen           = EXCLUDED.origen
    WHERE seriales_gestion.estado = 'pendiente'
""")

_SERIAL_EXISTS = (
    text("SELECT serial, estado FROM seriales_gestion WHERE serial = ANY(:serials)")
    .bindparams(bindparam("serials", type_=ARRAY(String)))
)

_ORDEN_EXISTS = (
    text("SELECT numero_orden, id FROM ordenes WHERE numero_orden = ANY(:nums)")
    .bindparams(bindparam("nums", type_=ARRAY(String)))
)


async def procesar_csv(
    contenido: bytes,
    db: AsyncSession,
    filename: str = "",
) -> CargaMasivaResult:
    # ── Leer archivo (CSV o XLSX) ─────────────────────────────────────────────
    try:
        if filename.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(contenido), dtype=str).dropna(how="all")
        else:
            df = pd.read_csv(io.BytesIO(contenido), dtype=str, low_memory=False).dropna(how="all")
    except Exception as e:
        return CargaMasivaResult(
            total_filas=0, filas_ignoradas=0, seriales_nuevos=0, seriales_actualizados=0,
            ordenes_nuevas=0, ordenes_actualizadas=0, errores=[f"Error leyendo archivo: {e}"]
        )

    # ── Excluir couriers no permitidos (Lecta/Prindel) ───────────────────────
    errores: list[str] = []
    for col_name in df.columns:
        if col_name.strip().lower() in ("courrier", "courier"):
            mask = df[col_name].str.strip().str.upper().isin(_COURIERS_EXCLUIDOS)
            n_excluidos = int(mask.sum())
            if n_excluidos:
                errores.append(f"{n_excluidos} filas excluidas: courier no permitido (Lecta/Prindel)")
                df = df[~mask].copy()
            break

    # ── Detectar flujo y normalizar columnas ──────────────────────────────────
    es_imile = _es_flujo_imile(df)
    if es_imile:
        df = _transformar_imile(df)
    else:
        if "fecha_recepcion" not in df.columns and "f_emi" in df.columns:
            df = df.rename(columns={"f_emi": "fecha_recepcion"})
        if "nombre_cliente" not in df.columns and "no_entidad" in df.columns:
            df = df.rename(columns={"no_entidad": "nombre_cliente"})
        if "tipo_servicio" not in df.columns:
            df["tipo_servicio"] = "sobre"
        if "ambito" not in df.columns:
            if "colum_ciudad" in df.columns:
                df["ambito"] = df["colum_ciudad"].str.strip().str.lower().apply(
                    lambda v: "bogota" if v == "local" else "nacional"
                )
            elif "ciudad1" in df.columns:
                df["ambito"] = df["ciudad1"].str.strip().str.lower().apply(
                    lambda v: "bogota" if "bog" in str(v) else "nacional"
                )
            else:
                df["ambito"] = "nacional"

    # ── Validar columnas mínimas ──────────────────────────────────────────────
    cols = set(df.columns)
    faltantes = {"serial", "orden", "fecha_recepcion", "nombre_cliente"} - cols
    if faltantes:
        return CargaMasivaResult(
            total_filas=len(df), filas_ignoradas=0, seriales_nuevos=0, seriales_actualizados=0,
            ordenes_nuevas=0, ordenes_actualizadas=0,
            errores=[f"Columnas faltantes: {', '.join(sorted(faltantes))}"],
        )

    # ── Normalizar valores internos ───────────────────────────────────────────
    df["_orden"]         = df["orden"].str.strip().str.replace(r"\.0$", "", regex=True)
    df["_tipo_servicio"] = df["tipo_servicio"].str.lower().str.strip()
    df["_es_local"]      = df["ambito"].str.lower().str.strip().str.contains("bog", na=False)
    df["_planilla_col"]  = df["planilla"].str.strip() if "planilla" in df.columns else ""
    df["_lot_esc_col"]   = df["lot_esc"].str.strip()  if "lot_esc"  in df.columns else ""
    df["_cod_men"]       = df["cod_men"].str.strip().str.upper() if "cod_men" in df.columns else ""

    _PENDIENTE = {"0", "lleva mensajero", "lleva ciudad", "pendiente"}

    def _mapear_estado(v: str) -> tuple[str, str]:
        v = (v if isinstance(v, str) else "").strip().lower()
        if v in _PENDIENTE or v in {"entrega", "entregado"}:
            return ("pendiente", "Entrega")
        return ("pendiente", "Devolucion")

    if es_imile:
        df["_db_estado"]    = "pendiente"
        df["_tipo_gestion"] = "Entrega"
    elif "estado" in df.columns:
        mapped = df["estado"].apply(_mapear_estado)
        df["_db_estado"]    = mapped.apply(lambda t: t[0])
        df["_tipo_gestion"] = mapped.apply(lambda t: t[1])
    else:
        df["_db_estado"]    = "pendiente"
        df["_tipo_gestion"] = "Entrega"

    # ── Filtro de fecha de corte ──────────────────────────────────────────────
    df["_fecha_parsed"] = df["fecha_recepcion"].apply(lambda x: _parse_date(str(x).strip()))
    total_filas = len(df)
    df = df[df["_fecha_parsed"].apply(lambda d: d is not None and d >= DATE_CORTE)].copy()
    filas_ignoradas = total_filas - len(df)

    clientes_by_name, precios_cli, precios_men, personal_by_code, personal_by_name = (
        await _cargar_maestros(db)
    )

    # ── Resolver DA → cod_men para filas iMile ────────────────────────────────
    if es_imile and "_da_nombre" in df.columns:
        def _resolver_da(nombre: str) -> str:
            nombre = (nombre or "").strip()
            if not nombre:
                return ""
            pid = personal_by_name.get(nombre.lower())
            if pid:
                for cod, info in personal_by_code.items():
                    if info['id'] == pid:
                        return cod
            return ""  # DA no encontrado → sin código asignado

        df["_cod_men"] = df["_da_nombre"].apply(_resolver_da)

    # ── Paso 1: construir params en Python (sin DB) ───────────────────────────
    all_serial_params: list[dict] = []

    for i, fila in df.iterrows():
        cliente_nom = str(fila["nombre_cliente"]).strip()
        id_cliente = clientes_by_name.get(cliente_nom.lower())
        if not id_cliente:
            errores.append(f"Fila {int(i)+2}: cliente '{cliente_nom}' no encontrado")  # type: ignore[arg-type]
            continue

        serial           = str(fila["serial"]).strip()
        num_orden        = str(fila["_orden"])
        fecha_parsed: date = fila["_fecha_parsed"]
        tipo_ser         = str(fila["_tipo_servicio"])
        ambito_val       = "bogota" if fila["_es_local"] else "nacional"
        cod_men_val      = (str(fila["_cod_men"]) if fila["_cod_men"] else "").zfill(4)[:4]
        tipo_gestion_val = str(fila["_tipo_gestion"])
        db_estado_val    = str(fila["_db_estado"])

        precio_cli   = precios_cli.get((id_cliente, tipo_ser, ambito_val), 0.0)
        precio_men   = precios_men.get((id_cliente, tipo_ser, ambito_val), 0.0)
        men_info     = personal_by_code.get(cod_men_val) if cod_men_val else None
        mensajero_id = men_info['id'] if men_info else None
        tipo_men     = men_info['tipo_personal'] if men_info else 'mensajero'
        if tipo_men == 'courier_externo':
            planilla_val = str(fila["_planilla_col"]) if fila["_planilla_col"] else ""
        else:
            planilla_val = (str(fila["_lot_esc_col"]) if fila["_lot_esc_col"] else "") or \
                           (str(fila["_planilla_col"]) if fila["_planilla_col"] else "")

        all_serial_params.append({
            "serial": serial, "orden": num_orden, "planilla": planilla_val,
            "fecha": fecha_parsed, "cod_men": cod_men_val, "mensajero_id": mensajero_id,
            "cliente_id": id_cliente, "tipo_gestion": tipo_gestion_val,
            "tipo_envio": tipo_ser, "ambito": ambito_val,
            "precio_cli": precio_cli, "precio_men": precio_men,
            "db_estado": db_estado_val,
        })

    # ── Paso 1b: resolver nuevos vs actualizados (1 query) ────────────────────
    sg_nuevos = 0
    sg_actualizados = 0

    if all_serial_params:
        incoming_serials = [p["serial"] for p in all_serial_params]
        rows = (await db.execute(_SERIAL_EXISTS, {"serials": incoming_serials})).fetchall()
        existing_map = {r[0]: r[1] for r in rows}  # serial → estado actual

        params_to_process: list[dict] = []
        for p in all_serial_params:
            s = p["serial"]
            if s not in existing_map:
                sg_nuevos += 1
                params_to_process.append(p)
            elif existing_map[s] == "pendiente":
                sg_actualizados += 1
                params_to_process.append(p)
            # estado != pendiente → no-op (no se inserta ni actualiza)

        # ── Paso 1c: batch upsert seriales (1 round-trip) ─────────────────────
        if params_to_process:
            try:
                await db.execute(text("SAVEPOINT sp_batch_serial"))
                await db.execute(_SERIAL_UPSERT, params_to_process)
                await db.execute(text("RELEASE SAVEPOINT sp_batch_serial"))
            except Exception as e:
                await db.execute(text("ROLLBACK TO SAVEPOINT sp_batch_serial"))
                logger.error("Error en batch seriales: %s", e)
                errores.append(f"Error en batch seriales: {e}")

    # ── Paso 2: ordenes (agrupar por número de orden) ─────────────────────────
    resumen = (
        df.groupby(["_orden", "fecha_recepcion", "nombre_cliente", "_tipo_servicio"])
        .agg(
            cant_local=("_es_local", "sum"),
            cant_nac=("_es_local", lambda x: (~x.astype(bool)).sum()),
        )
        .reset_index()
    )

    ordenes_nuevas = 0
    ordenes_actualizadas = 0

    orden_rows: list[dict] = []
    for _, grp in resumen.iterrows():
        cliente_nom = str(grp["nombre_cliente"]).strip()
        id_cliente = clientes_by_name.get(cliente_nom.lower())
        if not id_cliente:
            continue
        num_orden    = str(grp["_orden"])
        fecha_parsed = _parse_date(str(grp["fecha_recepcion"]).strip())
        if not fecha_parsed:
            continue
        tipo_ser = str(grp["_tipo_servicio"])
        c_local  = int(grp["cant_local"])
        c_nac    = int(grp["cant_nac"])
        c_total  = c_local + c_nac
        p_local  = precios_cli.get((id_cliente, tipo_ser, "bogota"),   0.0)
        p_nac    = precios_cli.get((id_cliente, tipo_ser, "nacional"), 0.0)
        v_total  = (c_local * p_local) + (c_nac * p_nac)
        orden_rows.append({
            "num": num_orden, "cli": id_cliente, "fecha": fecha_parsed,
            "tipo": tipo_ser, "total": c_total, "valor": v_total,
        })

    if orden_rows:
        # 1 query para saber cuáles ya existen
        nums = [r["num"] for r in orden_rows]
        rows = (await db.execute(_ORDEN_EXISTS, {"nums": nums})).fetchall()
        existing_ordenes = {r[0]: r[1] for r in rows}

        new_orden_params = [r for r in orden_rows if r["num"] not in existing_ordenes]
        upd_orden_params = [
            {"total": r["total"], "valor": r["valor"], "id": existing_ordenes[r["num"]]}
            for r in orden_rows if r["num"] in existing_ordenes
        ]

        if new_orden_params:
            try:
                await db.execute(
                    text("""
                        INSERT INTO ordenes
                            (numero_orden, cliente_id, fecha_recepcion, tipo_servicio,
                             cantidad_total, cantidad_recibido, valor_total, estado)
                        VALUES (:num, :cli, :fecha, :tipo, :total, :total, :valor, 'activa')
                    """),
                    new_orden_params,
                )
                ordenes_nuevas = len(new_orden_params)
            except Exception as e:
                errores.append(f"Error en batch ordenes nuevas: {e}")

        if upd_orden_params:
            try:
                await db.execute(
                    text("""
                        UPDATE ordenes
                        SET cantidad_total    = :total,
                            cantidad_recibido = :total,
                            valor_total       = :valor
                        WHERE id = :id
                    """),
                    upd_orden_params,
                )
                ordenes_actualizadas = len(upd_orden_params)
            except Exception as e:
                errores.append(f"Error en batch ordenes actualizadas: {e}")

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
