"""Tests de la sectorización (dirección → código postal → localidad, y zona específica).

No usan la BD: el índice se arma desde el mismo CSV con el que la migración 031
carga `sectorizacion_limites`. Los resultados esperados salen de la lógica vieja de
dirnum (los 3 Excel), salvo los cambios aprobados el 2026-10-08:
  - códigos postales 110561 y 111981 → Usme (antes sin localidad)
  - zona 70_6 = CL 78–CL 80, CR 56A (placa impar)–CR 58; 70_5 se queda con CR 56A par
  - "CLLL" se lee como calle; "Carretera" y "Carera" como carrera
  - en las zonas, la paridad de placa solo cuenta en la vía principal
"""
import csv
from pathlib import Path

import pytest

from app.services.sectorizacion_service import (
    TIPO_CODIGO_POSTAL,
    TIPO_ZONA,
    LimiteSector,
    construir_indice,
    sectorizar,
)

SEMILLA = Path(__file__).resolve().parents[1] / "app" / "assets" / "sectorizacion_limites.csv"


def _leer_semilla() -> list[LimiteSector]:
    with SEMILLA.open(encoding="utf-8", newline="") as f:
        return [
            LimiteSector(**{**{k: (v or None) for k, v in fila.items()}, "orden": int(fila["orden"])})
            for fila in csv.DictReader(f)
        ]


@pytest.fixture(scope="module")
def limites():
    return _leer_semilla()


@pytest.fixture(scope="module")
def indice(limites):
    return construir_indice(limites)


# ── La tabla unificada ────────────────────────────────────────────────────────

def test_tabla_tiene_81_codigos_postales_y_33_zonas(limites):
    postales = [lim for lim in limites if lim.tipo == TIPO_CODIGO_POSTAL]
    zonas = [lim for lim in limites if lim.tipo == TIPO_ZONA]
    assert len(postales) == 81
    assert len(zonas) == 33


def test_todo_codigo_postal_tiene_localidad(limites):
    sin_localidad = [lim.nombre for lim in limites if lim.tipo == TIPO_CODIGO_POSTAL and not lim.localidad]
    assert sin_localidad == []


# ── Mismo resultado que dirnum (datos_prueba de estandarizar_direcciones_v3) ─

