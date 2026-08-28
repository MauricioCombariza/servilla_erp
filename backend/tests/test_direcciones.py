"""Tests de integración para /api/direcciones y de la función de normalización."""
import io

import pytest

from app.services.direcciones_service import (
    VHG_FIELDS,
    ajustar_dir_leonisa,
    generar_txt_vehigrupo,
    procesar_archivo_vehigrupo,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def token(client):
    r = await client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return r.json()["access_token"]


@pytest.fixture(scope="module")
async def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Tests unitarios de ajustar_dir_leonisa (ejemplos del docstring) ────────────

@pytest.mark.parametrize("raw,esperado", [
    ("CARRERA 78 K  # 50   53 CASA", "KRA 78K 50 53 CS"),
    ("KRA.81H 51C-81 SUR", "KRA 81H 51C 81 SUR"),
    (
        "CLL 54C SUR 88I 65 CONJUNTO RESIDENCIAL TANGARA 1 TORRE 4 APTO 1106",
        "CLL 54C SUR 88I 65 APTO 1106 TO 4",
    ),
    (
        "CLL 51 SUR 87D-79 PISO 1 ENTREGAR DE LUNES A VIERNES 8 AM A 5 PM",
        "CLL 51 SUR 87D 79 PS 1",
    ),
    ("carretera 80 45 30", "KRA 80 45 30"),
    ("avenida caracas 53 20 sur", "KRA 14 53 20 SUR"),
    ("carrera 15 40 20 bloque 2 apto 501", "KRA 15 40 20 APTO 501 BL 2"),
    ("carrera 15 40 20 edificio 5 apto 302", "KRA 15 40 20 APTO 302 ED 5"),
])
def test_ajustar_dir_leonisa_ejemplos(raw, esperado):
    assert ajustar_dir_leonisa(raw) == esperado


@pytest.mark.parametrize("raw", [
    "CARRERA 78 K  # 50   53 CASA",
    "carrera 78 k  # 50   53 casa",
    "Carrera 78 K  # 50   53 Casa",
])
def test_ajustar_dir_leonisa_independiente_de_case(raw):
    # Mayúsculas, minúsculas o Title Case deben dar exactamente el mismo resultado
    assert ajustar_dir_leonisa(raw) == "KRA 78K 50 53 CS"


def test_ajustar_dir_leonisa_vacio():
    assert ajustar_dir_leonisa("") == ""
    assert ajustar_dir_leonisa(None) == ""


def test_ajustar_dir_leonisa_sin_via_reconocida():
    # Sin tipo de vía reconocido → no se modifica más allá de uppercase
    raw = "barrio desconocido sin coordenadas"
    assert ajustar_dir_leonisa(raw) == raw.upper()


def test_ajustar_dir_leonisa_menos_de_3_coordenadas_queda_en_mayusculas():
    # No hay placa (solo 2 números) → no se reordena con confianza, pero el
    # resultado nunca queda en minúsculas.
    assert ajustar_dir_leonisa("cll 80 45") == "CLL 80 45"


@pytest.mark.parametrize("raw,esperado", [
    ("GUAYACAN DE LA PLAZACL 48 SUR 39 57 AP 566", "CLL 48 SUR 39 57 APTO 566"),
    ("OCEANACL 39 52 95 AP 914", "CLL 39 52 95 APTO 914"),
    ("REFUGIO VALLE VERDEAV 26 51 81 AP 1615 BL 2", "AV 26 51 81 APTO 1615 BL 2"),
    ("NOGALES APARTAMENTOSCR 65 C 72 140 AP 1107 TO 1", "KRA 65C 72 140 APTO 1107 TO 1"),
    # también pegado a un número (no solo a una palabra)
    ("AP 1916CR 61 33 51", "KRA 61 33 51"),
    ("CIVITACR 49A 48 200 TO 3 AP 3147", "KRA 49A 48 200 APTO 3147 TO 3"),
])
def test_ajustar_dir_leonisa_tipo_via_pegado_al_nombre_anterior(raw, esperado):
    # El tipo de vía puede venir pegado (sin espacio) al nombre del
    # barrio/conjunto o a un número de complemento que lo precede — común
    # en el archivo Vehigrupo.
    assert ajustar_dir_leonisa(raw) == esperado


def test_ajustar_dir_leonisa_tipo_via_pegado_no_rompe_palabras_normales():
    # Palabras que contienen una subcadena de tipo de vía pero no la tienen
    # pegada a números de dirección no deben partirse.
    assert ajustar_dir_leonisa("CONJUNTO IRUNKM 69 VIA PANAMERICANA") == \
        "CONJUNTO IRUNKM 69 VIA PANAMERICANA"


def test_ajustar_dir_leonisa_ca_es_carrera():
    # En el archivo Vehigrupo "CA" se usa como abreviatura de Carrera (no de
    # Casa, que usa "CASA"/"CS").
    assert ajustar_dir_leonisa("CA 82A 30 57 AP 401") == "KRA 82A 30 57 APTO 401"


def test_ajustar_dir_leonisa_to_ya_abreviado_se_reconoce():
    # "TO" (Torre ya abreviada, como viene en el archivo Vehigrupo) debe
    # reconocerse igual que "TORRE"/"TRR", no solo la palabra completa.
    assert ajustar_dir_leonisa("carrera 15 40 20 apto 501 to 2") == "KRA 15 40 20 APTO 501 TO 2"


@pytest.mark.parametrize("raw,esperado", [
    ("Calle160#14b-42 torre 1 apt 304", "CLL 160 14B 42 APTO 304 TO 1"),
    ("carrera 15 40 20 apt 501", "KRA 15 40 20 APTO 501"),
])
def test_ajustar_dir_leonisa_apt_abreviado_se_reconoce(raw, esperado):
    # "APT" (Apartamento abreviado a 3 letras) debe reconocerse igual que
    # "APTO"/"AP"/"APARTAMENTO", no descartarse como ruido.
    assert ajustar_dir_leonisa(raw) == esperado


def test_ajustar_dir_leonisa_edificio_con_nombre_propio():
    # Cuando "EDIFICIO" no va seguido de un número, lo que sigue suele ser el
    # nombre propio del edificio: se conserva y se agrega al final (en vez de
    # descartarse como ruido). Letras sueltas (numeración romana de torre/
    # bloque, p.ej. "PARK I") se descartan por ambiguas.
    assert ajustar_dir_leonisa(
        "CARRERA 20   # 127 B  22 EDIFICIO CALLEJA PARK I APT 302"
    ) == "KRA 20 127B 22 APTO 302 ED CALLEJA PARK"
    assert ajustar_dir_leonisa(
        "Av Carrera 9 # 146 - 45 Apto 702 Edificio Milano Park"
    ) == "KRA 9 146 45 APTO 702 ED MILANO PARK"


def test_ajustar_dir_leonisa_p_abreviado_es_piso():
    # "P" suelto (sin punto ni más letras) se usa como abreviatura de "PISO"
    # en algunos archivos.
    assert ajustar_dir_leonisa("CR 11 N 86 60 P 7") == "KRA 11 86 60 PS 7"


def test_ajustar_dir_leonisa_n_suelto_se_descarta():
    # "N" suelto (separado por espacios, no pegado a un número) se usa como
    # indicador de número ("No") en algunos archivos y no debe confundirse
    # con una letra de coordenada real (compárese con "carrera 78 K" en
    # test_ajustar_dir_leonisa_ejemplos, donde la letra SÍ se conserva).
    assert ajustar_dir_leonisa("CR 11  N 86 60") == "KRA 11 86 60"


def test_ajustar_dir_leonisa_bis_suelto_sin_letra():
    # "BIS" como token separado y sin letra de coordenada de por medio
    # ("14 BIS", no "87D BIS") no era reconocido por el colector de
    # coordenadas y abortaba todo el parseo, dejando la dirección completa
    # sin normalizar (sin abreviar vía/torre/apto ni reordenar complementos).
    assert ajustar_dir_leonisa("Kra 14 Bis 153-80 Torre 16 Apto 101") == \
        "KRA 14BIS 153 80 APTO 101 TO 16"


# ── Tests de integración de los endpoints ──────────────────────────────────────

def _archivo_muestra() -> bytes:
    filas = [
        "ORD-1|SER-1|2026-06-01|Cliente Uno|BOGOTA|CARRERA 78 K # 50 53 CASA",
        "ORD-2|SER-2|2026-06-01|Cliente Dos|BOGOTA|KRA.81H 51C-81 SUR",
    ]
    return ("\n".join(filas) + "\n").encode("latin-1")


@pytest.mark.asyncio
async def test_ajustar_endpoint(client, headers):
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("ordenes.txt", io.BytesIO(_archivo_muestra()), "text/plain")},
        data={"cliente": "leonisa"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_filas"] == 2
    assert data["total_columnas"] == 6
    assert data["col_direccion"] == 5
    assert data["filas"][0][5] == "KRA 78K 50 53 CS"
    assert data["filas"][1][5] == "KRA 81H 51C 81 SUR"
    # Las demás columnas quedan intactas
    assert data["filas"][0][0] == "ORD-1"
    assert data["filas"][0][3] == "Cliente Uno"


@pytest.mark.asyncio
async def test_ajustar_endpoint_extension_invalida(client, headers):
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("ordenes.csv", io.BytesIO(b"a|b"), "text/csv")},
        data={"cliente": "leonisa"},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ajustar_endpoint_columnas_insuficientes(client, headers):
    contenido = "solo|dos|columnas\n".encode("latin-1")
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("ordenes.txt", io.BytesIO(contenido), "text/plain")},
        data={"cliente": "leonisa"},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ajustar_endpoint_cliente_invalido(client, headers):
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("ordenes.txt", io.BytesIO(_archivo_muestra()), "text/plain")},
        data={"cliente": "otro"},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_descargar_endpoint_roundtrip(client, headers):
    filas = [
        ["ORD-1", "SER-1", "2026-06-01", "Cliente Uno", "KRA 78K 50 53 CASA"],
        ["ORD-2", "SER-2", "2026-06-01", "Cliente Dos", "KRA 81H 51C 81 SUR"],
    ]
    r = await client.post(
        "/api/direcciones/descargar",
        json={"cliente": "leonisa", "nombre_archivo": "20260601", "filas": filas},
        headers=headers,
    )
    assert r.status_code == 200
    # application/octet-stream (no "; charset=utf-8" engañoso: los bytes son latin-1)
    assert r.headers["content-type"] == "application/octet-stream"
    assert 'filename="20260601.txt"' in r.headers["content-disposition"]

    texto = r.content.decode("latin-1")
    lineas = texto.strip("\n").split("\n")
    assert len(lineas) == 2
    assert lineas[0] == "ORD-1|SER-1|2026-06-01|Cliente Uno|KRA 78K 50 53 CASA"
    assert lineas[1] == "ORD-2|SER-2|2026-06-01|Cliente Dos|KRA 81H 51C 81 SUR"


