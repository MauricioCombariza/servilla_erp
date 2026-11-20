"""Tracking de guías en iMile (mejora continua: tiempo de entrega). Con un navegador real
contra el iMile FALSO de tests/fake_imile.py. Solo consulta.

Verifica que:
  1. Se cuentan las novedades ("Problem") con su motivo y hora de Bogotá.
  2. La llegada a la estación es el "Arrived" de la .DS, no el del HUB ni el del centro.
  3. Una guía que iMile no tiene queda como no encontrada.
  4. completar_tracking_pendiente guarda llegada y novedades solo en guías entregadas
     sin tracking, y deja en NULL las que iMile no encontró.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.imile_sesion import ImileSesion
from app.services.imile_tracking import ImileTracking, completar_tracking_pendiente, leer_tracking
from tests.fake_imile import CLAVE, TRACKING, USUARIO, _FakeImile, servidor_fake_imile

_BOGOTA = timezone(timedelta(hours=-5))


@pytest.fixture(scope="module")
def fake_imile_url():
    with servidor_fake_imile() as url:
        yield url


@pytest.fixture
async def sesion(fake_imile_url, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)
    s = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                    login_timeout_ms=3_000, espera_carga_ms=200,
                    recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield s
    await s.cerrar()


def test_lee_novedades_y_llegada_a_la_estacion():
    body = {"status": "success", "resultObject": {"trackInfo": {"G1": TRACKING["FAKE-TRK-2NOV"]}}}
    t = leer_tracking(body, "G1")

    assert t.encontrado
    assert t.llegada_ds == datetime(2026, 11, 16, 8, 44, 34, tzinfo=_BOGOTA)
    assert [(n.hora, n.motivo) for n in t.novedades] == [
        (datetime(2026, 11, 17, 17, 34, 7, tzinfo=_BOGOTA), "Uncontactable-No Answer/Switched off"),
        (datetime(2026, 11, 18, 17, 10, 55, tzinfo=_BOGOTA), "Need after 7 days"),
    ]


async def test_consulta_varias_guias_en_imile(sesion):
    _FakeImile.consultas_tracking.clear()
    res = await ImileTracking(sesion=sesion, lote=2).consultar(
        ["FAKE-TRK-2NOV", "FAKE-TRK-0NOV", "FAKE-TRK-NOEXISTE"]
    )

    assert len(res["FAKE-TRK-2NOV"].novedades) == 2
    sin_novedades = res["FAKE-TRK-0NOV"]
    assert sin_novedades.novedades == ()
    assert sin_novedades.llegada_ds == datetime(2026, 11, 18, 7, 6, 35, tzinfo=_BOGOTA)
    assert not res["FAKE-TRK-NOEXISTE"].encontrado
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-2NOV", "FAKE-TRK-0NOV", "FAKE-TRK-NOEXISTE"]


# ── Guardar en seriales_gestion ───────────────────────────────────────────────

_GUIAS = {
    "FAKE-TRK-2NOV": datetime(2026, 11, 19, 9, 0, tzinfo=_BOGOTA),        # entregada, 2 novedades
    "FAKE-TRK-0NOV": datetime(2026, 11, 18, 9, 3, 56, tzinfo=_BOGOTA),    # entregada, sin novedades
    "FAKE-TRK-NOEXISTE": datetime(2026, 11, 18, 10, 0, tzinfo=_BOGOTA),   # entregada, iMile no la tiene
    "FAKE-TRK-SINENTREGA": None,                                          # no entregada: no se consulta
}


@pytest.fixture
async def seriales():
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'FAKE-TRK-%'"))
        for serial, entrega in _GUIAS.items():
            await db.execute(text("""
                INSERT INTO seriales_gestion
                    (serial, orden, planilla, f_esc, cod_men, tipo_gestion, tipo_envio,
                     ambito, estado, origen, fecha_entrega)
                VALUES (:s, 'IM20261118', 'IM20261118', '2026-11-18', '0000', 'Entrega',
                        'paquete', 'bogota', 'pendiente', 'manual', :e)
            """), {"s": serial, "e": entrega})
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM seriales_gestion WHERE serial LIKE 'FAKE-TRK-%'"))
        await db.commit()


class _SoloPrueba(ImileTracking):
    """Limita la corrida a las guías de la prueba (la base de pruebas puede tener otras)."""

    async def consultar(self, guias):
        return await super().consultar([g for g in guias if g.startswith("FAKE-TRK-")])


async def test_completar_guarda_llegada_y_novedades(sesion, seriales):
    _FakeImile.consultas_tracking.clear()
    resumen = await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion))

    assert resumen.guardadas == 2
    assert resumen.sin_tracking == 1
    assert "FAKE-TRK-SINENTREGA" not in _FakeImile.consultas_tracking

    async with AsyncSessionLocal() as db:
        filas = {r.serial: r for r in (await db.execute(text(
            "SELECT serial, fecha_llegada_ds, novedades_imile FROM seriales_gestion "
            "WHERE serial LIKE 'FAKE-TRK-%'"
        ))).all()}

    dos = filas["FAKE-TRK-2NOV"]
    assert dos.fecha_llegada_ds == datetime(2026, 11, 16, 8, 44, 34, tzinfo=_BOGOTA)
    assert [n["motivo"] for n in dos.novedades_imile] == [
        "Uncontactable-No Answer/Switched off", "Need after 7 days",
    ]
    assert filas["FAKE-TRK-0NOV"].novedades_imile == []
    assert filas["FAKE-TRK-NOEXISTE"].novedades_imile is None  # se reintenta en la próxima carga
    assert filas["FAKE-TRK-SINENTREGA"].novedades_imile is None

    # Segunda corrida: solo se reintenta la que iMile no encontró
    _FakeImile.consultas_tracking.clear()
    await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion))
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-NOEXISTE"]


def test_novedades_se_guardan_como_json_legible():
    t = leer_tracking({"status": "success", "resultObject": {"trackInfo": {
        "G": TRACKING["FAKE-TRK-2NOV"]}}}, "G")
    guardado = json.dumps([{"hora": n.hora.isoformat(), "motivo": n.motivo} for n in t.novedades])
    assert '"hora": "2026-11-17T17:34:07-05:00"' in guardado
