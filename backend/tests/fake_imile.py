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
- POST .../unloading/search (Paso 2.3): lo descargado en la estación, un renglón por paquete
  con su tula (bagNo), paginado con pageNum / pageSize. Como iMile real, ignora cualquier
  filtro. Cualquier POST a .../unloading/submit (descargar de verdad) queda en `descargas`.
- #/DSOperation/DispatchManagement/assignDA (Paso 3.3): selector DA con buscador y opciones
  "Nombre | Dxxxx", y Número de Guía. Sin DA elegido no manda nada ("Required"). Al
  escanear hace POST a .../bizAssignDaScan/submit con daCode / daName / forceOperate; el
  servidor guarda cada asignación en `asignaciones` y responde bloqueo 1119 a NOEXISTE…
  Confirmar en la ventana "bloquear" reenvía con forceOperate=true (como iMile real).
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

USUARIO, CLAVE = "operador", "clave-secreta"
BLOQUEO_NO_EXISTE = ("1119", "Sin información de pedido()")
BLOQUEO_PROBLEMA = ("1121", "No registrar Motivo Problema")
# Paso 3.3: mensajeros del selector DA ("Nombre | código"); "Ana Ruiz" está dos veces
MENSAJEROS_IMILE = [("Juan Porras", "D21043330501"), ("Juan Carlos Rodriguez", "D21038000001"),
                    ("Ana Ruiz", "D21000000001"), ("Ana Ruiz", "D21000000002")]