@pytest.mark.asyncio
async def test_descargar_endpoint_sanitiza_nombre(client, headers):
    r = await client.post(
        "/api/direcciones/descargar",
        json={"cliente": "leonisa", "nombre_archivo": "../../etc/passwd", "filas": [["a", "b"]]},
        headers=headers,
    )
    assert r.status_code == 200
    assert "/" not in r.headers["content-disposition"].split("filename=")[1]


# ── Banco Vehigrupo: ancho fijo (288 caracteres/línea, CRLF, latin-1) ──────────

def _linea_vhg(doc="", nombre="", direccion="", barrio="", ciudad="", depto="", cola="") -> str:
    valores = [doc, nombre, direccion, barrio, ciudad, depto, cola]
    return "".join(v.ljust(fin - inicio) for v, (inicio, fin) in zip(valores, VHG_FIELDS))


def _archivo_vhg_muestra() -> bytes:
    lineas = [
        _linea_vhg(
            doc="CC00000000000000000000000000004263000001",
            nombre="RAMIREZ GIRALDO JOHN OLIVER",
            direccion="CL 49 50C 107",
            barrio="EL HOSPITAL",
            ciudad="",
            depto="",
            cola="1I",
        ),
        _linea_vhg(
            doc="CC00000000000000000000000000004476000002",
            nombre="TABARES BETANCUR JUAN CARLOS",
            direccion="CARRERA 48 49 14",
            barrio="CENTRO",
            ciudad="AMAGA",
            depto="ANTIOQUIA",
            cola="1I",
        ),
    ]
    return ("\r\n".join(lineas) + "\r\n").encode("latin-1")


