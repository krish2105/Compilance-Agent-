// Minimal app-shell service worker: cache-first for static assets, network-first
// for navigations (so a deploy is picked up), offline fallback to the cached shell.
const CACHE = "ca-shell-v1";
const SHELL = ["/", "/index.html", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Never cache API calls — always hit the network.
  if (url.pathname.startsWith("/api") || url.hostname.includes("onrender.com")) return;

  if (req.mode === "navigate") {
    // Network-first for pages so new deploys show up; fall back to the shell offline.
    e.respondWith(fetch(req).catch(() => caches.match("/index.html")));
    return;
  }
  // Cache-first for hashed static assets.
  e.respondWith(
    caches.match(req).then((hit) =>
      hit ||
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
        return res;
      }).catch(() => hit),
    ),
  );
});
