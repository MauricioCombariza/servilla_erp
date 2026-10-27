"""Tests de la sectorización (dirección → código postal → localidad, y zona específica).

No usan la BD: el índice se arma desde el mismo CSV con el que la migración 031
carga `sectorizacion_limites`. Los resultados esperados salen de la lógica vieja de
dirnum (los 3 Excel), salvo los cambios aprobados el 2026-10-08:
  - códigos postales 110561 y 111981 → Usme (antes sin localidad)
  - zona 70_6 = CL 78–CL 80, CR 56A (placa impar)–CR 58; 70_5 se queda con CR 56A par
  - "CLLL" se lee como calle; "Carretera" y "Carera" como carrera
  - en las zonas, la paridad de placa solo cuenta en la vía principal
  - "SUR ESTE" (o SUR en el medio + ESTE al final) ubica la dirección al sur-oriente
Y los del 2026-10-21: "_" separa como "-"; Avenida La Esperanza (cualquier forma) = CR 60.
Y el del 2026-10-26: Autopista Norte = CR 20 entre CL 80 y 99, CR 45 entre CL 100 y 270.
"""
import csv
import importlib.util
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
_MIGRACION_043 = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions" / "043_zonas_nombres_nuevos.py"


def _nombres_nuevos() -> dict[int, tuple[str, str]]:
    """orden → (nombre anterior, nombre nuevo) de la migración 043."""
    spec = importlib.util.spec_from_file_location("migracion_043", _MIGRACION_043)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo.CAMBIOS


def _leer_semilla() -> list[LimiteSector]:
    """El CSV semilla (lo que carga la migración 031) con los nombres de zona de la 043 encima:
    lo mismo que queda en la base después de todas las migraciones."""
    cambios = _nombres_nuevos()
    with SEMILLA.open(encoding="utf-8", newline="") as f:
        limites = []
        for fila in csv.DictReader(f):
            orden = int(fila["orden"])
            if fila["tipo"] == TIPO_ZONA and orden in cambios:
                fila["nombre"] = cambios[orden][1]
            limites.append(LimiteSector(**{**{k: (v or None) for k, v in fila.items()}, "orden": orden}))
        return limites


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
    assert len(zonas) == 33  # filas de límites; desde la 043 una zona puede tener varias
    assert len({z.nombre for z in zonas}) == 28
    assert sorted({z.nombre for z in zonas if z.nombre.startswith("60_")}) == [f"60_{i}" for i in range(1, 9)]


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
    ("Calle 63f #28A-11 Panaderia mil delicias", "CL 63F 28A 11", "Barrios Unidos", "60_3"),  # antes None: CL 63F impar no caía en ninguna zona (2026-10-09)
    ("KR 21 A 83 21 CASA,Bogota, D.C.~~~Barrios Unidos~~~~~~KR 21 A 83 21 CASA",
     "CR 21A 83 21", "Chapinero", "80_1"),
    ("Cr 60 D # 90 04 apartamento 614,Bogota, D.C.~~~Barrios Unidos~~~~~~Cr 60 D # 90 04 apartamento 614",
     "CR 60D 90 04", "Barrios Unidos", "90_5"),
    ("cra67#67a-10 apto 203 Cundinamarca,Bogota, D.C.~~~Barrios Unidos~~~~~~cra67#67a-10 apto 203 Cundinamarca",
     "CR 67 67A 10", "Barrios Unidos", "60_8"),
    ("carrera 28 63 g 46 casa,Bogota, D.C.~~~Bogota~~~~~~carrera 28 63 g 46 casa",
     "CR 28 63G 46", "Barrios Unidos", "60_3"),
    ("CLL 72# 20-03 401,Bogota, D.C.~~~Bogota~~~~~~CLL 72# 20-03 401", "CL 72 20 03", "Chapinero", "60_2"),
    ("carrera 26 # 63b-13 casa,Bogota, D.C.~~~Barrios Unidos~~~~~~carrera 26 # 63b-13 casa",
     "CR 26 63B 13", "Barrios Unidos", "60_3"),
    ("Carrera 22#63c-68 Carrera 22#63c-68,Bogota, D.C.~~~Barrios Unidos~~~~~~Carrera 22#63c-68 Carrera 22#63c-68",
     "CR 22 63C 68", "Barrios Unidos", "60_1"),
    ("cra 27 a # 66-38 almacén kimautos,Bogota, D.C.~~~Barrios Unidos~~~~~~cra 27 a # 66-38 almacén kimautos",
     "CR 27A 66 38", "Barrios Unidos", "60_3"),
    ("Calle 71 # 21-21, Barrio Alcazarez Casa, Piso 2.,Bogota, D.C.~~~Barrios Unidos~~~~~~Calle 71 # 21-21, Barrio Alcazarez Casa, Piso 2.",
     "CL 71 21 21", "Barrios Unidos", "60_2"),
    ("calle 68 #28b17 tirnda de bicicletas local", "CL 68 28B 17", "Barrios Unidos", "60_3"),
    ("transversal 14B Nu 42-43", "TR 14B 42 43", "Chapinero", None),
    ("CR 79Fbis 36A 16 BL8 INT 2 AP 403 SUR", "CR 79FBIS 36A 16 SUR", "Kennedy", None),
    ("CL 39A 73A 26 PS 2 SUR", "CL 39A 73A 26 SUR", "Kennedy", None),
    ("CR 73Bbis 26 81B 9 AP 313 SUPERMANZANA 2 SU", "CR 73BBIS 26 81B", "Fontibon", None),
    # dirnum no daba localidad: Fontibón llegaba solo hasta CR 125/130 (cambio 2026-10-27)
    ("carrera 135 17 84 torre 1 1209", "CR 135 17 84", "Fontibon", None),
    ("CR 140 30 10", "CR 140 30 10", "Fontibon", None),
    # dirnum daba Engativa porque ignoraba el SUR de "SUR ESTE" (cambio 2026-10-08)
    ("CL 36B 73F 15 SUR ESTE", "CL 36B 73F 15 SUR ESTE", "Kennedy", None),
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
    ("60_3", "CL 63 # 27-12"), ("60_1", "CL 64 # 20-11"), ("60_1", "CL 65 # 15-11"),
    ("60_1", "CL 67 # 20-11"), ("60_2", "CL 70 # 15-11"), ("60_2", "CL 70 # 20-11"),
    ("60_3", "CL 67 # 27-11"), ("60_4", "CL 70 # 27-11"), ("60_7", "CL 70 # 49-11"),
    ("60_6", "CR 45 # 66-50"), ("60_5", "CR 45 # 63-50"), ("60_8", "CL 65 # 64-11"),
    ("60_3", "CL 64 # 27-11"), ("70_2", "CL 78 # 22-11"), ("70_1", "CL 74 # 22-11"),
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
     "CL 64 25 123", "60_3"),
    ("clll64 # 25-123", "CL 64 25 123", "60_3"),
])
def test_clll_se_lee_como_calle(indice, direccion, dir_std, zona):
    r = sectorizar(direccion, indice)
    assert r.direccion_estandarizada == dir_std
    assert r.localidad == "Barrios Unidos"
    assert r.zona == zona


