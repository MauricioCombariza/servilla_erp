"""Tests de la sesión de iMile (Paso 2.0) con un navegador real contra un iMile FALSO
servido en local: mismo formulario de ingreso (userCode / password), recorrido de
bienvenida que aparece tarde y tapa la página, y selector de idioma en el encabezado.
No tocan iMile."""
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.config import settings
from app.services.imile_sesion import (
    ImileCredencialesFaltantesError,
    ImileLoginError,
    ImileSesion,
)

USUARIO, CLAVE = "operador", "clave-secreta"

LOGIN_HTML = f"""<!doctype html><html><body>
<input name="userCode"><input name="password" type="password">
<script>
document.querySelector("input[name=password]").addEventListener("keydown", e => {{
  if (e.key !== "Enter") return;
  const u = document.querySelector("input[name=userCode]").value;
  if (u === "{USUARIO}" && e.target.value === "{CLAVE}") {{
    document.cookie = "sesion=1; path=/"; location.href = "/#";
  }}
}});
</script></body></html>"""

HOME_HTML = """<!doctype html><html><body>
<script>
if (!document.cookie.includes("sesion=1")) location.href = "/login";
const idioma = document.cookie.includes("LANG=es") ? "Español" : "English";
</script>
<header><span id="idioma"></span><ul id="menu" style="display:none">
  <li>English</li><li>简体中文</li><li>Español</li><li>German</li></ul></header>
<main>Inicio</main>
<script>
document.getElementById("idioma").textContent = idioma;
document.getElementById("idioma").onclick = () => document.getElementById("menu").style.display = "block";
document.querySelectorAll("#menu li").forEach(li => li.onclick = () => {
  document.cookie = "LANG=" + (li.textContent === "Español" ? "es_MX" : "en_US") + "; path=/";
  location.reload();
});
// Como en iMile real: el recorrido de bienvenida aparece un rato DESPUÉS de cargar y tapa la página
setTimeout(() => {
  const w = document.createElement("div");
  w.className = "fireWrap";
  w.innerHTML = '<div class="overlay" style="position:fixed;inset:0"></div><div class="close-icon" style="position:fixed;z-index:9">x</div>';
  document.body.appendChild(w);
  w.querySelector(".close-icon").onclick = () => w.remove();
}, 600);
</script></body></html>"""


class _FakeImile(BaseHTTPRequestHandler):
    def do_GET(self):  # nombre fijo de http.server
        cuerpo = LOGIN_HTML if self.path.startswith("/login") else HOME_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(cuerpo.encode())

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def fake_imile_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeImile)
    hilo = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def credenciales(monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", CLAVE)


@pytest.fixture
async def sesion(fake_imile_url, tmp_path):
    s = ImileSesion(base_url=fake_imile_url, state_path=tmp_path / "sesion.json",
                    login_timeout_ms=3_000, espera_carga_ms=200,
                    recorrido_quieto_ms=1_000, recorrido_max_ms=5_000)
    yield s
    await s.cerrar()


async def test_sin_credenciales_no_abre_navegador(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", "")
    monkeypatch.setattr(settings, "imile_pass", "")
    with pytest.raises(ImileCredencialesFaltantesError):
        await sesion.conectar()
    assert (await sesion.estado()).navegador_abierto is False


async def test_conectar_inicia_sesion_cierra_recorrido_y_pone_espanol(sesion, credenciales, tmp_path):
    estado = await sesion.conectar()

    assert estado.conectado and estado.idioma == "Español"
    assert estado.ultimo_ingreso is not None
    assert (tmp_path / "sesion.json").exists()  # la sesión queda guardada para el próximo arranque
    async with sesion.usar() as page:
        assert await page.locator(".fireWrap").count() == 0


async def test_sesion_expirada_vuelve_a_entrar_sola(sesion, credenciales):
    await sesion.conectar()
    primer_ingreso = sesion.ultimo_ingreso
    async with sesion.usar() as page:
        await page.context.clear_cookies()  # iMile cierra la sesión
        await page.reload()

    async with sesion.usar() as page:
        assert "/login" not in page.url
        assert await page.locator("#idioma").inner_text() == "Español"
    assert sesion.ultimo_ingreso > primer_ingreso


async def test_credenciales_incorrectas(sesion, monkeypatch):
    monkeypatch.setattr(settings, "imile_user", USUARIO)
    monkeypatch.setattr(settings, "imile_pass", "mala")
    with pytest.raises(ImileLoginError):
        await sesion.conectar()


async def test_usar_no_deja_que_dos_pasos_escriban_a_la_vez(sesion, credenciales):
    await sesion.conectar()
    dentro = 0
    maximo = 0

    async def paso():
        nonlocal dentro, maximo
        async with sesion.usar():
            dentro += 1
            maximo = max(maximo, dentro)
            await asyncio.sleep(0.05)
            dentro -= 1

    await asyncio.gather(paso(), paso(), paso())
    assert maximo == 1
