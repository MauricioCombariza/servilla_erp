"""Tests de integración para /api/direcciones y de la función de normalización."""
import io

import pytest

from app.services.direcciones_service import ajustar_dir_leonisa

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
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_ajustar_endpoint_columnas_insuficientes(client, headers):
    contenido = "solo|dos|columnas\n".encode("latin-1")
    r = await client.post(
        "/api/direcciones/ajustar",
        files={"file": ("ordenes.txt", io.BytesIO(contenido), "text/plain")},
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
        json={"nombre_archivo": "20260601", "filas": filas},
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
        json={"nombre_archivo": "../../etc/passwd", "filas": [["a", "b"]]},
        headers=headers,
    )
    assert r.status_code == 200
    assert "/" not in r.headers["content-disposition"].split("filename=")[1]