@pytest.mark.parametrize("direccion,dir_std,zona", [
    ("Carretera 50b 64 43 Torre 1 apto 1002 camino del viento etapa 2", "CR 50B 64 43", "60_6"),
    ("Calle Carera 61 #75b-40 Panaderia flor camelia", "CR 61 75B 40", "70_8"),
])
def test_carretera_y_carera_se_leen_como_carrera(indice, direccion, dir_std, zona):
    r = sectorizar(direccion, indice)
    assert r.direccion_estandarizada == dir_std
    assert r.zona == zona



@pytest.mark.parametrize("direccion,dir_std", [
    ("calle 24_78_17", "CL 24 78 17"),
    ("Calle 24_78_17 apto 301", "CL 24 78 17"),
    ("Calle Calle 98b#68b_67 Casa", "CL 98B 68B 67"),
    ("Cra 22#86_28 casa rejas negras de 8_5pm L_V", "CR 22 86 28"),
])
def test_guion_bajo_separa_como_guion(indice, direccion, dir_std):
    assert sectorizar(direccion, indice).direccion_estandarizada == dir_std


@pytest.mark.parametrize("direccion,dir_std", [
    ("AV LA ESPERANZA # 72-15", "CR 60 72 15"),
    ("av la esperanza 68 50", "CR 60 68 50"),
    ("Avenida la Esperanza 75-20", "CR 60 75 20"),
    ("Av. La Esperanza No 68A-30", "CR 60 68A 30"),
    ("Av.La Esperanza #70-10", "CR 60 70 10"),
    ("AVDA LA ESPERANZA 70 10", "CR 60 70 10"),
    ("Avenida de la Esperanza 70 10", "CR 60 70 10"),
    ("avenida esperanza 70 10", "CR 60 70 10"),
    ("av laesperanza 70-10", "CR 60 70 10"),
])
def test_avenida_la_esperanza_es_la_carrera_60(indice, direccion, dir_std):
    assert sectorizar(direccion, indice).direccion_estandarizada == dir_std


