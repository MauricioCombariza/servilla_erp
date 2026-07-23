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

El archivo se procesa **por chunks**: el dashboard diario puede traer cientos de miles
de filas y materializar el DataFrame completo agotaba la memoria del contenedor
(OOM kill de uvicorn). Con chunksize + usecols el pico de memoria es constante y no
depende del tamaño del archivo.
"""
from __future__ import annotations

import io
import logging
import unicodedata
from collections import Counter
from collections.abc import Iterator
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

# Filas por chunk de lectura y params por sentencia enviada a Postgres.
CHUNK_FILAS = 50_000
LOTE_UPSERT = 10_000
MAX_ERRORES = 50

# Únicas columnas que el servicio lee. El dashboard trae ~30 columnas y descartar
# las demás en el parser (usecols) reduce la memoria del chunk unas 2.5x.
_COLUMNAS_UTILES = frozenset({
    "serial", "orden", "fecha_recepcion", "f_emi",
    "nombre_cliente", "no_entidad", "tipo_servicio", "ambito",
    "colum_ciudad", "ciudad1", "estado", "planilla", "lot_esc", "cod_men",
    "courrier", "courier",
    "waybill no.", "scan time", "da",
})


def _es_columna_util(nombre: str) -> bool:
    return nombre.strip().lower() in _COLUMNAS_UTILES


def _normalizar_nombre(s: str) -> str:
    """minúsculas + sin tildes/diacríticos + espacios colapsados, para que
    'Pabón  Gomez' == 'Pabon Gomez' == 'PABÓN GOMEZ'."""
    s = unicodedata.normalize("NFKD", s.strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


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
            select(
                Personal.id,
                Personal.codigo,
                Personal.nombre_completo,
                Personal.tipo_personal,
                Personal.precio_local,
                Personal.precio_nacional,
            ).where(Personal.activo == True)  # noqa: E712
        )
    ).all()
    personal_by_code = {
        r.codigo.strip().upper(): {
            'id':             r.id,
            'tipo_personal':  r.tipo_personal or 'mensajero',
            'precio_local':   float(r.precio_local   or 0),
            'precio_nacional': float(r.precio_nacional or 0),
        }
        for r in rows_per if r.codigo
    }
    personal_by_name = {
        _normalizar_nombre(r.nombre_completo): r.id for r in rows_per if r.nombre_completo
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


def _parse_fechas(serie: pd.Series) -> pd.Series:
    """Serie de texto → datetime64 (NaT si no parsea).

    El formato ISO cubre prácticamente todo el volumen del dashboard, así que se
    vectoriza; solo los valores que no encajan caen al parser multi-formato.
    """
    s = serie.fillna("").astype(str).str.strip()
    fechas = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    resto = fechas.isna() & (s != "")
    if resto.any():
        fechas.loc[resto] = pd.to_datetime(s[resto].map(_parse_date), errors="coerce")
    return fechas


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
      AND seriales_gestion.editado_manualmente = FALSE
""")

_SERIAL_EXISTS = (
    text("SELECT serial, estado, editado_manualmente FROM seriales_gestion WHERE serial = ANY(:serials)")
    .bindparams(bindparam("serials", type_=ARRAY(String)))
)

_ORDEN_EXISTS = (
    text("SELECT numero_orden, id FROM ordenes WHERE numero_orden = ANY(:nums)")
    .bindparams(bindparam("nums", type_=ARRAY(String)))
)


def _iter_chunks(origen: bytes | str, filename: str) -> Iterator[pd.DataFrame]:
    """Itera el archivo en DataFrames de CHUNK_FILAS filas.

    `origen` puede ser el contenido en memoria (archivos chicos, tests) o la ruta
    del temporal que escribió el endpoint.
    """
    fuente: io.BytesIO | str = io.BytesIO(origen) if isinstance(origen, bytes) else origen

    if filename.endswith(".xlsx"):
        # pandas no soporta lectura por chunks en Excel; los .xlsx de este flujo
        # son manuales y pequeños.
        yield pd.read_excel(fuente, dtype=str)
        return

    with pd.read_csv(
        fuente, dtype=str, usecols=_es_columna_util, chunksize=CHUNK_FILAS
    ) as reader:
        yield from reader


