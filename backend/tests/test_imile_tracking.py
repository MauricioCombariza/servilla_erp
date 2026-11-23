"""Tracking de guías en iMile (mejora continua: tiempo de entrega). Con un navegador real
contra el iMile FALSO de tests/fake_imile.py. Solo consulta.

Verifica que:
  1. Se cuentan las novedades ("Problem") con su motivo y hora de Bogotá.
  2. La llegada a la estación es el "Arrived" de la .DS, no el del HUB ni el del centro.
  3. Una guía que iMile no tiene queda como no encontrada.
  4. completar_tracking_pendiente guarda llegada y novedades solo en guías entregadas
     sin tracking, y deja en NULL las que iMile no encontró.
  5. Se mandan los encabezados de la página de seguimiento (resource-code, front-sec y
     hubcode copiados de la página): sin ellos iMile real responde "Unauthorized".
  6. Si iMile está ocupado se espera y se reintenta; si sigue, se detiene la corrida y las
     guías sin consultar quedan pendientes. Varios "Unauthorized" seguidos la detienen.
  7. Si el token vence ("Invalid access token"), se vuelve a entrar a iMile y se reintenta
     la misma guía; si sigue vencido, se detiene sin gastar intentos de las guías.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.imile_sesion import ImileSesion
from app.services.imile_tracking import (
    ImileNoAutorizadoError,
    ImileOcupadoError,
    ImileTokenVencidoError,
    ImileTracking,
    completar_tracking_pendiente,
    leer_tracking,
)
from app.services.imile_tula import ImileConsultaError
from tests.fake_imile import (
    CLAVE,
    FRONT_SEC,
    HUBCODE,
    NO_AUTORIZADO,
    OCUPADO,
    TOKEN_VENCIDO,
    TRACKING,
    USUARIO,
    _FakeImile,
    servidor_fake_imile,
)

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
    _FakeImile.consultas_tracking.clear()
    _FakeImile.encabezados_tracking.clear()
    _FakeImile.ocupado_proximas = 0
    _FakeImile.token_vencido_proximas = 0
    yield s
    _FakeImile.ocupado_proximas = 0
    _FakeImile.token_vencido_proximas = 0
    await s.cerrar()


def _rapido(sesion, **kw) -> ImileTracking:
    """Sin pausas ni esperas reales (en producción: 1,5 s entre guías y 10/30/60 s si está ocupado)."""
    return ImileTracking(sesion=sesion, **{"pausa_s": 0, "esperas_ocupado_s": (0, 0, 0),
                                            "espera_encabezados_ms": 3_000, **kw})


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
    res = await _rapido(sesion, lote=2).consultar(
        ["FAKE-TRK-2NOV", "FAKE-TRK-0NOV", "FAKE-TRK-NOEXISTE"]
    )

    assert len(res["FAKE-TRK-2NOV"].novedades) == 2
    sin_novedades = res["FAKE-TRK-0NOV"]
    assert sin_novedades.novedades == ()
    assert sin_novedades.llegada_ds == datetime(2026, 11, 18, 7, 6, 35, tzinfo=_BOGOTA)
    assert not res["FAKE-TRK-NOEXISTE"].encontrado
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-2NOV", "FAKE-TRK-0NOV", "FAKE-TRK-NOEXISTE"]


async def test_manda_los_encabezados_de_la_pagina_de_seguimiento(sesion):
    await _rapido(sesion).consultar(["FAKE-TRK-0NOV"])

    h = _FakeImile.encabezados_tracking[0]
    assert h["resource-code"] == "dsTrackQuery"
    assert h["front-sec"] == FRONT_SEC
    assert h["hubcode"] == HUBCODE
    assert h["path"] == "/DSOperation/WaybillManagement/dsTrackQuery"
    assert h["x-page-path"].endswith("/#/DSOperation/WaybillManagement/dsTrackQuery")
    assert (h["timezone"], h["lang"], h["sys-name"]) == ("-5", "es_MX", "DS")


def test_clasifica_los_errores_de_imile():
    with pytest.raises(ImileOcupadoError):
        leer_tracking({"status": "fail", "message": OCUPADO}, "G")
    with pytest.raises(ImileNoAutorizadoError):
        leer_tracking({"status": "fail", "message": NO_AUTORIZADO}, "G")
    with pytest.raises(ImileTokenVencidoError):
        leer_tracking({"status": "fail", "message": TOKEN_VENCIDO}, "G")
    with pytest.raises(ImileConsultaError):
        leer_tracking({"status": "fail", "message": "otra cosa"}, "G")


async def test_token_vencido_vuelve_a_entrar_y_reintenta(sesion):
    _FakeImile.token_vencido_proximas = 1
    consulta = _rapido(sesion)
    res = await consulta.consultar(["FAKE-TRK-2NOV", "FAKE-TRK-0NOV"])

    assert consulta.detenida is None
    assert len(res["FAKE-TRK-2NOV"].novedades) == 2 and res["FAKE-TRK-0NOV"].encontrado
    # Token vencido, se vuelve a entrar y la misma guía otra vez
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-2NOV"] * 2 + ["FAKE-TRK-0NOV"]


async def test_token_sigue_vencido_se_detiene_y_deja_el_resto_pendiente(sesion):
    _FakeImile.token_vencido_proximas = 100
    consulta = _rapido(sesion)
    res = await consulta.consultar(["FAKE-TRK-2NOV", "FAKE-TRK-0NOV"])

    assert res == {}  # ninguna guía queda con error: siguen pendientes
    assert "vencido" in consulta.detenida
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-2NOV"] * 2  # 1 + 1 tras volver a entrar


async def test_ocupado_espera_y_reintenta(sesion):
    _FakeImile.ocupado_proximas = 2
    consulta = _rapido(sesion)
    res = await consulta.consultar(["FAKE-TRK-2NOV", "FAKE-TRK-0NOV"])

    assert consulta.detenida is None
    assert len(res["FAKE-TRK-2NOV"].novedades) == 2 and res["FAKE-TRK-0NOV"].encontrado
    # Dos "busy" y luego la misma guía otra vez
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-2NOV"] * 3 + ["FAKE-TRK-0NOV"]


async def test_sigue_ocupado_se_detiene_y_deja_el_resto_pendiente(sesion):
    _FakeImile.ocupado_proximas = 100
    consulta = _rapido(sesion, esperas_ocupado_s=(0, 0))
    res = await consulta.consultar(["FAKE-TRK-2NOV", "FAKE-TRK-0NOV"])

    assert res == {}
    assert "ocupado" in consulta.detenida
    assert len(_FakeImile.consultas_tracking) == 3  # 1 + 2 reintentos


async def test_varios_no_autorizados_seguidos_detienen_la_corrida(sesion, monkeypatch):
    # Sin los encabezados de la página (como la primera versión): iMile no autoriza
    async def solo_token(self, page):
        from app.services.imile_tula import encabezados_api
        return await encabezados_api(page)
    monkeypatch.setattr(ImileTracking, "_encabezados", solo_token)

    consulta = _rapido(sesion, max_no_autorizado=2)
    res = await consulta.consultar(["FAKE-TRK-2NOV", "FAKE-TRK-0NOV", "FAKE-TRK-NOEXISTE"])

    assert set(res) == {"FAKE-TRK-2NOV", "FAKE-TRK-0NOV"}
    assert all(isinstance(r, ImileNoAutorizadoError) for r in res.values())
    assert "no autoriza" in consulta.detenida


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
    resumen = await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion, pausa_s=0))

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
    await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion, pausa_s=0))
    assert _FakeImile.consultas_tracking == ["FAKE-TRK-NOEXISTE"]


async def test_con_tracking_no_se_repite_y_no_encontrada_se_deja_a_los_3_intentos(sesion, seriales):
    for _ in range(5):
        await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion, pausa_s=0))

    # Las encontradas: una sola consulta. La que iMile no tiene: 3 y se deja.
    c = _FakeImile.consultas_tracking
    assert (c.count("FAKE-TRK-2NOV"), c.count("FAKE-TRK-0NOV"), c.count("FAKE-TRK-NOEXISTE")) == (1, 1, 3)
    assert "FAKE-TRK-SINENTREGA" not in c


async def test_no_autorizado_no_gasta_intentos(sesion, seriales, monkeypatch):
    async def solo_token(self, page):
        from app.services.imile_tula import encabezados_api
        return await encabezados_api(page)
    monkeypatch.setattr(ImileTracking, "_encabezados", solo_token)

    await completar_tracking_pendiente(consulta=_SoloPrueba(sesion=sesion, pausa_s=0))
    async with AsyncSessionLocal() as db:
        intentos = (await db.execute(text(
            "SELECT max(tracking_intentos) FROM seriales_gestion WHERE serial LIKE 'FAKE-TRK-%'"
        ))).scalar()
    assert intentos == 0


async def test_guarda_por_tandas_aunque_la_corrida_se_corte(sesion, seriales, monkeypatch):
    import app.services.imile_tracking as mod
    monkeypatch.setattr(mod, "_TANDA_GUARDAR", 1)

    class _SeCorta(_SoloPrueba):
        tandas = 0

        async def consultar(self, guias):
            _SeCorta.tandas += 1
            if _SeCorta.tandas > 1:
                raise RuntimeError("se reinició el backend")
            return await super().consultar(guias)

    with pytest.raises(RuntimeError):
        await completar_tracking_pendiente(consulta=_SeCorta(sesion=sesion, pausa_s=0))

    async with AsyncSessionLocal() as db:
        guardadas = (await db.execute(text(
            "SELECT count(*) FROM seriales_gestion WHERE serial LIKE 'FAKE-TRK-%' AND novedades_imile IS NOT NULL"
        ))).scalar()
    assert guardadas == 1  # la primera tanda quedó guardada


async def test_corrida_detenida_deja_las_guias_pendientes(sesion, seriales):
    _FakeImile.ocupado_proximas = 100
    resumen = await completar_tracking_pendiente(
        consulta=_SoloPrueba(sesion=sesion, pausa_s=0, esperas_ocupado_s=(0,)))

    assert resumen.guardadas == 0
    assert resumen.sin_consultar == 3
    assert "ocupado" in resumen.detenida
    async with AsyncSessionLocal() as db:
        nulos = (await db.execute(text(
            "SELECT count(*) FROM seriales_gestion WHERE serial LIKE 'FAKE-TRK-%' AND novedades_imile IS NULL"
        ))).scalar()
    assert nulos == 4


def test_novedades_se_guardan_como_json_legible():
    t = leer_tracking({"status": "success", "resultObject": {"trackInfo": {
        "G": TRACKING["FAKE-TRK-2NOV"]}}}, "G")
    guardado = json.dumps([{"hora": n.hora.isoformat(), "motivo": n.motivo} for n in t.novedades])
    assert '"hora": "2026-11-17T17:34:07-05:00"' in guardado