@pytest.mark.parametrize("direccion,dir_std", [
    ("autopista norte # 93-85 restaurante", "CR 20 93 85"),  # direcciones reales de despachos
    ("Autopista norte #87-33 clínica Retornar Clínica Retornar", "CR 20 87 33"),
    ("AUTOPISTA NORTE 80 10", "CR 20 80 10"),
    ("Autopista Norte No. 99A-20", "CR 20 99A 20"),
    ("AUTOPISTA NORTE # 100-15", "CR 45 100 15"),
    ("Av. Autopista Norte # 127-45 Apto 302", "CR 45 127 45"),
    ("Autop Norte 147 20", "CR 45 147 20"),
    ("AUTONORTE #170-50", "CR 45 170 50"),
    ("aut norte 245 10", "CR 45 245 10"),
    ("Autopista Norte 270 05", "CR 45 270 05"),
])
def test_autopista_norte_es_carrera_20_o_45_segun_la_calle(indice, direccion, dir_std):
    assert sectorizar(direccion, indice).direccion_estandarizada == dir_std


@pytest.mark.parametrize("direccion", ["Autopista Norte # 79-10", "Autopista Norte # 271-10"])
def test_autopista_norte_fuera_de_los_tramos_no_se_traduce(indice, direccion):
    assert not (sectorizar(direccion, indice).direccion_estandarizada or "").startswith("CR")


def test_barrio_la_esperanza_no_cambia_la_via(indice):
    r = sectorizar("Carrera 15 # 63- 32 Apto 202 Barrio La Esperanza Edificio Modulor", indice)
    assert (r.direccion_estandarizada, r.zona) == ("CR 15 63 32", "60_1")

@pytest.mark.parametrize("direccion,dir_std", [
    ("CL 11 # 16-99 SUR ESTE", "CL 11 16 99 SUR ESTE"),
    ("CL 11 SUR # 16-99 ESTE", "CL 11 16 99 SUR ESTE"),  # SUR en el medio + ESTE al final
])
def test_sur_este_se_estandariza_completo(indice, direccion, dir_std):
    assert sectorizar(direccion, indice).direccion_estandarizada == dir_std


def test_sur_este_queda_al_sur_oriente():
    from app.services.sectorizacion_service import _coordenadas_dir
    cl, cr = _coordenadas_dir("CL 11 16 99 SUR ESTE")
    assert cl < 0 and cr < 0


# ── Paridad solo en la vía principal; la vía que cruza va por cuadras ─────────

@pytest.mark.parametrize("direccion,zona", [
    # Carrera con cruce sobre el límite CL 66 (60_2 termina, 60_4 empieza): par e impar → 60_4
    ("CR 20 # 66-15", "60_1"),
    ("CR 20 # 66-14", "60_1"),
    # Sobre la CR 17 la placa sí decide el lado: impar → 60_2, par → 60_3; cruce CL 63 queda dentro
    ("CR 17 # 63-49", "60_1"),
    ("CR 17 # 63-48", "60_1"),
    # Calle sobre el límite CL 66: aquí la placa sí decide (según la tabla, impar → 60_2, par → 60_4)
    ("CL 66 # 20-15", "60_1"),
    ("CL 66 # 20-14", "60_1"),
    # Calle con cruce sobre el límite CR 17 (60_3 termina, 60_2 empieza): par e impar → 60_2
    ("CL 64 # 17-15", "60_1"),
    ("CL 64 # 17-14", "60_1"),
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


# ── Ajuste de zonas 60_1, 60_10 y 60_11 (2026-10-08) ──────────────────────────

@pytest.mark.parametrize("direccion,zona", [
    ("CR 45 # 63-50", "60_5"),  # cuadra CL 63–64: 60_11
    ("CR 45 # 64-10", "60_6"),  # desde la CL 64: 60_10
    ("CR 58 # 66-20", "60_6"),  # 60_10 llega ahora hasta la CR 60
    ("CR 35 # 63-20", "60_5"),  # 60_11 empieza ahora en la CR 30
    ("CR 32 # 63B-20", "60_5"), # 60_1 ya no pasa de la CR 30: ahí sigue 60_11
    ("CL 63 # 30-11", None),     # cuadra CR 30–31 sobre la CL 63 (placa impar): fuera de zona
])
def test_ajuste_zonas_60(indice, direccion, zona):
    assert sectorizar(direccion, indice).zona == zona


# ── Paridad en los bordes de 60_1 y 60_13 (prueba de exactitud, 2026-10-09) ───

@pytest.mark.parametrize("direccion,zona", [
    ("CL 63 # 26-62", "60_3"),    # CL 63 placa par: lado de 60_1 (antes quedaba fuera de zona)
    ("CL 63 # 24-44", "60_3"),
    ("CL 63 # 27-11", None),      # CL 63 placa impar: el otro lado de la calle (Teusaquillo)
    ("CL 63F # 25-15", "60_3"),  # CL 63F placa impar: 60_13 (antes no caía en ninguna zona)
    ("CL 63F # 26-22", "60_3"),   # CL 63F placa par: sigue en 60_1
])
def test_paridad_bordes_60_1_y_60_13(indice, direccion, zona):
    assert sectorizar(direccion, indice).zona == zona
