/* Sukoon — app-shell cache for offline access to the patient app.
   Strategy: cache-first for the shell (HTML/CSS/JS), network-first for API
   calls (falls through to the offline queue handled in offline.js when the
   network is unavailable — this worker does not intercept /api/*). */

const CACHE_NAME = "sukoon-shell-v1";
const SHELL_FILES = [
  "/",
  "/app/patient/index.html",
  "/app/css/base.css",
  "/app/css/patient.css",
  "/app/js/api.js",
  "/app/js/i18n.js",
  "/app/js/offline.js",
  "/app/js/util.js",
  "/app/js/patient.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) return; // never intercept API calls

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
          return res;
        })
        .catch(() => cached);
    })
  );
});
