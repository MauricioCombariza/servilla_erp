"""Informe de tiempo de entrega iMile (/api/tiempo-entrega).

Verifica que:
  1. Tiempo real = horas seguidas entre la llegada a la estación y la entrega.
  2. Se descuentan 24 h por devolución y cumple si queda en 48 h o menos.
  3. El rango filtra por el día de entrega en hora de Bogotá.
  4. Una guía sin tracking sale en el listado, pero no cuenta para el % ni los promedios.
  5. El Excel se descarga.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.tiempo_entrega_service import calcular

_BOG = timezone(timedelta(hours=-5))
_NOV = [{"hora": "2026-11-17T12:54:00-05:00", "motivo": "Uncontactable-No Answer/Switched off"}]

# serial: (llegada a la estación, entrega, novedades)
_GUIAS = {
    # 2 h, sin devoluciones → cumple
    "TE-TEST-RAPIDA": (datetime(2026, 11, 18, 7, 6, tzinfo=_BOG), datetime(2026, 11, 18, 9, 6, tzinfo=_BOG), []),
    # 60 h con 1 devolución → 36 h ajustadas → cumple
    "TE-TEST-1DEV": (datetime(2026, 11, 16, 8, 0, tzinfo=_BOG), datetime(2026, 11, 18, 20, 0, tzinfo=_BOG), _NOV),
    # 50 h sin devoluciones → no cumple
    "TE-TEST-LENTA": (datetime(2026, 11, 16, 7, 0, tzinfo=_BOG), datetime(2026, 11, 18, 9, 0, tzinfo=_BOG), []),
    # Entregada, todavía sin tracking
    "TE-TEST-SINTRK": (None, datetime(2026, 11, 18, 10, 0, tzinfo=_BOG), None),
    # Entregada el 19 a las 23:30 de Bogotá (ya es 20 en UTC): está dentro de un rango hasta el 19
    "TE-TEST-NOCHE": (datetime(2026, 11, 19, 20, 0, tzinfo=_BOG), datetime(2026, 11, 19, 23, 30, tzinfo=_BOG), []),
    # Entregada fuera del rango
    "TE-TEST-FUERA": (datetime(2026, 11, 1, 8, 0, tzinfo=_BOG), datetime(2026, 11, 2, 8, 0, tzinfo=_BOG), []),
}


def test_calcular():
    llegada = datetime(2026, 11, 16, 8, 0, tzinfo=_BOG)
    assert calcular(llegada, llegada + timedelta(hours=72), 1) == (72.0, 48.0, True)
    assert calcular(llegada, llegada + timedelta(hours=72.5), 1) == (72.5, 48.5, False)
    assert calcular(None, llegada, 0) == (None, None, None)
    assert calcular(llegada, llegada, None) == (None, None, None)


@pytest.fixture(scope="module")
async def auth_headers(client):
    import bcrypt
    pwd_hash = bcrypt.hashpw(b"te-test-pw", bcrypt.gensalt()).decode()
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'te_test_user'"))
        await db.execute(text("""
            INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo)
            VALUES ('te_test_user', :h, 'TE Test', 'administrador', TRUE)
        """), {"h": pwd_hash})
        await db.commit()
    r = await client.post("/api/auth/login", json={"username": "te_test_user", "password": "te-test-pw"})
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usuarios WHERE username = 'te_test_user'"))
        await db.commit()


@pytest.fixture(scope="module")
async def guias():
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'TE-TEST-%'"))
        for serial, (llegada, entrega, novedades) in _GUIAS.items():
            await db.execute(text("""
                INSERT INTO seriales_gestion
                    (serial, orden, planilla, f_esc, cod_men, tipo_gestion, tipo_envio, ambito,
                     estado, origen, fecha_llegada_ds, fecha_entrega, novedades_imile)
                VALUES (:s, 'IM20261118', 'IM20261118', '2026-11-18', '0000', 'Entrega', 'paquete',
                        'bogota', 'pendiente', 'manual', :l, :e, CAST(:n AS JSONB))
            """), {"s": serial, "l": llegada, "e": entrega,
                   "n": None if novedades is None else json.dumps(novedades)})
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'TE-TEST-%'"))
        await db.commit()


async def test_informe_por_rango(client, auth_headers, guias):
    r = await client.get("/api/tiempo-entrega", params={"desde": "2026-11-18", "hasta": "2026-11-19"},
                         headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    por_guia = {g["serial"]: g for g in data["guias"] if g["serial"].startswith("TE-TEST-")}

    assert set(por_guia) == {"TE-TEST-RAPIDA", "TE-TEST-1DEV", "TE-TEST-LENTA", "TE-TEST-SINTRK", "TE-TEST-NOCHE"}

    dev = por_guia["TE-TEST-1DEV"]
    assert (dev["devoluciones"], dev["horas_reales"], dev["horas_ajustadas"], dev["cumple"]) == (1, 60.0, 36.0, True)
    assert por_guia["TE-TEST-RAPIDA"]["horas_reales"] == 2.0
    assert por_guia["TE-TEST-LENTA"]["cumple"] is False
    sin = por_guia["TE-TEST-SINTRK"]
    assert (sin["devoluciones"], sin["fecha_inicial"], sin["cumple"]) == (None, None, None)

    # La base de pruebas puede tener otras guías: el resumen se revisa solo si están las de la prueba
    if len(data["guias"]) == len(por_guia):
        res = data["resumen"]
        assert (res["total"], res["con_tracking"], res["sin_tracking"], res["cumplen"]) == (5, 4, 1, 3)
        assert res["porcentaje_cumple"] == 75.0
        assert res["con_devoluciones"] == 1


async def test_rango_invertido(client, auth_headers):
    r = await client.get("/api/tiempo-entrega", params={"desde": "2026-11-19", "hasta": "2026-11-18"},
                         headers=auth_headers)
    assert r.status_code == 400


async def test_excel(client, auth_headers, guias):
    r = await client.get("/api/tiempo-entrega/excel", params={"desde": "2026-11-18", "hasta": "2026-11-19"},
                         headers=auth_headers)
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx = zip