def test_procesar_archivo_vehigrupo_normaliza_direccion_y_preserva_resto():
    resultado = procesar_archivo_vehigrupo(_archivo_vhg_muestra())
    assert resultado.total_filas == 2
    assert resultado.total_columnas == 7
    assert resultado.col_direccion == 2
    assert resultado.filas[0][2] == "CLL 49 50C 107"
    assert resultado.filas[1][2] == "KRA 48 49 14"
    # Los demás campos quedan intactos (con su padding de ancho fijo original)
    assert resultado.filas[0][1].strip() == "RAMIREZ GIRALDO JOHN OLIVER"
    assert resultado.filas[1][4].strip() == "AMAGA"


def test_procesar_archivo_vehigrupo_linea_corta_lanza_error():
    with pytest.raises(ValueError):
        procesar_archivo_vehigrupo(b"linea demasiado corta\r\n")


def test_generar_txt_vehigrupo_roundtrip_preserva_ancho_fijo():
    resultado = procesar_archivo_vehigrupo(_archivo_vhg_muestra())
    contenido = generar_txt_vehigrupo(resultado.filas)
    lineas = contenido.decode("latin-1").split("\r\n")
    lineas = [l for l in lineas if l]  # descarta el "" final tras el último \r\n
    assert len(lineas) == 2
    assert all(len(l) == 288 for l in lineas)
    assert lineas[0][105:170].strip() == "CLL 49 50C 107"
    # Campos no editados se preservan exactamente
    assert lineas[1][216:251].strip() == "AMAGA"