@pytest.mark.parametrize("direccion,dir_std,localidad,zona", [
    ("CL 102 AA 89 25 MZ 110 CA 14", "CL 102A 89 25", "Suba", None),
    ("CL 21 33 40", "CL 21 33 40", "Puente Aranda", None),
    ("CR 19 57 60 BL 5 AP 302", "CR 19 57 60", "Chapinero", None),
    ("CL 13 9 36 AP 202 ED CRN", "CL 13 9 36", "Candelaria", None),
    ("CL 15 13 73", "CL 15 13 73", "Santa Fe", None),
    ("CR 41F 20D 52", "CR 41F 20D 52", "Puente Aranda", None),
    ("DG 142F 34 19", "DG 142F 34 19", "Usaquen", None),
    ("DG 43 34 20 AP 232 TO 4 CURASAO EST", "DG 43 34 20 ESTE", "Teusaquillo", None),
    ("CL 54A 50 92 AP 201", "CL 54A 50 92", "Teusaquillo", None),
    ("CL 57A 66 BB 96 LC DOS ESQUINAS", "CL 57A 66B 96", "Teusaquillo", None),
    ("calle 95 # 49-22 clinica del pie y spa", "CL 95 49 22", "Barrios Unidos", "90_2"),
    ("Calle 63f #28A-11 Panaderia mil delicias", "CL 63F 28A 11", "Barrios Unidos", None),
    ("KR 21 A 83 21 CASA,Bogota, D.C.~~~Barrios Unidos~~~~~~KR 21 A 83 21 CASA",
     "CR 21A 83 21", "Chapinero", "80_1"),
    ("Cr 60 D # 90 04 apartamento 614,Bogota, D.C.~~~Barrios Unidos~~~~~~Cr 60 D # 90 04 apartamento 614",
     "CR 60D 90 04", "Barrios Unidos", "90_5"),
    ("cra67#67a-10 apto 203 Cundinamarca,Bogota, D.C.~~~Barrios Unidos~~~~~~cra67#67a-10 apto 203 Cundinamarca",
     "CR 67 67A 10", "Barrios Unidos", "60_12"),
    ("carrera 28 63 g 46 casa,Bogota, D.C.~~~Bogota~~~~~~carrera 28 63 g 46 casa",
     "CR 28 63G 46", "Barrios Unidos", "60_13"),
    ("CLL 72# 20-03 401,Bogota, D.C.~~~Bogota~~~~~~CLL 72# 20-03 401", "CL 72 20 03", "Chapinero", "60_6"),
    ("carrera 26 # 63b-13 casa,Bogota, D.C.~~~Barrios Unidos~~~~~~carrera 26 # 63b-13 casa",
     "CR 26 63B 13", "Barrios Unidos", "60_1"),
    ("Carrera 22#63c-68 Carrera 22#63c-68,Bogota, D.C.~~~Barrios Unidos~~~~~~Carrera 22#63c-68 Carrera 22#63c-68",
     "CR 22 63C 68", "Barrios Unidos", "60_2"),
    ("cra 27 a # 66-38 almacén kimautos,Bogota, D.C.~~~Barrios Unidos~~~~~~cra 27 a # 66-38 almacén kimautos",
     "CR 27A 66 38", "Barrios Unidos", "60_7"),
    ("Calle 71 # 21-21, Barrio Alcazarez Casa, Piso 2.,Bogota, D.C.~~~Barrios Unidos~~~~~~Calle 71 # 21-21, Barrio Alcazarez Casa, Piso 2.",
     "CL 71 21 21", "Barrios Unidos", "60_6"),
    ("calle 68 #28b17 tirnda de bicicletas local", "CL 68 28B 17", "Barrios Unidos", "60_7"),
    ("transversal 14B Nu 42-43", "TR 14B 42 43", "Chapinero", None),
    ("CR 79Fbis 36A 16 BL8 INT 2 AP 403 SUR", "CR 79FBIS 36A 16 SUR", "Kennedy", None),
    ("CL 39A 73A 26 PS 2 SUR", "CL 39A 73A 26 SUR", "Kennedy", None),
    ("CR 73Bbis 26 81B 9 AP 313 SUPERMANZANA 2 SU", "CR 73BBIS 26 81B", "Fontibon", None),
    ("CL 36B 73F 15 SUR ESTE", "CL 36B 73F 15 SUR ESTE", "Engativa", None),
    ("CR 78J 3539 BL 29 INT 04 AP 404 SUPER MANZ", "CR 78J 35 39", "Engativa", None),
    ("CR 51Dbis 42B 49 SUR", "CR 51DBIS 42B 49 SUR", "Puente Aranda", None),
    ("CR 68CbisA 38C 42 SUR", "CR 68CBISA 38C 42 SUR", "Kennedy", None),
])
def test_igual_que_dirnum(indice, direccion, dir_std, localidad, zona):
    r = sectorizar(direccion, indice)
    assert r.direccion_estandarizada == dir_std
    assert r.localidad == localidad
    assert r.zona == zona


# ── Cada una de las 33 zonas reconoce una dirección de su centro ──────────────

@pytest.mark.parametrize("zona,direccion", [
    ("60_1", "CL 63 # 30-11"), ("60_2", "CL 64 # 20-11"), ("60_3", "CL 65 # 15-11"),
    ("60_4", "CL 67 # 20-11"), ("60_5", "CL 70 # 15-11"), ("60_6", "CL 70 # 20-11"),
    ("60_7", "CL 67 # 27-11"), ("60_8", "CL 70 # 27-11"), ("60_9", "CL 70 # 49-11"),
    ("60_10", "CL 65 # 42-11"), ("60_11", "CL 65 # 57-11"), ("60_12", "CL 65 # 64-11"),
    ("60_13", "CL 64 # 27-11"), ("70_1", "CL 78 # 22-11"), ("70_2", "CL 74 # 22-11"),
    ("70_3", "CL 74 # 27-11"), ("70_4", "CL 78 # 27-11"), ("70_5", "CL 76 # 43-11"),
    ("70_6", "CL 79 # 57-11"), ("70_7", "CL 76 # 58-11"), ("70_8", "CL 76 # 62-11"),
    ("70_9", "CL 76 # 66-11"), ("80_1", "CL 86 # 22-11"), ("80_2", "CL 86 # 27-11"),
    ("80_3", "CL 85 # 40-11"), ("80_4", "CL 85 # 63-11"), ("90_1", "CL 92 # 47-11"),
    ("90_2", "CL 97 # 50-11"), ("90_3", "CL 98 # 59-11"), ("90_4", "CL 93 # 55-11"),
    ("90_5", "CL 93 # 62-11"), ("90_6", "CL 95 # 66-11"), ("10_1", "CL 98 # 70-11"),
])
def test_centro_de_cada_zona(indice, zona, direccion):
    assert sectorizar(direccion, indice).zona == zona


