"""Paridad entre la copia sin pandas (scripts/sco_dirnum/dirnum_legacy.py, la que corre en el
servidor web para el punto 1 de arrastre.prg) y la lógica de dir_num del ERP.

Si este test falla, la lógica del ERP cambió: hay que regenerar dirnum_legacy.py."""
import sys
from pathlib import Path

import pytest

from app.services.dirnum_service import estandarizar_direccion, generar_direccion_numerica

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "sco_dirnum"))
import dirnum_legacy  # noqa: E402
import dirnum_sco  # noqa: E402

DIRECCIONES = [
    "CL 21 33 40",
    "CR 19 57 60 BL 5 AP 302",
    "CR 41F 20D 52",
    "DG 43 34 20 AP 232 TO 4 CURASAO EST",
    "CR 69D 1 51 TRR 3 AP 924 TORRES DE SAN ISID SUR",
    "CR 51Dbis 42B 49 SUR",
    "CR 68CbisA 38C 42 SUR",
    "CL 102 AA 89 25 MZ 110 CA 14",
    "calle 95 # 49-22 clinica del pie y spa",
    "KR 21 A 83 21 CASA,Bogota, D.C.~~~Barrios Unidos~~~~~~KR 21 A 83 21 CASA",
    "transversal 14B Nu 42-43",
    "CL 36B 73F 15 SUR ESTE",
    "CLLL 45 12 30",
    "Carera 7 # 45-10",
    "AVENIDA CALLE 26 # 68-35",
    "SIN DIRECCION",
    "",
    "   ",
    None,
]


@pytest.mark.parametrize("direccion", DIRECCIONES)
def test_legacy_igual_al_erp(direccion):
    ajustada_erp = estandarizar_direccion(direccion)
    ajustada_legacy = dirnum_legacy.estandarizar_direccion(direccion)
    assert ajustada_legacy == ajustada_erp
    assert dirnum_legacy.generar_direccion_numerica(ajustada_legacy) == generar_direccion_numerica(ajustada_erp)


# ── Formato del .req / .ok que intercambia con arrastre.prg ──────────────────

def test_procesar_req_de_foxpro():
    req = (
        b'"0012345","CALLE 95 # 49-22 CLINICA","CALLE 95 # 49-22 CLINICA"\r\n'
        b'"0012346","SIN DIRECCION","CR 19 57 60 BL 5"\r\n'   # dirdes1 sin vía: usa dir_ori
        b'"0012347","SIN DIRECCION","SIN DIRECCION"\r\n'      # no se puede: no va al .ok
    )
    salida, recibidas, ajustadas = dirnum_sco.procesar(req)
    assert (recibidas, ajustadas) == (3, 2)
    assert salida.decode("latin-1").splitlines() == [
        '"0012345","CL 95 49 22","110951003049100022"',
        '"0012346","CR 19 57 60","130191001057100060"',
    ]
    assert b"\r" not in salida  # FoxPro en el SCO lee fin de línea Unix


def test_procesar_req_latin1_y_comillas():
    req = '"A1","CALLE 10 # 5-20 Ñ"","x"\n'.encode("latin-1")
    salida, recibidas, _ = dirnum_sco.procesar(req)
    assert recibidas == 1
    texto = salida.decode("latin-1")
    assert texto.count('"') == 6  # sin comillas sueltas que rompan el APPEND DELIMITED


def test_procesar_req_vacio():
    assert dirnum_sco.procesar(b"") == (b"", 0, 0)
