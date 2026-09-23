import io

import pandas as pd
import pytest

from app.services.generar_dat_service import ANCHO_REGISTRO, generar_dat


def _excel(filas: list[dict]) -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(filas).to_excel(buffer, index=False)
    return buffer.getvalue()


def _histo(serial: str, oficina: str, courrier: str = "F&S") -> dict:
    return {
        "identdes": "0000000008878", "oficina": oficina, "nombred": "CENTRO DE ACOMPAÑAMIENTO",
        "dir_pred": "CL 20 20 43", "barrd1": None, "ciudad1": "ARAUCA", "dpto1": "ARAUCA ARAUCA",
        "serial": serial, "courrier": courrier, "orden": "123791",
    }


HISTO = [
    _histo("1672696003", "000300"),
    _histo("1672693019", "000001", "PRINDEL"),
    _histo("1672693026", "000002", "LECTA"),
]

EXCEL_1 = _excel([
    {"serial": 1672696003, "Estado": "ENT", "Causal_Dev": 0, "F_recepcio": 20260803,
     "guias": 150018205327, "F_GESTION": 20260806},
])
EXCEL_2 = _excel([
    {"serial": "1672693019", "Estado": "DEV", "Causal_Dev": "5", "F_recepcio": "20260806",
     "guias": "150018205324", "F_GESTION": None},
    {"serial": "9999999999", "Estado": "ENT", "Causal_Dev": "00", "F_recepcio": "20260806",
     "guias": "1", "F_GESTION": "20260820"},
])


def test_genera_registros_de_ancho_fijo():
    r = generar_dat("123791", "20260731", [("a.xlsx", EXCEL_1), ("b.xlsx", EXCEL_2)], HISTO)
    lineas = r.contenido_dat.decode("latin-1").split("\n")

    assert r.nombre_dat == "BCS_CON_EXT_02_20260731.dat"
    assert r.registros == 2
    assert lineas[0] == "*BCSEXTCON0220260731".ljust(312)
    assert lineas[-2] == "*00000002".ljust(312) + "NOC"
    assert lineas[-1] == ""

    registros = lineas[1:-2]
    assert all(len(l) == ANCHO_REGISTRO for l in registros)
    # Ordenados por oficina
    assert registros[0][34:40] == "000001"
    assert registros[1] == (
        "NI" + "8878".zfill(32) + "000300" + "CENTRO DE ACOMPAÑAMIENTO".ljust(65)
        + "CL 20 20 43".ljust(65) + " " * 35 + "0" * 11 + "ARAUCA".ljust(35)
        + "ARAUCA ARAUCA".ljust(35) + "20260731ENT0020260803000150018205327"
        + "20260806NOC1" + "F&S".ljust(35) + "123791"
    )
    # Causal rellenada y F_GESTION vacía queda en blanco
    assert registros[0][294:330] == "DEV0520260806000150018205324" + " " * 8


def test_reporta_errores_y_no_encontrados():
    r = generar_dat("123791", "20260731", [("a.xlsx", EXCEL_1), ("b.xlsx", EXCEL_2)], HISTO)
    assert r.errores == [{"serial": "1672693026", "courrier": "LECTA"}]
    assert r.no_encontrados_en_orden == ["9999999999"]


def test_detecta_duplicados_entre_excels():
    r = generar_dat("123791", "20260731", [("a.xlsx", EXCEL_1), ("c.xlsx", EXCEL_1)], HISTO)
    assert r.duplicados_en_excel == ["1672696003"]
    assert r.registros == 1


def test_columnas_faltantes():
    malo = _excel([{"serial": 1, "Estado": "ENT"}])
    with pytest.raises(ValueError, match="faltan columnas"):
        generar_dat("123791", "20260731", [("malo.xlsx", malo)], HISTO)


def test_orden_sin_registros():
    with pytest.raises(ValueError, match="no tiene registros"):
        generar_dat("1", "20260731", [("a.xlsx", EXCEL_1)], [])


def test_terceros_solo_bloque_de_gestion():
    r = generar_dat(
        "123791", "20260731", [("a.xlsx", EXCEL_1), ("b.xlsx", EXCEL_2)], HISTO, tipo="terceros"
    )
    lineas = r.contenido_dat.decode("latin-1").split("\n")

    assert r.nombre_dat == "BCS_CON_EXT_02_20260731.dat"
    assert lineas[0] == "*BCSEXTCON0220260731".ljust(312)
    assert lineas[-2] == "*00000002".ljust(312) + "NOC"
    assert lineas[1:-2] == [
        "20260731DEV0520260806000150018205324" + " " * 8,
        "20260731ENT0020260803000150018205327" + "20260806",
    ]


def test_tipo_invalido():
    with pytest.raises(ValueError, match="Tipo de informe"):
        generar_dat("123791", "20260731", [("a.xlsx", EXCEL_1)], HISTO, tipo="otro")