# ── Correcciones aprobadas el 2026-10-08 ──────────────────────────────────────

@pytest.mark.parametrize("direccion,zona", [
    ("CR 56A # 79-15", "70_6"),  # sobre CR 56A, placa impar
    ("CR 56A # 79-14", "70_5"),  # sobre CR 56A, placa par
    ("CL 79 # 57-11", "70_6"),
    ("CL 79 # 44-11", "70_5"),
])
def test_frontera_70_5_y_70_6_por_paridad(indice, direccion, zona):
    assert sectorizar(direccion, indice).zona == zona


@pytest.mark.parametrize("direccion", ["CL 120 SUR # 18-15", "CL 91 SUR # 25-15"])
def test_codigos_postales_de_usme(indice, direccion):
    r = sectorizar(direccion, indice)
    assert r.localidad == "Usme"
    assert r.zona is None


# ── Variantes de escritura aceptadas además de las de dirnum ─────────────────

@pytest.mark.parametrize("direccion,dir_std,zona", [
    ("CLLL 64 # 25:--::123****RINCON ZIURMA,Bogota, D.C.~~~Fontibon~~~~~~CLLL 64 # 25:--::123****RINCON ZIURMA",
     "CL 64 25 123", "60_13"),
    ("clll64 # 25-123", "CL 64 25 123", "60_13"),
])
def test_clll_se_lee_como_calle(indice, direccion, dir_std, zona):
    r = sectorizar(direccion, indice)
    assert r.direccion_estandarizada == dir_std
    assert r.localidad == "Barrios Unidos"
    assert r.zona == zona


@pytest.mark.parametrize("direccion,dir_std,zona", [
    ("Carretera 50b 64 43 Torre 1 apto 1002 camino del viento etapa 2", "CR 50B 64 43", "60_10"),
    ("Calle Carera 61 #75b-40 Panaderia flor camelia", "CR 61 75B 40", "70_8"),
])
def test_carretera_y_carera_se_leen_como_carrera(indice, direccion, dir_std, zona):
    r = sectorizar(direccion, indice)
    assert r.direccion_estandarizada == dir_std
    assert r.zona == zona


# ── Paridad solo en la vía principal; la vía que cruza va por cuadras ─────────

@pytest.mark.parametrize("direccion,zona", [
    # Carrera con cruce sobre el límite CL 66 (60_2 termina, 60_4 empieza): par e impar → 60_4
    ("CR 20 # 66-15", "60_4"),
    ("CR 20 # 66-14", "60_4"),
    # Sobre la CR 17 la placa sí decide el lado: impar → 60_2, par → 60_3; cruce CL 63 queda dentro
    ("CR 17 # 63-49", "60_2"),
    ("CR 17 # 63-48", "60_3"),
    # Calle sobre el límite CL 66: aquí la placa sí decide (según la tabla, impar → 60_2, par → 60_4)
    ("CL 66 # 20-15", "60_2"),
    ("CL 66 # 20-14", "60_4"),
    # Calle con cruce sobre el límite CR 17 (60_3 termina, 60_2 empieza): par e impar → 60_2
    ("CL 64 # 17-15", "60_2"),
    ("CL 64 # 17-14", "60_2"),
    # Cruce sobre el límite norte de la última zona: la cuadra siguiente queda fuera
    ("CR 45 # 100-21", None),
])
def test_paridad_solo_en_via_principal(indice, direccion, zona):
    assert sectorizar(direccion, indice).zona == zona


# ── Direcciones que no se pueden ubicar ───────────────────────────────────────

@pytest.mark.parametrize("direccion", ["", None, "XYZ sin direccion"])
def test_direccion_que_no_se_puede_ubicar(indice, direccion):
    r = sectorizar(direccion, indice)
    assert r.localidad is None
    assert r.zona is None
