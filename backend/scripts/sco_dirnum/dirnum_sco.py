"""
Punto 1 de devoluciones de arrastre.prg: ajuste de direccion + dir_num con la logica del ERP.

Corre EN el servidor WEB (Windows, Python 3.8, sin dependencias externas), junto a
actualizar_bases_web.py, y usa su mismo config.ini (seccion [ftp] y [correo]).

Ida y vuelta con el SCO (192.160.30.11):
  1. arrastre.prg deja /u/tmp/dn_<orden>.req con los seriales SIN digitos en dir_num:
     "serial","dirdes1","dir_ori"   (COPY TO ... DELIMITED de FoxPro)
  2. Este programa lo baja por FTP, calcula direccion ajustada + dir_num (dirnum_legacy.py)
  3. Sube dn_<orden>.tmp y lo renombra a dn_<orden>.ok (asi FoxPro nunca lee un archivo a medias)
     "serial","direccion_ajustada","dir_num"   (APPEND FROM ... DELIMITED de FoxPro)
  4. Borra el .req. arrastre.prg carga el .ok y sigue con las reglas de devolucion.

Uso:
  python dirnum_sco.py                    # loop continuo (tarea programada al iniciar el sistema)
  python dirnum_sco.py --once             # una sola revision de /u/tmp y termina
  python dirnum_sco.py --archivo x.req    # procesa un .req local y deja x.ok al lado (sin FTP)
"""
import argparse
import csv
import datetime as dt
import ftplib
import io
import logging
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dirnum_legacy import estandarizar_direccion, generar_direccion_numerica  # noqa: E402

log = logging.getLogger("dirnum_sco")

CARPETA_REMOTA = "/u/tmp"
PREFIJO = "dn_"
# El SCO es latin-1 / ISO-8859-1, igual que el .dat de BCS
CODIFICACION = "latin-1"


# ----------------------------------------------------------------------------
# Calculo (sin FTP: es lo que prueban los tests)
# ----------------------------------------------------------------------------
def ajustar(direccion):
    """(direccion_ajustada, dir_num) o (None, None) si no se pudo generar dir_num."""
    ajustada = estandarizar_direccion((direccion or "").strip())
    if not ajustada:
        return None, None
    dir_num = generar_direccion_numerica(ajustada)
    if not dir_num:
        return None, None
    return ajustada, dir_num


def leer_req(contenido):
    """Filas (serial, dirdes1, dir_ori) de un .req de FoxPro (COPY TO ... DELIMITED)."""
    texto = contenido.decode(CODIFICACION, "replace")
    filas = []
    for campos in csv.reader(io.StringIO(texto)):
        if not campos or not campos[0].strip():
            continue
        campos = [c.strip() for c in campos] + ["", ""]
        filas.append((campos[0], campos[1], campos[2]))
    return filas


def _sin_comillas(valor):
    # APPEND FROM ... DELIMITED de FoxPro no soporta comillas escapadas
    return valor.replace('"', "")


def procesar(contenido):
    """Recibe el .req y devuelve (contenido del .ok, filas recibidas, filas ajustadas).

    Primero intenta con dirdes1; si no sale dir_num, con dir_ori (la direccion original).
    Solo van al .ok los seriales a los que si se les pudo generar dir_num.
    """
    filas = leer_req(contenido)
    lineas = []
    for serial, dirdes1, dir_ori in filas:
        ajustada, dir_num = ajustar(dirdes1)
        if not dir_num and dir_ori and dir_ori != dirdes1:
            ajustada, dir_num = ajustar(dir_ori)
        if dir_num:
            lineas.append('"%s","%s","%s"' % (_sin_comillas(serial), _sin_comillas(ajustada), dir_num))
    # Fin de linea Unix: el .ok lo lee FoxPro en el SCO
    salida = "".join(linea + "\n" for linea in lineas).encode(CODIFICACION, "replace")
    return salida, len(filas), len(lineas)


# ----------------------------------------------------------------------------
# FTP
# ----------------------------------------------------------------------------
def conectar(cfg):
    f = cfg["ftp"]
    ftp = ftplib.FTP()
    ftp.connect(f["host"], f.getint("puerto", 21), f.getint("timeout", 60))
    ftp.login(f["usuario"], f["password"])
    ftp.set_pasv(f.getboolean("pasivo", True))
    ftp.cwd(CARPETA_REMOTA)
    ftp.voidcmd("TYPE I")  # binario: los finales de linea viajan tal cual
    return ftp


