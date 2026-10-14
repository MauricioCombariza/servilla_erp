"""Tests de estandarización + dirección numérica (dir_num) y de /api/direcciones/dirnum."""
import io

import pandas as pd
import pytest

from app.schemas.direcciones import FilaDirNum
from app.services.dirnum_service import (
    estandarizar_direccion,
    generar_direccion_numerica,
    generar_excel_dirnum,
    procesar_excel_dirnum,
)


@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


def _xlsx(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    return buffer.getvalue()


# ── Casos de datos_prueba de dashboard/dirnum/estandarizar_direcciones_v3.py ──

@pytest.mark.parametrize("raw,ajustada,dir_num", [
    ("CL 21 33 40", "CL 21 33 40", "110211003033100040"),
    ("CR 19 57 60 BL 5 AP 302", "CR 19 57 60", "130191001057100060"),
    ("CL 13 9 36 AP 202 ED CRN", "CL 13 9 36", "110131003009100036"),
    ("CL 15 13 73", "CL 15 13 73", "110151001013100073"),
    ("CR 41F 20D 52", "CR 41F 20D 52", "130412741020216052"),
    ("DG 142F 34 19", "DG 142F 34 19", "111422741034100019"),
    ("DG 43 34 20 AP 232 TO 4 CURASAO EST", "DG 43 34 20 ESTE", "410431003034100020"),
    ("CL 54A 50 92 AP 201", "CL 54A 50 92", "110541293050100092"),
    ("CL 37 45 200 AP 1521 TO 6 CONJ LA VIDA ES B", "CL 37 45 200", "110371003045100200"),
    ("CR 69D 1 51 TRR 3 AP 924 TORRES DE SAN ISID SUR", "CR 69D 1 51 SUR", "230692163001100051"),
    ("CR 69D 1 60 SUR", "CR 69D 1 60 SUR", "230692161001100060"),
    ("CR 51Dbis 42B 49 SUR", "CR 51DBIS 42B 49 SUR", "230512173042158049"),
    ("CR 68CbisA 38C 42 SUR", "CR 68CBISA 38C 42 SUR", "230681891038187042"),
])
def test_estandarizar_y_dir_num(raw, ajustada, dir_num):
    assert estandarizar_direccion(raw) == ajustada
    assert generar_direccion_numerica(ajustada) == dir_num


@pytest.mark.parametrize("raw,esperado", [
    ("CL 102 AA 89 25 MZ 110 CA 14", "CL 102A 89 25"),
    ("calle 95 # 49-22 clinica del pie y spa", "CL 95 49 22"),
    ("Calle 63f #28A-11 Panaderia mil delicias", "CL 63F 28A 11"),
    ("KR 21 A 83 21 CASA,Bogota, D.C.~~~Barrios Unidos~~~~~~KR 21 A 83 21 CASA", "CR 21A 83 21"),
    ("transversal 14B Nu 42-43", "TR 14B 42 43"),
    ("CL 36B 73F 15 SUR ESTE", "CL 36B 73F 15 SUR ESTE"),
])
def test_estandarizar_direccion(raw, esperado):
    assert estandarizar_direccion(raw) == esperado


@pytest.mark.parametrize("raw", ["", "   ", None, "SIN DIRECCION"])
def test_sin_direccion_valida_no_genera_dir_num(raw):
    ajustada = estandarizar_direccion(raw)
    assert ajustada is None
    assert generar_direccion_numerica(ajustada) is None


# ── Excel ─────────────────────────────────────────────────────────────────────

def test_procesar_excel_encabezados_flexibles():
    df = pd.DataFrame({
        " Serial ": ["0001", "0002", "0003"],
        "DIRECCION": ["CL 21 33 40", "", "texto sin via"],
        "otra": ["x", "y", "z"],
    })
    r = procesar_excel_dirnum(_xlsx(df))
    assert r.total_filas == 3
    assert r.sin_dir_num == 2
    assert r.filas[0].serial == "0001"  # dtype=str: no pierde ceros a la izquierda
    assert r.filas[0].direccion_ajustada == "CL 21 33 40"
    assert r.filas[0].dir_num == "110211003033100040"
    assert r.filas[1].direccion_ajustada == "" and r.filas[1].dir_num == ""


def test_procesar_excel_sin_columnas_requeridas():
    df = pd.DataFrame({"serial": ["1"], "dir": ["CL 21 33 40"]})
    with pytest.raises(ValueError, match="direccion"):
        procesar_excel_dirnum(_xlsx(df))


def test_generar_excel_recalcula_dir_num_editado():
    filas = [FilaDirNum(
        serial="0001", direccion="original", direccion_ajustada="cr 19 57 60", dir_num="viejo",
    )]
    df = pd.read_excel(io.BytesIO(generar_excel_dirnum(filas)), dtype=str)
    assert list(df.columns) == ["serial", "direccion", "direccion_ajustada", "dir_num"]
    assert df.loc[0, "serial"] == "0001"
    assert df.loc[0, "direccion_ajustada"] == "CR 19 57 60"
    assert df.loc[0, "dir_num"] == "130191001057100060"


# ── Endpoints ─────────────────────────────────────────────────────────────────

async def test_dirnum_endpoint(client, headers):
    contenido = _xlsx(pd.DataFrame({"serial": ["A1"], "direccion": ["CL 15 13 73"]}))
    r = await client.post(
        "/api/direcciones/dirnum",
        files={"file": ("base.xlsx", contenido)},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_filas"] == 1
    assert data["filas"][0]["dir_num"] == "110151001013100073"

    r = await client.post(
        "/api/direcciones/dirnum/descargar",
        json={"nombre_archivo": "base", "filas": data["filas"]},
        headers=headers,
    )
    assert r.status_code == 200
    assert 'filename="base_dirnum.xlsx"' in r.headers["content-disposition"]


async def test_dirnum_endpoint_extension_invalida(client, headers):
    r = await client.post(
        "/api/direcciones/dirnum",
        files={"file": ("base.csv", b"serial,direccion\n")},
        headers=headers,
    )
    assert r.status_code == 400