def test_generar_txt_vehigrupo_direccion_larga_no_trunca():
    fila = [
        "CC" + "0" * 38,
        "NOMBRE".ljust(65),
        "X" * 90,  # dirección más larga que el campo (65)
        "BARRIO".ljust(46),
        "CIUDAD".ljust(35),
        "DEPTO".ljust(29),
        "1I".rjust(8),
    ]
    contenido = generar_txt_vehigrupo([fila])
    linea = contenido.decode("latin-1").split("\r\n")[0]
    assert "X" * 90 in linea
    assert len(linea) > 288  # no se truncó: la línea creció


@pytest.mark.asyncio
async def test_ajustar_endpoint_vehigrupo(client, headers):
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("BD_VHG.txt", io.BytesIO(_archivo_vhg_muestra()), "text/plain")},
        data={"cliente": "vehigrupo"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total_filas"] == 2
    assert data["total_columnas"] == 7
    assert data["col_direccion"] == 2
    assert data["filas"][0][2] == "CLL 49 50C 107"


@pytest.mark.asyncio
async def test_descargar_endpoint_vehigrupo_roundtrip(client, headers):
    ajustar = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("BD_VHG.txt", io.BytesIO(_archivo_vhg_muestra()), "text/plain")},
        data={"cliente": "vehigrupo"},
        headers=headers,
    )
    filas = ajustar.json()["filas"]

    r = await client.post(
        "/api/direcciones/descargar",
        json={"cliente": "vehigrupo", "nombre_archivo": "BD_VHG", "filas": filas},
        headers=headers,
    )
    assert r.status_code == 200
    lineas = [l for l in r.content.decode("latin-1").split("\r\n") if l]
    assert len(lineas) == 2
    assert all(len(l) == 288 for l in lineas)