def pendientes(ftp):
    """Nombres dn_*.req de /u/tmp. Se usa LIST (el NLST del SCO no es confiable)."""
    lineas = []
    ftp.retrlines("LIST", lineas.append)
    nombres = [linea.split()[-1] for linea in lineas if linea.strip()]
    return sorted(n for n in nombres if n.startswith(PREFIJO) and n.endswith(".req"))


def atender(ftp, nombre_req, cfg):
    base = nombre_req[:-len(".req")]
    buffer = io.BytesIO()
    ftp.retrbinary("RETR " + nombre_req, buffer.write)
    try:
        salida, recibidas, ajustadas = procesar(buffer.getvalue())
    except Exception as e:  # nunca dejar a arrastre.prg esperando: se responde vacio
        log.exception("Error procesando %s", nombre_req)
        avisar(cfg, "dirnum_sco: error en %s" % nombre_req, str(e))
        salida, recibidas, ajustadas = b"", 0, 0
    ftp.storbinary("STOR " + base + ".tmp", io.BytesIO(salida))
    try:
        ftp.delete(base + ".ok")  # un .ok viejo de una corrida anterior de la misma orden
    except ftplib.error_perm:
        pass
    ftp.rename(base + ".tmp", base + ".ok")
    ftp.delete(nombre_req)
    log.info("%s: %d seriales sin dir_num, %d ajustados", nombre_req, recibidas, ajustadas)


def revisar(ftp, cfg):
    nombres = pendientes(ftp)
    for nombre in nombres:
        atender(ftp, nombre, cfg)
    return len(nombres)


# ----------------------------------------------------------------------------
# Config, log y correo (los de actualizar_bases_web.py si esta en la misma carpeta)
# ----------------------------------------------------------------------------
def cargar_config(ruta):
    import configparser
    cfg = configparser.ConfigParser(interpolation=None)
    if not cfg.read(ruta, encoding="utf-8"):
        raise SystemExit("No se encontro el archivo de configuracion: %s" % ruta)
    return cfg


def avisar(cfg, asunto, cuerpo):
    try:
        from actualizar_bases_web import enviar_correo
    except ImportError:
        return
    enviar_correo(cfg, asunto, cuerpo)


def configurar_log():
    carpeta = os.path.join(BASE_DIR, "logs")
    os.makedirs(carpeta, exist_ok=True)
    archivo = os.path.join(carpeta, "dirnum_" + dt.date.today().strftime("%Y-%m-%d") + ".log")
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    log.setLevel(logging.INFO)
    for h in (logging.FileHandler(archivo, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(BASE_DIR, "config.ini"))
    ap.add_argument("--once", action="store_true", help="revisa /u/tmp una vez y termina")
    ap.add_argument("--archivo", help="procesa un .req local (sin FTP) y deja el .ok al lado")
    ap.add_argument("--intervalo", type=int, default=5, help="segundos entre revisiones (default 5)")
    args = ap.parse_args(argv)
    configurar_log()

    if args.archivo:
        with open(args.archivo, "rb") as fh:
            salida, recibidas, ajustadas = procesar(fh.read())
        destino = os.path.splitext(args.archivo)[0] + ".ok"
        with open(destino, "wb") as fh:
            fh.write(salida)
        log.info("%s -> %s: %d seriales, %d ajustados", args.archivo, destino, recibidas, ajustadas)
        return 0

    cfg = cargar_config(args.config)
    log.info("Vigilando %s:%s cada %d s", cfg["ftp"]["host"], CARPETA_REMOTA, args.intervalo)
    ftp = None
    fallas = 0
    while True:
        try:
            if ftp is None:
                ftp = conectar(cfg)
            revisar(ftp, cfg)
            fallas = 0
        except (OSError, EOFError, ftplib.Error) as e:
            fallas += 1
            log.warning("FTP: %s (falla %d), se reconecta", e, fallas)
            if fallas == 12:  # ~1 minuto caido: un solo correo, no uno por intento
                avisar(cfg, "dirnum_sco: sin conexion al SCO", str(e))
            try:
                if ftp is not None:
                    ftp.close()
            finally:
                ftp = None
        if args.once:
            break
        time.sleep(args.intervalo)
    codigo = 1 if fallas else 0
    if ftp is not None:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