# El selector DA muestra los resultados de la búsqueda con demora (más que el 1,5 s fijo
# que esperaba la primera versión y que no alcanzó en producción el 2026-10-23)
DEMORA_BUSQUEDA_MS = 2_000
# Paso 2.3: tulas ya descargadas en la estación y sus paquetes
DESCARGADOS = {
    "2610154964301": ["FAKE-T1-01", "FAKE-T1-02", "FAKE-T1-03", "FAKE-T1-04"],
    "2610154963701": ["FAKE-T2-01", "FAKE-T2-02"],
}

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
<header><script>const MENSAJEROS = __MENSAJEROS__; const DEMORA_BUSQUEDA_MS = __DEMORA__;</script><span id="idioma"></span><ul id="menu" style="display:none">
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
function renderAsignar(c) {
  c.innerHTML = '<h2>Asignar repartidor</h2><div id="daCode"><div>DA*</div>' +
    '<div class="ImileSelect-root" style="min-width:200px;min-height:30px;border:1px solid"><div class="ImileSelect-trigger-label"></div></div><span id="req"></span></div>' +
    '<label>Número de Guía</label><input name="scanNumber">' +
    '<div id="impresion" role="dialog">Excepción de impresión <span>cierre</span></div>';
  document.querySelector("#impresion span").onclick = () => document.getElementById("impresion").remove();
  let da = null;
  const etiqueta = document.querySelector(".ImileSelect-trigger-label");
  document.querySelector("#daCode .ImileSelect-root").onclick = () => {
    const pop = document.createElement("div");
    pop.className = "MuiTooltip-popper";
    pop.innerHTML = '<input placeholder="buscar"><ul class="ImileSelect-list"></ul>';
    document.body.appendChild(pop);
    const lista = () => {
      const q = pop.querySelector("input").value.toLowerCase();
      pop.querySelector("ul").innerHTML = MENSAJEROS.filter(([n]) => n.toLowerCase().includes(q))
        .map(([n, c]) => '<li class="ImileSelect-item" data-n="' + n + '" data-c="' + c + '">' + n + ' | ' + c + '</li>').join("");
      pop.querySelectorAll("li").forEach(li => li.onclick = () => {
        da = {daName: li.dataset.n, daCode: li.dataset.c};
        etiqueta.textContent = li.textContent; pop.remove();
      });
    };
    // Como iMile real visto desde el servidor: los resultados de la búsqueda llegan tarde
    pop.querySelector("input").oninput = () => {
      pop.querySelector("ul").innerHTML = "";
      clearTimeout(pop.t); pop.t = setTimeout(lista, DEMORA_BUSQUEDA_MS);
    };
    document.addEventListener("keydown", e => { if (e.key === "Escape") pop.remove(); }, {once: true});
    lista();
  };
  const enviar = async (scanNumber, forceOperate) => {
    const r = await fetch("/lm/express/ops/v1/biz/bizAssignDaScan/submit", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({...da, scanNumber, forceOperate, ocCode: "S210445301"})});
    return r.json();
  };
  document.querySelector("input[name=scanNumber]").addEventListener("keydown", async e => {
    if (e.key !== "Enter") return;
    if (!da) { document.getElementById("req").textContent = "Required"; return; }
    const scanNumber = e.target.value.trim();
    const body = await enviar(scanNumber, false);
    if (body.resultObject.blockInfo) {
      ventanaBloqueo(body.resultObject.blockInfo);
      document.querySelector("#confirmar").addEventListener("click", () => enviar(scanNumber, true));
    }
    e.target.value = "";
  });
}
function renderDescarga(c) {
  c.innerHTML = '<h2>Descarga de escaneo</h2><label>Pallet/ Bag /Waybill NO.</label><input name="scanNumber">';
  document.querySelector("input[name=scanNumber]").addEventListener("keydown", async e => {
    if (e.key !== "Enter") return;
    await fetch("/lm/express/ops/v1/biz/unloading/submit", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({scanNumber: e.target.value.trim()})});
    e.target.value = "";
  });
}
function render() {
  const c = document.getElementById("contenido");
  if (location.hash.includes("dsOffloadingScan")) { renderDescarga(c); return; }
  if (location.hash.includes("assignDA")) { renderAsignar(c); return; }
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
    asignaciones: ClassVar[list[dict]] = []  # Paso 3.3: cada POST a .../bizAssignDaScan/submit
    descargas: ClassVar[list[dict]] = []

    def do_GET(self):  # nombre fijo de http.server
        cuerpo = LOGIN_HTML if self.path.startswith("/login") else HOME_HTML.replace(
            "__MENSAJEROS__", json.dumps(MENSAJEROS_IMILE)).replace("__DEMORA__", str(DEMORA_BUSQUEDA_MS))
        self._responder(cuerpo.encode(), "text/html; charset=utf-8")

    def do_POST(self):  # nombre fijo de http.server
        largo = int(self.headers.get("Content-Length", 0))
        datos = json.loads(self.rfile.read(largo) or b"{}")
        if "/unloading/submit" in self.path:
            self.descargas.append(datos)
            return self._json({"status": "success", "resultObject": None})
        if "/unloading/search" in self.path:
            filas = [{"waybillNo": w, "bagNo": b, "scanNumber": b, "scanNumberType": "bag", "scanType": "Offloading"}
                     for b, ws in DESCARGADOS.items() for w in ws]
            tam, num = int(datos.get("pageSize", 20)), int(datos.get("pageNum", 1))
            pagina = filas[(num - 1) * tam:num * tam]
            return self._json({"status": "success", "resultObject": {
                "results": pagina, "pagination": {"currentPage": num, "pageSize": tam, "totalResult": len(filas)}}})
        if "/bizAssignDaScan/submit" in self.path:
            return self._asignar(datos)
        serial = datos.get("scanNumber", "")
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
        self._json({"status": "success", "resultCode": "", "message": "Successful operation!", "resultObject": ro})

    def _asignar(self, datos: dict):
        serial = datos.get("scanNumber", "")
        ro = {"scanNumber": serial, "scanType": "Asignar DA", "status": 2, "popup": True, "repeat": False,
              "voiceType": "success", "driverCode": datos.get("daCode"), "driverName": datos.get("daName")}
        if serial.startswith("NOEXISTE") and not datos.get("forceOperate"):
            ro.update(blockCode=BLOQUEO_NO_EXISTE[0], blockInfo=BLOQUEO_NO_EXISTE[1], voiceType="fail")
        else:
            previas = [a for a in self.asignaciones if a["scanNumber"] == serial and a["daCode"] == datos.get("daCode")]
            ro["repeat"] = bool(previas)
            self.asignaciones.append(datos)
        self._json({"status": "success", "resultCode": "", "message": "Successful operation!", "resultObject": ro})

    def _json(self, cuerpo: dict):
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
