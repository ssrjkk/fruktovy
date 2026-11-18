/* Тема ставится до первой отрисовки: этот файл грузится синхронно в <head>,
   чтобы атрибут на <html> встал раньше, чем браузер покрасит body. Инлайн-скрипт
   недоступен — CSP разрешает только 'self'. */
(function () {
  var KEY = "fd.theme.v1";
  var val = "parchment";
  try {
    var raw = localStorage.getItem(KEY);
    var saved = raw;
    if (raw && raw.charAt(0) === '"') saved = JSON.parse(raw);
    if (saved === "market" || saved === "parchment") val = saved;
  } catch (e) { }
  document.documentElement.setAttribute("data-theme", val);
})();
