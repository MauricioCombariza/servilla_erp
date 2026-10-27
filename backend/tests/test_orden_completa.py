import io
import random

import pandas as pd
import pytest

from app.services.generar_dat_service import ANCHO_REGISTRO, ANCHO_TERCEROS
from app.services.orden_completa_service import generar_dats_orden_completa

INFORMES = {"centralizado": "CON", "terceros": "CLP"}


def _fila(serial, estado, oficina="000383", f_emi="2026-10-06", courrier="F&S", orden="123904") -> dict:
    # Mismas columnas (y otras que sobran) que el export de la orden, p. ej. 123904.xlsx
    return {
        "no_entidad": "BANCO CAJA SOCIAL", "orden": orden, "identdes": "0000000000001682",
        "oficina": oficina, "nombred": "JOSE ALBEIRO GOMEZ", "dirdes1": "CL 20 17 46", "barrd1": None,
        "ciudad1": "ARAUCA", "dpto1": "ARAUCA ARAUCA", "serial": serial, "f_emi": f_emi,
        "motivo": "Lleva Ciudad", "dir_pred": "CL 20 17 46", "courrier": courrier, "estado": estado,
    }


def _excel(filas: list[dict], otra_hoja: bool = True) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as w:
        pd.DataFrame(filas).to_excel(w, sheet_name="Hoja1", index=False)
        if otra_hoja:
            pd.DataFrame([{"serial": "1", "motivo_final": "Entrega"}]).to_excel(w, sheet_name="Hoja2", index=False)
    return buffer.getvalue()


def _generar(filas, **kw):
    return generar_dats_orden_completa("123904.xlsx", _excel(filas, **kw), "20261027", INFORMES, random.Random(1))


def _registros(dat) -> list[str]:
    return dat.contenido.decode("latin-1").splitlines()[1:-1]


def test_genera_centralizado_y_terceros_desde_la_orden():
    r = _generar([
        _fila(1673582022, "Entrega", oficina="000384"),
        _fila("1673582015", "Direccion Errad", oficina="000001"),  # truncado como en histo
        _fila("1673582039", "Destinatario Descono"),
    ])

    assert (r.orden, r.seriales, r.por_revisar) == ("123904", 3, [])
    centralizado, terceros = r.dats
    assert (centralizado.nombre, terceros.nombre) == ("BCS_CON_EXT_02_20261027.dat", "BCS_CLP_EXT_02_20261027.dat")
    assert (centralizado.registros, terceros.registros) == (3, 3)
    assert {len(l) for l in _registros(centralizado)} == {ANCHO_REGISTRO}
    assert {len(l) for l in _registros(terceros)} == {ANCHO_TERCEROS}

    # Ordenado por oficina; gestión = Estado + causal + F_recepcio (f_emi) + guía (serial)
    t = _registros(terceros)
    assert t[0].startswith("0000000001DEV0520261006000001673582015")
    assert t[1].startswith("0000000383DEV0120261006000001673582039")
    assert t[2].startswith("0000000384ENT0020261006000001673582022")
    f_gestion = int(t[0][-8:])
    assert 20261008 <= f_gestion <= 20261012  # f_emi + 2..6 días

    c = _registros(centralizado)[0]
    assert c.startswith("NI" + "0" * 16 + "0000000000001682" + "000001JOSE ALBEIRO GOMEZ")
    assert c.endswith("NOC1F&S" + " " * 32 + "123904")


def test_estado_no_reconocido_o_sin_f_emi_queda_por_revisar():
    r = _generar([
        _fila("1", "Entrega"),
        _fila("2", "Lleva Ciudad"),
        _fila("3", "Entrega", f_emi=". ."),
    ])
    assert [d.registros for d in r.dats] == [1, 1]
    assert r.por_revisar == [
        {"serial": "2", "courrier": "F&S", "motivo": "Lleva Ciudad", "falta": "Causal_Dev"},
        {"serial": "3", "courrier": "F&S", "motivo": "Entrega", "falta": "F_recepcio"},
    ]


def test_seriales_repetidos_se_reportan_y_queda_el_ultimo():
    r = _generar([_fila("1", "Rehusado"), _fila("1", "Entrega")])
    assert (r.seriales, r.duplicados) == (1, ["1"])
    assert _registros(r.dats[1])[0][10:13] == "ENT"


def test_varias_ordenes_en_el_archivo_es_error():
    with pytest.raises(ValueError, match="varias órdenes"):
        _generar([_fila("1", "Entrega"), _fila("2", "Entrega", orden="123905")])


def test_archivo_sin_las_columnas_de_la_orden_es_error():
    with pytest.raises(ValueError, match="faltan .*estado"):
        _generar([{k: v for k, v in _fila("1", "Entrega").items() if k != "estado"}], otra_hoja=False)
