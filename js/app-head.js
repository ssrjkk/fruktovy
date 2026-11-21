/* Этот скрипт исполняется синхронно в <head>, до первой отрисовки: он ставит
   сохранённые палитру и режим карточек, чтобы страница не вспыхивала базовой темой,
   и заодно объявляет запасную картинку — фото с Pexels может не прийти. */
(function () {
  try {
    var savedTheme = localStorage.getItem('fd.theme');
    document.documentElement.dataset.theme = (savedTheme && /^(market|light|fig|emerald|night)$/.test(savedTheme)) ? savedTheme : 'market';

    var savedCards = localStorage.getItem('fd.cardMode');
    if (savedCards === '2d' || savedCards === '3d') {
      document.documentElement.dataset.cards = savedCards;
    } else {
      var prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      var isCoarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
      document.documentElement.dataset.cards = (prefersReduced || isCoarse) ? '2d' : '3d';
    }
  } catch (e) {
    document.documentElement.dataset.theme = 'market';
    document.documentElement.dataset.cards = '2d';
  }

  /* Деревянный лоток вместо пустоты: цвет и подпись берутся из data-fb-* самой картинки. */
  window.__fdImgFallback = function (img, color, label) {
    if (!img || img.dataset.fbApplied === '1') return;
    img.dataset.fbApplied = '1';
    img.onerror = null;
    var bg = (typeof color === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(color)) ? color : '#8C5E3C';
    var rawText = (label || img.alt || 'Фруктовый дворец').toString().slice(0, 32);
    var safeText = rawText.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 480" width="640" height="480">' +
      '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0%" stop-color="' + bg + '"/>' +
      '<stop offset="100%" stop-color="#1D2622"/>' +
      '</linearGradient></defs>' +
      '<rect width="640" height="480" fill="url(#g)"/>' +
      '<circle cx="320" cy="196" r="80" fill="rgba(250,245,236,0.14)"/>' +
      '<path d="M320 134c28 16 44 46 38 78-28-6-52-28-56-58 6-8 12-15 18-20z" fill="rgba(250,245,236,0.9)"/>' +
      '<path d="M318 216c-22-12-44-4-56 14 22 10 46 8 60-6" fill="rgba(212,155,42,0.88)"/>' +
      '<text x="320" y="328" text-anchor="middle" fill="#FAF5EC" font-family="Georgia,serif" font-size="34" font-weight="600">' + safeText + '</text>' +
      '<text x="320" y="366" text-anchor="middle" fill="rgba(250,245,236,0.72)" font-family="sans-serif" font-size="13" letter-spacing="3">ФРУКТОВЫЙ ДВОРЕЦ · СПБ</text>' +
      '</svg>';
    img.src = 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };
})();

window.FD_IMG_FALLBACK_BOUND = true;

/* Событие error не всплывает, поэтому слушатель идёт на capture: один на все картинки,
   включая те, что появятся позже из шаблонов app.js. */
document.addEventListener('error', function (e) {
  var img = e.target;
  if (!img || img.tagName !== 'IMG' || img.onerror || !img.dataset.fbColor) return;
  window.__fdImgFallback(img, img.getAttribute('data-fb-color') || '#1B4D3E', img.getAttribute('data-fb-label') || '');
}, true);
