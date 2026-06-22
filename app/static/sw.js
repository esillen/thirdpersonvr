const CACHE_NAME = "third-person-view-headset-v1";
const APP_SHELL = ["/headset", "/static/headset.css", "/static/headset.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((key) => (key === CACHE_NAME ? Promise.resolve() : caches.delete(key))))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/headset")));
    return;
  }
  if (request.url.includes("/api/active-camera/preview.mjpg")) {
    event.respondWith(fetch(request));
    return;
  }
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});
