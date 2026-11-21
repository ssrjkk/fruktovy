/* Офлайн-кэш оболочки витрины. Список CORE и версию проставляет tools/build.py —
   руками их не менять: иначе кэш разойдётся с реальным набором файлов.
   Стратегия: cache-first для оболочки, сеть для свежего, фото добираются по ходу. */
var VERSION = "fd-20261121-005025";
var CORE = ["./", "./index.html", "./404.html", "./css/style.css", "./assets/fonts.css", "./js/app-head.js", "./js/data.js", "./js/app.js", "./assets/logo.svg", "./manifest.webmanifest", "./assets/icon-192.png", "./assets/icon-512.png"];
self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(VERSION).then(function (c) { return c.addAll(CORE); }).then(function () { return self.skipWaiting(); }));
});
self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== VERSION; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});
self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET" || new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(caches.match(e.request).then(function (hit) {
    var net = fetch(e.request).then(function (res) {
      if (res.ok) { var copy = res.clone(); caches.open(VERSION).then(function (c) { c.put(e.request, copy); }); }
      return res;
    }).catch(function () { return hit || caches.match("./index.html"); });
    return hit || net;
  }));
});