def _preparar_columnas(df: pd.DataFrame, es_imile: bool) -> pd.DataFrame:
    """Lleva las columnas de origen a los nombres canónicos y deriva las ausentes."""
    if es_imile:
        return _transformar_imile(df)

    df = df.copy()
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
    return df


_PENDIENTE = {"0", "lleva mensajero", "lleva ciudad", "pendiente"}
_ESTADOS_ENTREGA = _PENDIENTE | {"entrega", "entregado"}

# Variantes de texto que un CSV puede traer para representar "sin dato": el NaN
# real de pandas (celda ausente) o el texto literal "na"/"n/a"/"nan"
# (case-insensitive). Un simple .fillna("") solo cubre el primer caso: si el CSV
# trae la celda con el texto literal "NaN"/"NA" ya escrito, pasa intacto y
# termina guardándose tal cual en columnas como planilla (bug histórico de
# planilla='nan' en seriales_gestion, ver commit d92993a — esta es la variante
# de ese mismo bug que ese fix no cubría).
_TEXTOS_VACIOS = {"na", "n/a", "nan"}


def _limpiar_texto(serie: pd.Series) -> pd.Series:
    """NaN de pandas y variantes de texto "vacío" (na/n.a/nan) → ""."""
    limpio = serie.fillna("").astype(str).str.strip()
    return limpio.mask(limpio.str.lower().isin(_TEXTOS_VACIOS), "")


def _derivar_valores(df: pd.DataFrame, es_imile: bool) -> pd.DataFrame:
    """Agrega las columnas de trabajo `k_*` que consume el armado de params.

    El prefijo es `k_` y no `_` a propósito: itertuples() renombra a posicional
    (`_3`, `_4`, …) cualquier columna cuyo nombre no sea un identificador válido
    de namedtuple, y los nombres con guion bajo inicial no lo son.
    """
    df["k_orden"]         = _limpiar_texto(
        df["orden"].str.strip().str.replace(r"\.0$", "", regex=True)
    )
    df["k_tipo_servicio"] = df["tipo_servicio"].str.lower().str.strip()
    df["k_es_local"]      = df["ambito"].str.lower().str.strip().str.contains("bog", na=False)
    df["k_planilla"]      = _limpiar_texto(df["planilla"]) if "planilla" in df.columns else ""
    df["k_lot_esc"]       = _limpiar_texto(df["lot_esc"])  if "lot_esc"  in df.columns else ""
    df["k_cod_men"]       = _limpiar_texto(df["cod_men"]).str.upper() if "cod_men" in df.columns else ""

    # Todas las filas entran como 'pendiente'; el estado del CSV solo decide si la
    # gestión es Entrega o Devolución.
    df["k_db_estado"] = "pendiente"
    if es_imile or "estado" not in df.columns:
        df["k_tipo_gestion"] = "Entrega"
    else:
        es_entrega = df["estado"].fillna("").str.strip().str.lower().isin(_ESTADOS_ENTREGA)
        df["k_tipo_gestion"] = "Devolucion"
        df.loc[es_entrega, "k_tipo_gestion"] = "Entrega"
    return df


