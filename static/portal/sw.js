// Service worker del portal.
//
// Guarda solo la cáscara (estilos e íconos) para que la aplicación abra con
// internet intermitente. Los datos NO se cachean a propósito: un horario o una
// licencia desactualizados serían peores que un mensaje de "sin conexión".

const CACHE = "sge-portal-v1";
const ARCHIVOS = ["/static/css/sge.css", "/static/css/portal.css", "/static/portal/icono.svg"];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ARCHIVOS)));
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((claves) =>
      Promise.all(claves.filter((clave) => clave !== CACHE).map((clave) => caches.delete(clave)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  const esEstatico = evento.request.method === "GET" && url.pathname.startsWith("/static/");
  if (!esEstatico) return;

  evento.respondWith(
    caches.match(evento.request).then((guardado) => guardado || fetch(evento.request))
  );
});
