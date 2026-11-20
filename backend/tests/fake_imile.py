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
- POST /saastms/v1/biz/track/query (tracking de una guía, mejora continua): devuelve los
  eventos de TRACKING con el mismo formato que iMile real (2026-11-19). Guía que no está
  → trackInfo vacío. Cada consulta queda en `consultas_tracking` y sus encabezados en
  `encabezados_tracking`. Como iMile real (2026-11-20), sin resource-code: dsTrackQuery
  y el front-sec del usuario responde "Unauthorized data access"; con `ocupado_proximas`
  > 0, las siguientes consultas responden "The system is busy".
- #/DSOperation/WaybillManagement/dsTrackQuery: al abrirse, la página hace un pedido
  con front-sec / hubcode (como las páginas de iMile real).
"""
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

USUARIO, CLAVE = "operador", "clave-secreta"
# Encabezados que la página de iMile pone en cada pedido (valores inventados)
FRONT_SEC = '{"orgId":10,"entId":10,"userCode":"0000000000","moduleId":10007,"client":"pc"}'
HUBCODE = "S000000001"
NO_AUTORIZADO = "Unauthorized data access. Please refresh the page and try again."
OCUPADO = "The system is busy,please try again later"
BLOQUEO_NO_EXISTE = ("1119", "Sin información de pedido()")
BLOQUEO_PROBLEMA = ("1121", "No registrar Motivo Problema")
# Paso 3.3: mensajeros del selector DA ("Nombre | código"); "Ana Ruiz" está dos veces
MENSAJEROS_IMILE = [("Juan Porras", "D21043330501"), ("Juan Carlos Rodriguez", "D21038000001"),
                    ("Ana Ruiz", "D21000000001"), ("Ana Ruiz", "D21000000002"),
                    ("Carlos Pérez Rojas", "D21050000001"), ("Diana  Mora", "D21050000002")]
# El selector DA muestra los resultados de la búsqueda con demora (más que el 1,5 s fijo
# que esperaba la primera versión y que no alcanzó en producción el 2026-10-23)
DEMORA_BUSQUEDA_MS = 2_000
# Paso 2.3: tulas ya descargadas en la estación y sus paquetes
DESCARGADOS = {
    "2610154964301": ["FAKE-T1-01", "FAKE-T1-02", "FAKE-T1-03", "FAKE-T1-04"],
    "2610154963701": ["FAKE-T2-01", "FAKE-T2-02"],
}
# Tulas que llegaron en el vehículo pero nadie ha descargado: al descargarlas
# (unloading/submit) pasan a DESCARGADOS y ya aparecen en la consulta
SIN_DESCARGAR = {
    "2611063528401": ["FAKE-T3-01", "FAKE-T3-02", "FAKE-T3-03"],
}


def _evento(content: str, time: str, track_type: str = "", stage: int | None = 1003) -> dict:
    return {"content": content, "trackStage": stage, "trackStageTx": "En Proceso de Reparto",
            "time": time, "trackType": track_type}


_PRUEBA = "<div class='viewPic' data-pic='lms/app/re_driver/img/problem/x.png,'>【View Proof】</div>"
# Tracking de guías (copiado de iMile real, guía 6110626411459, sin nombres ni teléfonos).
# Del más nuevo al más viejo, como lo manda iMile.
TRACKING = {
    "FAKE-TRK-2NOV": [
        _evento("【BOG-Doce de Octubre.DS】add a problem[Need after 7 days], The Operator is 【DA Prueba】."
                + _PRUEBA, "2026-11-18 17:10:55", "Problem"),
        _evento("【BOG-Doce de Octubre.DS】Has dispatched(DA: DA Prueba,ID: D0) ,The Operator is 【DA Prueba】",
                "2026-11-18 16:03:48", "Delivery"),
        _evento("【BOG-Doce de Octubre.DS】add a problem[Uncontactable-No Answer/Switched off], "
                "The Operator is 【DA Prueba】." + _PRUEBA, "2026-11-17 17:34:07", "Problem"),
        _evento("【BOG-Doce de Octubre.DS】Has dispatched(DA: DA Prueba,ID: D0) ,The Operator is 【DA Prueba】",
                "2026-11-17 13:54:35", "Delivery"),
        _evento(" 【BOG-Doce de Octubre.DS】Dispatch assigned to DA (DA：DA Prueba)，Pending on DA confirmed ,"
                "The Operator is 【Operador】 ", "2026-11-16 10:26:14"),
        _evento("【BOG-Doce de Octubre.DS】Arrived ,The Operator is 【Operador】.", "2026-11-16 08:44:34"),
        _evento("【BOG-Doce de Octubre.DS】Bag/Pallet[2611147559501]is offloaded.Trunk UUID【BGNB202611150014】."
                "The Operator is 【Operador】", "2026-11-16 08:09:32", stage=1002),
        _evento("【BOG-BOG NORTE.HUB】Arrived ,The Operator is 【Operador】.", "2026-11-14 21:21:36", stage=1002),
        _evento("【COL Center】Arrived，the package weight is【0.0kg】 ,The Operator is 【sorter】",
                "2026-11-14 13:39:51", stage=1002),
        _evento("Order Submited through [OpenApi] ", "2026-11-06 05:48:35", stage=1001),
    ],
    "FAKE-TRK-0NOV": [
        _evento("【BOG-Doce de Octubre.DS】Has dispatched(DA: DA Prueba,ID: D0) ,The Operator is 【DA Prueba】",
                "2026-11-18 08:18:44", "Delivery"),
        _evento("【BOG-Doce de Octubre.DS】Arrived ,The Operator is 【Operador】.", "2026-11-18 07:06:35"),
        _evento("【BOG-BOG NORTE.HUB】Arrived ,The Operator is 【Operador】.", "2026-11-17 21:00:00", stage=1002),
    ],
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
<header><script>const MENSAJEROS = __MENSAJEROS__; const DEMORA_BUSQUEDA_MS = __DEMORA__;
const FRONT_SEC = __FRONT_SEC__; const HUBCODE = __HUBCODE__;</script><span id="idioma"></span><ul id="menu" style="display:none">
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
  if (location.hash.includes("dsTrackQuery")) {
    c.innerHTML = '<h2>Consulta de seguimiento</h2>';
    fetch("/saastms/v1/base/menu/list", {method: "POST", body: "{}", headers: {
      "Content-Type": "application/json", "front-sec": FRONT_SEC, "hubcode": HUBCODE,
      "lang": "es_MX", "sys-name": "DS", "sys-portal": "DS", "resource-code": "dsTrackQuery"}});
    return;
  }
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
    consultas_tracking: ClassVar[list[str]] = []  # guías consultadas en .../track/query
    encabezados_tracking: ClassVar[list[dict]] = []
    ocupado_proximas: ClassVar[int] = 0  # tantas consultas de tracking responden "busy"

    def do_GET(self):  # nombre fijo de http.server
        cuerpo = LOGIN_HTML if self.path.startswith("/login") else HOME_HTML.replace(
            "__MENSAJEROS__", json.dumps(MENSAJEROS_IMILE)).replace("__DEMORA__", str(DEMORA_BUSQUEDA_MS)
        ).replace("__FRONT_SEC__", json.dumps(FRONT_SEC)).replace("__HUBCODE__", json.dumps(HUBCODE))
        self._responder(cuerpo.encode(), "text/html; charset=utf-8")

    def do_POST(self):  # nombre fijo de http.server
        largo = int(self.headers.get("Content-Length", 0))
        datos = json.loads(self.rfile.read(largo) or b"{}")
        if "/unloading/submit" in self.path:
            self.descargas.append(datos)
            codigo = datos.get("scanNumber", "")
            ro = {"scanNumber": codigo, "operateType": "offloading", "scanTypeDesc": "Descarga",
                  "scanNumberType": "bag", "status": 2, "popup": False, "repeat": False, "voiceType": "success"}
            if codigo in SIN_DESCARGAR:
                DESCARGADOS[codigo] = SIN_DESCARGAR.pop(codigo)
            elif codigo in DESCARGADOS:
                ro.update(repeat=True, warnMsg="Repetido")
            else:  # como iMile real con "21" (grabación 2026-10-26)
                ro.update(scanNumberType="waybill", popup=True, blockCode=BLOQUEO_NO_EXISTE[0],
                          blockInfo=BLOQUEO_NO_EXISTE[1], voiceType="fail")
            return self._json({"status": "success", "resultObject": ro, "message": "Successful operation!"})
        if "/unloading/search" in self.path:
            filas = [{"waybillNo": w, "bagNo": b, "scanNumber": b, "scanNumberType": "bag", "scanType": "Offloading"}
                     for b, ws in DESCARGADOS.items() for w in ws]
            tam, num = int(datos.get("pageSize", 20)), int(datos.get("pageNum", 1))
            pagina = filas[(num - 1) * tam:num * tam]
            return self._json({"status": "success", "resultObject": {
                "results": pagina, "pagination": {"currentPage": num, "pageSize": tam, "totalResult": len(filas)}}})
        if "/bizAssignDaScan/submit" in self.path:
            return self._asignar(datos)
        if "/saastms/v1/base/menu/list" in self.path:
            return self._json({"status": "success", "resultObject": []})
        if "/saastms/v1/biz/track/query" in self.path:
            guia = datos.get("searchValue", "")
            self.consultas_tracking.append(guia)
            self.encabezados_tracking.append({k.lower(): v for k, v in self.headers.items()})
            if _FakeImile.ocupado_proximas > 0:
                _FakeImile.ocupado_proximas -= 1
                return self._json({"status": "fail", "resultCode": "", "message": OCUPADO})
            if self.headers.get("resource-code") != "dsTrackQuery" or self.headers.get("front-sec") != FRONT_SEC:
                return self._json({"status": "fail", "resultCode": "", "message": NO_AUTORIZADO})
            eventos = TRACKING.get(guia, [])
            return self._json({"status": "success", "resultCode": "", "message": "Successful operation!",
                               "resultObject": {"baseInfo": {"waybillNo": guia} if eventos else None,
                                                "trackInfo": {guia: eventos} if eventos else {}}})
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
