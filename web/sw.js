// Service worker do Parallax: guarda a casca das telas para o app abrir sem sinal no campo.
// A API nunca vem do cache; a foto sem sinal espera na fila (IndexedDB) e sai quando o sinal volta.
const CACHE = "parallax-casca-v1";
const CASCA = ["/", "/web/app.js", "/web/style.css", "/web/fontes-inter/inter.css",
  "/web/fontes-inter/Inter-latin-6ab57b.woff2", "/web/fontes-inter/Inter-latin-ext-b6db4a.woff2"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((nomes) => Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        const copia = r.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copia));
        return r;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});