def _resolver_cod_men_imile(
    df: pd.DataFrame,
    personal_by_code: dict,
    personal_by_name: dict,
    da_no_resueltos: Counter,
) -> pd.Series:
    """DA (nombre del mensajero iMile) → código de personal."""
    id_to_codigo = {info['id']: cod for cod, info in personal_by_code.items()}

    def _resolver(nombre: str) -> str:
        nombre = (nombre or "").strip()
        if not nombre:
            return ""
        norm = _normalizar_nombre(nombre)
        pid = personal_by_name.get(norm)
        if pid is None:
            # Imile a veces envía el DA sin el segundo apellido (ej. "Mariela
            # Pabon" vs "Mariela Pabón Gomez" en personal). Si el nombre del DA
            # es prefijo exacto de un único nombre en personal, se usa ese match.
            candidatos = {
                v for k, v in personal_by_name.items()
                if k == norm or k.startswith(norm + " ")
            }
            if len(candidatos) == 1:
                pid = next(iter(candidatos))
        cod = id_to_codigo.get(pid) if pid else None
        if cod:
            return cod
        da_no_resueltos[nombre] += 1
        return ""  # DA no encontrado → sin código asignado

    return df["_da_nombre"].apply(_resolver)


async def procesar_csv(
    origen: bytes | str,
    db: AsyncSession,
    filename: str = "",
) -> CargaMasivaResult:
    """Procesa el archivo por chunks. `origen` = contenido en bytes o ruta en disco."""
    errores: list[str] = []
    total_filas = 0
    filas_ignoradas = 0
    n_excluidos_courier = 0
    sg_nuevos = sg_actualizados = sg_bloqueados = 0
    clientes_no_encontrados: Counter[str] = Counter()
    da_no_resueltos: Counter[str] = Counter()
    # (numero_orden, fecha, nombre_cliente, tipo_servicio) → [cant_local, cant_nacional]
    ordenes_acum: dict[tuple[str, date, str, str], list[int]] = {}

    (
        clientes_by_name, precios_cli, precios_men, personal_by_code, personal_by_name
    ) = await _cargar_maestros(db)

    es_imile: bool | None = None
    chunks = _iter_chunks(origen, filename)

    while True:
        try:
            chunk = next(chunks)
        except StopIteration:
            break
        except Exception as e:
            errores.append(f"Error leyendo archivo: {e}")
            break

        chunk = chunk.dropna(how="all")

        # ── Excluir couriers no permitidos (Lecta/Prindel) ────────────────────
        for col_name in chunk.columns:
            if col_name.strip().lower() in ("courrier", "courier"):
                mask = chunk[col_name].str.strip().str.upper().isin(_COURIERS_EXCLUIDOS)
                n_excluidos = int(mask.sum())
                if n_excluidos:
                    n_excluidos_courier += n_excluidos
                    chunk = chunk[~mask].copy()
                break

        # ── Detectar flujo (las columnas son idénticas en todos los chunks) ───
        if es_imile is None:
            es_imile = _es_flujo_imile(chunk)
        df = _preparar_columnas(chunk, es_imile)

        # ── Validar columnas mínimas ──────────────────────────────────────────
        faltantes = {"serial", "orden", "fecha_recepcion", "nombre_cliente"} - set(df.columns)
        if faltantes:
            errores.append(f"Columnas faltantes: {', '.join(sorted(faltantes))}")
            break

        total_filas += len(df)
        df = _derivar_valores(df, es_imile)

        # ── Filtro de fecha de corte ──────────────────────────────────────────
        fechas = _parse_fechas(df["fecha_recepcion"])
        vigentes = fechas.notna() & (fechas >= pd.Timestamp(DATE_CORTE))
        filas_ignoradas += int((~vigentes).sum())
        df = df[vigentes].copy()
        if df.empty:
            continue
        df["k_fecha"] = fechas[vigentes].dt.date

        # ── Resolver DA → cod_men para filas iMile ────────────────────────────
        if es_imile and "_da_nombre" in df.columns:
            df["k_cod_men"] = _resolver_cod_men_imile(
                df, personal_by_code, personal_by_name, da_no_resueltos
            )

        # ── Params de seriales ────────────────────────────────────────────────
        params: list[dict] = []
        for fila in df.itertuples(index=False):
            cliente_nom = str(fila.nombre_cliente).strip()
            id_cliente = clientes_by_name.get(cliente_nom.lower())
            if not id_cliente:
                clientes_no_encontrados[cliente_nom] += 1
                continue

            ambito_val  = "bogota" if fila.k_es_local else "nacional"
            tipo_ser    = str(fila.k_tipo_servicio)
            cod_men_val = (str(fila.k_cod_men) if fila.k_cod_men else "").zfill(4)[:4]

            precio_cli   = precios_cli.get((id_cliente, tipo_ser, ambito_val), 0.0)
            precio_men   = precios_men.get((id_cliente, tipo_ser, ambito_val), 0.0)
            men_info     = personal_by_code.get(cod_men_val) if cod_men_val else None
            mensajero_id = men_info['id'] if men_info else None
            tipo_men     = men_info['tipo_personal'] if men_info else 'mensajero'
            if tipo_men == 'courier_externo' and men_info:
                precio_men = (
                    men_info['precio_local'] if ambito_val == 'bogota'
                    else men_info['precio_nacional']
                )
            if tipo_men == 'courier_externo':
                planilla_val = str(fila.k_planilla) if fila.k_planilla else ""
            else:
                planilla_val = (str(fila.k_lot_esc) if fila.k_lot_esc else "") or \
                               (str(fila.k_planilla) if fila.k_planilla else "")

            params.append({
                "serial": str(fila.serial).strip(), "orden": str(fila.k_orden),
                "planilla": planilla_val, "fecha": fila.k_fecha,
                "cod_men": cod_men_val, "mensajero_id": mensajero_id,
                "cliente_id": id_cliente, "tipo_gestion": str(fila.k_tipo_gestion),
                "tipo_envio": tipo_ser, "ambito": ambito_val,
                "precio_cli": precio_cli, "precio_men": precio_men,
                "db_estado": str(fila.k_db_estado),
            })

        # ── Upsert de seriales en lotes ───────────────────────────────────────
        for i in range(0, len(params), LOTE_UPSERT):
            lote = params[i:i + LOTE_UPSERT]
            rows = (
                await db.execute(_SERIAL_EXISTS, {"serials": [p["serial"] for p in lote]})
            ).fetchall()
            existing_map = {r[0]: (r[1], r[2]) for r in rows}  # serial → (estado, editado_manualmente)

            a_procesar: list[dict] = []
            for p in lote:
                estado_actual = existing_map.get(p["serial"])
                if estado_actual is None:
                    sg_nuevos += 1
                    a_procesar.append(p)
                elif estado_actual[0] == "pendiente" and not estado_actual[1]:
                    sg_actualizados += 1
                    a_procesar.append(p)
                elif estado_actual[1]:  # editado_manualmente=True → planilla fija, no se toca
                    sg_bloqueados += 1
                # else: estado != pendiente → no-op silencioso

            if a_procesar:
                try:
                    await db.execute(text("SAVEPOINT sp_batch_serial"))
                    await db.execute(_SERIAL_UPSERT, a_procesar)
                    await db.execute(text("RELEASE SAVEPOINT sp_batch_serial"))
                except Exception as e:
                    await db.execute(text("ROLLBACK TO SAVEPOINT sp_batch_serial"))
                    logger.error("Error en batch seriales: %s", e)
                    if len(errores) < MAX_ERRORES:
                        errores.append(f"Error en batch seriales: {e}")

        # ── Acumular el resumen de órdenes entre chunks ───────────────────────
        resumen = (
            df.groupby(["k_orden", "k_fecha", "nombre_cliente", "k_tipo_servicio"])
            .agg(
                cant_local=("k_es_local", "sum"),
                cant_nac=("k_es_local", lambda x: (~x.astype(bool)).sum()),
            )
            .reset_index()
        )
        for g in resumen.itertuples(index=False):
            key = (str(g.k_orden), g.k_fecha, str(g.nombre_cliente).strip(), str(g.k_tipo_servicio))
            acum = ordenes_acum.setdefault(key, [0, 0])
            acum[0] += int(g.cant_local)
            acum[1] += int(g.cant_nac)

        # Commit por chunk: el upsert es idempotente, así que un fallo a mitad de
        # archivo deja lo ya procesado consistente y reintentar es inocuo.
        await db.commit()

    # ── Ordenes: un solo upsert al final con el acumulado ─────────────────────
    ordenes_nuevas = 0
    ordenes_actualizadas = 0

    # El acumulado se agrupa por (orden, fecha, cliente, tipo) porque el precio
    # depende del tipo de servicio, pero ordenes.numero_orden es UNIQUE: un mismo
    # número que aparezca con varias fechas o tipos debe consolidarse en una fila,
    # o el INSERT del lote entero falla por duplicate key y no se crea ninguna orden.
    por_numero: dict[str, dict] = {}
    for (num_orden, fecha_parsed, cliente_nom, tipo_ser), (c_local, c_nac) in ordenes_acum.items():
        id_cliente = clientes_by_name.get(cliente_nom.lower())
        if not id_cliente:
            continue
        p_local = precios_cli.get((id_cliente, tipo_ser, "bogota"),   0.0)
        p_nac   = precios_cli.get((id_cliente, tipo_ser, "nacional"), 0.0)
        valor   = (c_local * p_local) + (c_nac * p_nac)

        fila = por_numero.get(num_orden)
        if fila is None:
            por_numero[num_orden] = {
                "num": num_orden, "cli": id_cliente, "fecha": fecha_parsed,
                "tipo": tipo_ser, "total": c_local + c_nac, "valor": valor,
            }
        else:
            fila["total"] += c_local + c_nac
            fila["valor"] += valor
            fila["fecha"] = min(fila["fecha"], fecha_parsed)

    orden_rows = list(por_numero.values())

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

    # ── Errores agregados ─────────────────────────────────────────────────────
    # Se reportan por causa y no por fila: un dashboard con cientos de miles de
    # filas sin cliente generaba una lista de igual tamaño antes de recortarla.
    if clientes_no_encontrados:
        errores.insert(0, _resumen_conteo(
            clientes_no_encontrados, "filas con cliente no encontrado"
        ))
    if da_no_resueltos:
        errores.append(_resumen_conteo(
            da_no_resueltos,
            "filas de Imile con DA no reconocido en personal "
            "(quedaron sin código asignado, revisar nombre exacto)",
        ))
    if n_excluidos_courier:
        errores.append(
            f"{n_excluidos_courier} filas excluidas: courier no permitido (Lecta/Prindel)"
        )

    logger.info(
        "Carga masiva: órdenes_nuevas=%d actualizadas=%d "
        "seriales_nuevos=%d actualizados=%d bloqueados=%d ignoradas=%d errores=%d",
        ordenes_nuevas, ordenes_actualizadas, sg_nuevos, sg_actualizados,
        sg_bloqueados, filas_ignoradas, len(errores),
    )
    return CargaMasivaResult(
        total_filas=total_filas,
        filas_ignoradas=filas_ignoradas,
        seriales_nuevos=sg_nuevos,
        seriales_actualizados=sg_actualizados,
        seriales_bloqueados=sg_bloqueados,
        ordenes_nuevas=ordenes_nuevas,
        ordenes_actualizadas=ordenes_actualizadas,
        errores=errores[:MAX_ERRORES],
    )


def _resumen_conteo(conteo: Counter[str], descripcion: str, tope: int = 15) -> str:
    detalle = ", ".join(f"'{k}' ({v})" for k, v in conteo.most_common(tope))
    if len(conteo) > tope:
        detalle += f", … (+{len(conteo) - tope} más)"
    return f"{sum(conteo.values())} {descripcion}: {detalle}"
