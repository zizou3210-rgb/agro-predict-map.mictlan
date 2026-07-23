const CACHE_NAME = "ea-geo-app-v56";
const APP_SHELL = [
  "./",
  "./index.html",
  "./styles.css",
  "./manifest.webmanifest",
  "./src/main.js",
  "./src/selectColumnClassifier.js",
  "./src/launcher.js",
  "./data/world.geojson",
  "./icons/icon-app.svg",
  "./icons/icon-maskable.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      ),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  const isSameOrigin = url.origin === self.location.origin;
  const isApiRequest = isSameOrigin && url.pathname.startsWith("/api/");
  const isHtmlRequest =
    request.mode === "navigate"
    || url.pathname === "/"
    || url.pathname.endsWith("/index.html")
    || request.headers.get("accept")?.includes("text/html");
  const isRuntimeSourceRequest =
    url.pathname.startsWith("/src/")
    || url.pathname.endsWith("/service-worker.js")
    || url.pathname.endsWith("/styles.css");

  if (!isSameOrigin) {
    event.respondWith(fetch(request).catch(() => caches.match(request)));
    return;
  }

  if (isApiRequest) {
    event.respondWith(fetch(request));
    return;
  }

  if (isHtmlRequest || isRuntimeSourceRequest) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const cloned = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, cloned));
          }
          return response;
        })
        .catch(() => caches.match(request)),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response.ok) {
            const cloned = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, cloned));
          }
          return response;
        })
        .catch(() => cached);

      return cached || networkFetch;
    }),
  );
});
