/* Офлайн-кэш. Версию проставляет сборка на каждом деплое — вручную менять не нужно. */
var VERSION = "fd-20261117-203519";
var CORE = ["./", "./index.html", "./404.html", "./css/style.css", "./css/themes.css", "./assets/fonts.css",
  "./js/data.js", "./js/main.js", "./js/theme.js", "./assets/logo.svg", "./manifest.webmanifest",
  "./assets/icon-192.png", "./assets/icon-512.png",
  "./vendor/swiper-bundle.min.css", "./vendor/swiper-bundle.min.js",
  "./vendor/lenis.min.js", "./vendor/gsap.min.js", "./vendor/ScrollTrigger.min.js"];
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