"""iMile FALSO para las pruebas: se sirve en local y reproduce lo que la automatización
necesita de ds.imile.com, sin tocar el iMile real.

- /login: campos userCode / password; con las credenciales correctas deja cookie de sesión.
- Encabezado con selector de idioma (cookie LANG) y el recorrido de bienvenida, que
  aparece unos segundos DESPUÉS de cargar y tapa la página (como en iMile real).
- #/DSOperation/OperationManagement/arrivalScanAWB: "Llegada (Waybill No)" con el campo
  scanNumber y el aviso "Excepción de impresión" ("cierre"). Al escanear, la página hace
  POST a .../inbound/submit y el servidor responde con el mismo JSON que iMile real:
  bloqueo 1119 "Sin información de pedido()" (seriales NOEXISTE…), bloqueo 1121
  "No registrar Motivo Problema" (seriales BLOQ…), repeat=true si ya se ingresó, o éxito.
  Un bloqueo abre la ventana "bloquear" con Cancelar / Confirmar (textos, no <button>).
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

USUARIO, CLAVE = "operador", "clave-secreta"
BLOQUEO_NO_EXISTE = ("1119", "Sin información de pedido()")
BLOQUEO_PROBLEMA = ("1121", "No registrar Motivo Problema")

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
<main id="contenido">Inicio</main>
<script>
document.getElementById("idioma").textContent = idioma;
document.getElementById("idioma").onclick = () => document.getElementById("menu").style.display = "block";
document.querySelectorAll("#menu li").forEach(li => li.onclick = () => {
  document.cookie = "LANG=" + (li.textContent === "Español" ? "es_MX" : "en_US") + "; path=/";
  location.reload();
});
setTimeout(() => {
  const w = document.createElement("div");
  w.className = "fireWrap";
  w.innerHTML = '<div class="overlay" style="position:fixed;inset:0"></div><div class="close-icon" style="position:fixed;z-index:9">x</div>';
  document.body.appendChild(w);
  w.querySelector(".close-icon").onclick = () => w.remove();
}, 600);

function ventanaBloqueo(info) {
  const v = document.createElement("div");
  v.setAttribute("role", "dialog");
  v.id = "bloqueo";
  v.innerHTML = '<p>bloquear</p><p>' + info + '</p><span id="cancelar">Cancelar</span> <span id="confirmar">Confirmar</span>';
  document.body.appendChild(v);
  v.querySelector("#cancelar").onclick = () => v.remove();
  v.querySelector("#confirmar").onclick = () => { localStorage.setItem("confirmado", "1"); v.remove(); };
}
function render() {
  const c = document.getElementById("contenido");
  if (!location.hash.includes("arrivalScanAWB")) { c.textContent = "Inicio"; return; }
  c.innerHTML = '<h2>Llegada(Waybill No)</h2><label>Número de Guía</label><input name="scanNumber">' +
    '<div id="impresion" role="dialog">Excepción de impresión <span>cierre</span></div>';
  document.querySelector("#impresion span").onclick = () => document.getElementById("impresion").remove();
  document.querySelector("input[name=scanNumber]").addEventListener("keydown", async e => {
    if (e.key !== "Enter") return;
    const scanNumber = e.target.value.trim();
    const r = await fetch("/lm/express/ops/v1/biz/inbound/submit", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({scanNumber, weight: "", onlyWaybillSupported: true})});
    const body = await r.json();
    if (body.resultObject.blockInfo) ventanaBloqueo(body.resultObject.blockInfo);
    e.target.value = "";
  });
}
window.addEventListener("hashchange", render);
render();
</script></body></html>"""


class _FakeImile(BaseHTTPRequestHandler):
    # Compartido entre peticiones (http.server crea un handler por petición)
    ingresados: ClassVar[set[str]] = set()

    def do_GET(self):  # nombre fijo de http.server
        cuerpo = LOGIN_HTML if self.path.startswith("/login") else HOME_HTML
        self._responder(cuerpo.encode(), "text/html; charset=utf-8")

    def do_POST(self):  # nombre fijo de http.server
        largo = int(self.headers.get("Content-Length", 0))
        serial = json.loads(self.rfile.read(largo) or b"{}").get("scanNumber", "")
        ro = {"scanNumber": serial, "scanTypeDesc": "Llegar", "status": 2, "popup": True,
              "repeat": False, "voiceType": "success"}
        if serial.startswith("NOEXISTE"):
            ro.update(blockCode=BLOQUEO_NO_EXISTE[0], blockInfo=BLOQUEO_NO_EXISTE[1], voiceType="fail")
        elif serial.startswith("BLOQ"):
            ro.update(blockCode=BLOQUEO_PROBLEMA[0], blockInfo=BLOQUEO_PROBLEMA[1], voiceType="fail")
        elif serial in self.ingresados:
            ro.update(repeat=True, warnMsg="Ya escaneado")
        else:
            self.ingresados.add(serial)
        cuerpo = {"status": "success", "resultCode": "", "message": "Successful operation!", "resultObject": ro}
        self._responder(json.dumps(cuerpo).encode(), "application/json")

    def _responder(self, cuerpo: bytes, tipo: str):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *args):
        pass


@contextmanager
def servidor_fake_imile():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeImile)
    hilo = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
