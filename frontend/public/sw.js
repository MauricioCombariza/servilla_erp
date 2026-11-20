/*
 * Service worker: que la app abra sin señal (bodega con internet inestable).
 * - Páginas: primero la red (máx. 4 s); si no hay, la última copia guardada de la app.
 * - /assets/*: llevan hash en el nombre, no cambian. Con señal los baja el navegador (no
 *   se interceptan, por Safari 27) y se guarda una copia; sin señal se sirve la copia.
 * - /api/*: nunca se tocan (lo que se hace sin señal lo guarda la cola del celular).
 */
const CACHE = "servilla-app-v1"; // mismo nombre: conserva lo ya guardado en los celulares
const ESPERA_RED_MS = 4000;
// Pestañas cuya página salió de la copia guardada (no había red): sus archivos también
const sinSenal = new Set();

self.addEventListener("install", () => self.skipWaiting());

// iPhone/iPad: este service worker no debe quedar instalado (Safari 27, ver index.html).
const ES_IOS = /iPhone|iPad|iPod/.test(self.navigator.userAgent);

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((nombres) => Promise.all(nombres.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => (ES_IOS ? self.registration.unregister() : self.clients.claim())),
  );
});

function conLimite(promesa, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("tiempo")), ms);
    promesa.then((r) => { clearTimeout(t); resolve(r); }, (e) => { clearTimeout(t); reject(e); });
  });
}

self.addEventListener("fetch", (event) => {
  if (ES_IOS) return;
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate") {
    event.respondWith(
      conLimite(fetch(req), ESPERA_RED_MS)
        .then((r) => {
          const copia = r.clone();
          caches.open(CACHE).then((c) => c.put("/", copia));
          return r;
        })
        .catch(() => {
          if (event.resultingClientId) sinSenal.add(event.resultingClientId);
          return caches.match("/").then((r) => r || Response.error());
        }),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    // Si la página llegó por la red NO se intercepta: Safari 27 (iOS 27.2) no carga un
    // script de módulo que pase por respondWith (falla sin detalle y la app queda en
    // blanco; WebKit 322883). El navegador lo baja solo (cabecera immutable) y aquí se
    // guarda una copia aparte. Si la página salió de la copia (sin red), sus archivos
    // también salen de la copia.
    const offline = sinSenal.has(event.clientId) || self.navigator.onLine === false;
    if (!offline) {
      event.waitUntil(
        caches.open(CACHE)
          .then((c) => c.match(url.pathname).then((guardada) => guardada || c.add(url.pathname)))
          .catch(() => {}),
      );
      return;
    }
    event.respondWith(caches.match(url.pathname).then((guardada) => guardada || fetch(req)));
  }
});
