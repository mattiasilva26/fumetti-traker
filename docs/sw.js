// Service worker minimale: rende la PWA installabile e apribile offline.
// Strategia: network-first per data.json (vogliamo i dati freschi),
// cache-first per il guscio (html/icone).
const CACHE = "fumetti-v2";
const SHELL = ["./", "./index.html", "./manifest.json", "./icon.svg"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("data.json")) {
    const cacheKey = new Request(new URL("data.json", self.registration.scope));
    e.respondWith(
      fetch(e.request).then(r => {
        const copy = r.clone();
        caches.open(CACHE).then(c => c.put(cacheKey, copy));
        return r;
      }).catch(() => caches.match(cacheKey))
    );
  } else {
    // cache-first
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
