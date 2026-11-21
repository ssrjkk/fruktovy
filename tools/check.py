#!/usr/bin/env python3
"""Гейт качества витрины «Фруктовый дворец» перед деплоем.

Проверяет то, что браузер промолчит: разъехавшийся контракт JS ↔ DOM, отсутствующий
файл сборки, палитру без токена, безымянную кнопку, выдуманную оплату в тексте.
Пиксели (контраст, тап-цели, фокус) меряются прогоном в headless Chrome; здесь —
статическая часть контракта. Работает и по читаемым исходникам, и по минифицированным
после tools/build.py, поэтому порядок в CI «сборка → тесты → гейт» не слепнет.

Запуск: python tools/check.py [--skip-assets]
"""
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import quickjs

ROOT = Path(__file__).resolve().parent.parent
SKIP = "--skip-assets" in sys.argv
ERR, NOTES = [], []
SITE_URL = "https://ssrjkk.github.io/fruktovy/"
BRAND = "Фруктовый дворец"

VOID = {"meta", "link", "img", "br", "hr", "input", "source", "path", "circle", "rect", "ellipse",
        "line", "stop", "use", "polyline", "polygon", "area", "base", "col", "embed", "track", "wbr"}
GENERIC_FONTS = {"Georgia", "Times New Roman", "-apple-system", "BlinkMacSystemFont", "Segoe UI",
                 "Roboto", "sans-serif", "serif", "monospace", "system-ui", "Apple Color Emoji"}
# Хосты, которым разрешено торчать в исходниках. schema.org и w3.org — пространства имён
# (JSON-LD и SVG), а не запросы наружу; t.me и tel: — каналы связи магазина (единственные:
# заявка уходит в Telegram-чат лавки); yandex.ru — единственный iframe: виджет рейтинга,
# он же единственный источник отзывов.
ALLOWED_HOSTS = {"ssrjkk.github.io", "t.me", "yandex.ru", "yandex.com", "schema.org", "www.w3.org"}


class Doc(HTMLParser):
    """Собирает из разметки всё, с чем сверяются гейты: теги, id, имена контролов."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.err, self.tags = [], [], []
        self.ids, self.classes, self.symbols, self.uses = [], set(), set(), set()
        self.text_bits = []
        self.controls = []          # [{tag, attrs, text, line, label_of}]
        self._raw = 0               # глубина <script>/<style>: их текст посетитель не читает
        self._open = []             # стеки открытых контролов для сбора их текста

    def handle_starttag(self, tag, attrs):
        d = {k: ("" if v is None else v) for k, v in attrs}
        self.tags.append((tag, d, self.getpos()[0]))
        if "id" in d:
            self.ids.append(d["id"])
        for c in d.get("class", "").split():
            self.classes.add(c)
        if tag == "symbol" and "id" in d:
            self.symbols.add(d["id"])
        if tag == "use" and d.get("href", "").startswith("#"):
            self.uses.add(d["href"][1:])
        if tag in ("button", "a", "label", "summary") and tag not in VOID:
            self._open.append({"tag": tag, "attrs": d, "line": self.getpos()[0], "text": []})
        if tag in ("script", "style"):
            self._raw += 1
        if tag not in VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()
        if self._open and self._open[-1]["tag"] == tag:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._raw = max(0, self._raw - 1)
        if tag in VOID:
            return
        if self._open and self._open[-1]["tag"] == tag:
            self._flush()
        elif self._open and any(o["tag"] == tag for o in self._open):
            while self._open and self._open[-1]["tag"] != tag:
                self._flush()
            self._flush()
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.err.append("не закрыт <%s>" % self.stack.pop())
            self.stack.pop()
        else:
            self.err.append("лишний </%s>" % tag)

    def _flush(self):
        if self._open:
            o = self._open.pop()
            txt = re.sub(r"\s+", " ", " ".join(o["text"])).strip()
            self.controls.append({"tag": o["tag"], "attrs": o["attrs"], "line": o["line"], "text": txt})

    def handle_data(self, data):
        if self._raw:
            return
        t = data.strip()
        if t:
            self.text_bits.append(t)
            for o in self._open:
                o["text"].append(t)

    def feed_file(self, path):
        self.feed(path.read_text(encoding="utf-8"))
        while self._open:
            self._flush()
        if self.stack:
            self.err.append("висящие теги: " + ", ".join(self.stack))
        return self


def attr_of(doc, tag, name):
    return [d[name] for t, d, _ in doc.tags if t == tag and name in d]


def metas(doc, key):
    return [d["content"] for t, d, _ in doc.tags if t == "meta" and (d.get("name") or d.get("property")) == key]


def media_block(text, cond):
    """Тело @media <cond> { … } через счётчик скобок: минификатор снимает пробелы после @media и вокруг «:», поэтому условие собирается в шаблон токен за токеном."""
    tokens = re.findall(r"\(|\)|[A-Za-z-]+:|[A-Za-z0-9.-]+", cond)
    pat = r"@media\s*" + r"\s*".join(re.escape(t) for t in tokens)
    for m in re.finditer(pat + r"\s*\{", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        return text[m.end():i - 1]
    return None


def squash(text):
    """CSS без пробелов вокруг : ; { } , — чтобы сверять префиксы в любом виде."""
    return re.sub(r"\s*([:;,{}])\s*", r"\1", text)


# ---------------------------------------------------------------- sources ----
index_path = ROOT / "index.html"
doc = Doc().feed_file(index_path)
html = index_path.read_text(encoding="utf-8")
plain = re.sub(r"\s+", " ", " ".join(doc.text_bits))
css_path = ROOT / "css" / "style.css"
css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
JS_FILES = ["js/app-head.js", "js/data.js", "js/app.js"]
js = "\n".join((ROOT / f).read_text(encoding="utf-8") for f in JS_FILES if (ROOT / f).exists())
app_js = (ROOT / "js" / "app.js").read_text(encoding="utf-8")
head_js = (ROOT / "js" / "app-head.js").read_text(encoding="utf-8")
data_js = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
DEFAULT_THEME = (re.search(r'<html lang="([a-z]+)"[^>]*data-theme="([a-z]+)"', html) or [None, None, "market"])[2]

for p in (index_path, css_path) + tuple(ROOT / f for f in JS_FILES):
    if not p.exists():
        ERR.append(f"нет исходника {p.relative_to(ROOT).as_posix()}")
    elif not p.read_text(encoding="utf-8").strip():
        ERR.append(f"пустой исходник {p.relative_to(ROOT).as_posix()}")
if not js or not css:
    print("FAIL:")
    for e in ERR:
        print(" -", e)
    sys.exit(1)

# ============================================================ 1. РАЗМЕТКА ====
if doc.err:
    ERR.append("index.html: " + "; ".join(doc.err[:6]))
dupes = sorted({i for i in doc.ids if doc.ids.count(i) > 1})
if dupes:
    ERR.append("дубли id в index.html: " + ", ".join(dupes[:8]))
d404 = Doc().feed_file(ROOT / "404.html")
if d404.err:
    ERR.append("404.html: " + "; ".join(d404.err[:6]))
for t, dd, line in d404.tags:
    if t in ("link", "script"):
        target = dd.get("href") or dd.get("src") or ""
        if target.startswith(("css/", "js/", "assets/", "manifest")) and not (ROOT / target).exists() and not SKIP:
            ERR.append(f"404.html: нет файла {target}")
    if t == "use":
        ERR.append("404.html: <use> на спрайт из index.html — в другом документе он пустой")

img_tags = [(d, line) for t, d, line in doc.tags if t == "img"]
imgs = [d for d, _ in img_tags]
# «ниже каталога» считаем по строке разметки: поиск подстроки в html нашёл бы first-вхождение,
# а оно всегда живёт в <head> (preload) или в hero.
cat_line = next((line for t, d, line in doc.tags if d.get("id") == "catalog"), 10 ** 9)
if not imgs:
    ERR.append("index.html: ни одной картинки — гейт слепой")
# src у картинок модалки и лайтбокса подставляет JS по открытию: в разметке его нет по замыслу
js_managed_src = set()
for m in re.finditer(r"""(?:getElementById\(\s*['"]|querySelector\(\s*['"]#|\$\(\s*['"]#)([\w-]+)['"]""", js):
    if re.search(r"\.src\s*=", js[m.end():m.end() + 300]):
        js_managed_src.add(m.group(1))
for i, a in enumerate(imgs):
    for r in ("alt", "width", "height", "src"):
        if r not in a and not (r == "src" and a.get("id") in js_managed_src):
            ERR.append(f"img#{i} ({a.get('src', '?')[:44]}) без {r}")
    if a.get("loading") not in (None, "lazy", "eager"):
        ERR.append(f"img#{i}: loading={a['loading']}")
    src = a.get("src", "")
    if src.startswith(("http://", "//")):
        ERR.append(f"img#{i}: картинка грузится не с нашего домена ({src[:50]})")
    elif src.startswith("./assets/img/") and not (ROOT / src.lstrip("./")).exists() and not SKIP:
        ERR.append(f"img#{i}: нет файла {src}")
# жадная загрузка только до каталога: всё, что ниже, обязано быть ленивым
for i, (a, line) in enumerate(img_tags):
    if line > cat_line and a.get("loading") != "lazy":
        ERR.append(f"img#{i} ниже каталога без loading=lazy — телефон тянет весь прилавок")

# доступные имена контролов
for c in doc.controls:
    d, line = c["attrs"], c["line"]
    if c["tag"] == "button":
        named = d.get("aria-label") or d.get("aria-labelledby") or c["text"]
        if not named:
            ERR.append(f"кнопка@{line} без текста и без aria-label: class=\"{d.get('class', '')}\"")

for t, dd, line in doc.tags:
    if t in ("input", "select", "textarea") and dd.get("type") not in ("hidden", "submit", "button", "reset"):
        pid = dd.get("id", "")
        wrapped = pid and re.search(r"<label[^>]*>(?:(?!</label>)[\s\S])*?<" + t + r"\b[^>]*id=\"" + re.escape(pid), html)
        labelled = bool(dd.get("aria-label") or dd.get("aria-labelledby") or (pid and f'for="{pid}"' in html) or wrapped)
        if not labelled:
            ERR.append(f"<{t} id=\"{pid or '?'}\">@{line}: у поля нет доступного имени "
                       "(aria-label, aria-labelledby, <label for> или обёртка <label>)")

for t, dd, line in doc.tags:
    if t == "iframe":
        if not dd.get("title"):
            ERR.append(f"iframe@{line} без title — скринридер читает пустоту")
        if not dd.get("src", "").startswith("https://yandex.ru/"):
            ERR.append(f"iframe@{line}: источник вне белого списка: {dd.get('src', '')[:60]}")
    if dd.get("href", "").startswith("javascript:"):
        ERR.append(f"<{t}>@{line}: javascript:-ссылка")
    if t == "a" and dd.get("target", "_self") == "_blank" and "noopener" not in (dd.get("rel") or ""):
        ERR.append(f"<a href=\"{dd.get('href', '')[:40]}\">@{line}: target=_blank без rel\"noopener\"")

known_ids = set(doc.ids)
for t, dd, line in doc.tags:
    v = dd.get("href", "")
    if v.startswith("#") and len(v) > 1 and v[1:] not in known_ids:
        ERR.append(f"<{t} href=\"{v}\">@{line}: якоря нет в разметке")
    for key in ("aria-labelledby", "aria-describedby", "aria-controls", "for"):
        for ref in (dd.get(key) or "").split():
            if ref not in known_ids:
                ERR.append(f"<{t} {key}=\"{ref}\">@{line}: несуществующий id")

# часть иконок рисуют шаблоны из app.js (избранное, стрелки) — в разметке их нет
js_uses = set(re.findall(r'<use\s+href="#([\w-]+)"', app_js))
missing_syms = sorted((doc.uses | js_uses) - doc.symbols)
unused_syms = sorted(doc.symbols - (doc.uses | js_uses))
if missing_syms:
    ERR.append("спрайт: <use> ссылается на несуществующий символ: " + ", ".join(missing_syms))
if unused_syms:
    ERR.append("спрайт: символы не используются (мёртвый вес): " + ", ".join(unused_syms))
if len(doc.symbols) < 4:
    ERR.append("спрайт пуст — иконки рисуем не чем")
if not any('aria-live' in str(d) for t, d, _ in doc.tags):
    ERR.append("нет ни одной aria-live-зоны: тосты и счётчик пакета неозвучимы")

h1 = [t for t, d, _ in doc.tags if t == "h1"]
if len(h1) != 1:
    ERR.append(f"на странице {len(h1)} заголовков h1 (нужен ровно один)")

# ============================================================== 2. HEAD =====
def need(pattern, what):
    if not re.search(pattern, html):
        ERR.append("head: нет " + what)


need(r'<meta charset="UTF-8"', "charset")
need(r'name="viewport" content="width=device-width', "viewport")
need(r'name="description" content="[^"]{60,400}"', "description (60–400 знаков)")
need(r'name="robots" content="index, follow"', "robots")
need(r'rel="canonical" href="' + re.escape(SITE_URL) + '"', "canonical на " + SITE_URL)
need(r'property="og:image" content="' + re.escape(SITE_URL) + r'assets/og\.png"', "абсолютный og:image")
need(r'name="twitter:card" content="summary_large_image"', "twitter:card")
need(r'rel="manifest" href="manifest\.webmanifest"', "ссылка на манифест")
need(r'rel="apple-touch-icon" href="assets/icon-192\.png"', "apple-touch-icon")
need(r'rel="preload" as="image" href="\./assets/img/[^"]+" fetchpriority="high"', "preload LCP-картинки")
need(r'rel="stylesheet" href="assets/fonts\.css"', "assets/fonts.css")
need(r'rel="stylesheet" href="css/style\.css"', "css/style.css")
title = re.search(r"<title>(.*?)</title>", html)
if not title or BRAND not in title.group(1):
    ERR.append("head: в <title> нет названия магазина")
elif len(title.group(1)) > 78:
    NOTES.append(f"head: <title> {len(title.group(1))} знаков — в выдаче обрежут")
for prop in ("og:type", "og:locale", "og:site_name", "og:title", "og:description", "og:url"):
    if prop not in html:
        ERR.append(f"head: нет {prop}")
if BRAND not in " ".join(metas(doc, "og:site_name")):
    ERR.append("og:site_name не совпадает с названием магазина")
for v in metas(doc, "og:url") + metas(doc, "og:image"):
    if not v.startswith(SITE_URL):
        ERR.append(f"og-ссылка не абсолютная на {SITE_URL}: {v}")
preload = re.search(r'rel="preload" as="image" href="([^"]+)"', html)
hot = [(a, line) for a, line in img_tags if a.get("fetchpriority") == "high"]
if preload:
    if len(hot) != 1:
        ERR.append(f"прелоад LCP: картинок с fetchpriority=\"high\" — {len(hot)}, а должна быть одна")
    elif not hot[0][0].get("src", "").endswith(preload.group(1).split("/")[-1]):
        ERR.append(f"прелоад {preload.group(1)} ≠ картинка с fetchpriority=high ({hot[0][0].get('src', '')})")
    elif hot[0][1] > cat_line:
        ERR.append("прелоад тащит картинку ниже каталога — это не LCP, а трафик впустую")

# ============================================================== 3. CSP ======
csp_tag = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', html)
if not csp_tag:
    ERR.append("CSP: нет meta-политики")
else:
    directives = {}
    for chunk in csp_tag.group(1).split(";"):
        bits = chunk.strip().split()
        if bits:
            directives[bits[0]] = bits[1:]
    for d_name in ("default-src", "script-src", "style-src", "img-src", "font-src", "connect-src",
                   "object-src", "base-uri", "form-action"):
        if d_name not in directives:
            ERR.append(f"CSP: нет директивы {d_name}")
    if directives.get("script-src") != ["'self'"]:
        ERR.append("CSP: script-src должен быть ровно 'self' — скрипты обязаны лежать у нас")
    if directives.get("object-src") != ["'none'"]:
        ERR.append("CSP: object-src должен быть 'none'")
    if directives.get("base-uri") != ["'self'"]:
        ERR.append("CSP: base-uri должен быть 'self'")
    if directives.get("form-action") != ["'self'"]:
        ERR.append("CSP: form-action должен быть 'self' — формы у нас никуда не отправляются")
    if "'unsafe-eval'" in directives.get("script-src", []) or "'unsafe-inline'" in directives.get("script-src", []):
        ERR.append("CSP: script-src разрешает лишнее")
    for bad in ("img-src", "font-src", "connect-src"):
        if any(v.startswith("http") for v in directives.get(bad, [])):
            ERR.append(f"CSP: {bad} отворён наружу")
    if any(not v.startswith("https://yandex.ru") for v in directives.get("frame-src", [])):
        ERR.append("CSP: frame-src пущен не только в yandex.ru")

for tag_open, body in re.findall(r"(<script[^>]*>)(.*?)</script>", html, re.S):
    if "src=" in tag_open or "application/ld+json" in tag_open:
        continue
    if body.strip():
        ERR.append("CSP: inline-скрипт с кодом в разметке — политика его заблокирует")
if len(re.findall(r'<script src="js/', html)) != 3:
    ERR.append("ожидались три <script src=js/…>: app-head, data, app")
if not re.search(r'<script src="js/app-head\.js"></script>', html):
    ERR.append("js/app-head.js должен грузиться синхронно и без defer — иначе видна вспышка базовой темы")
if re.search(r'<script[^>]*src="js/(data|app)\.js"[^>]*>', html):
    for tag in re.findall(r'<script[^>]*src="js/(?:data|app)\.js"[^>]*>', html):
        if "defer" not in tag:
            ERR.append(f"{tag}: каталог и логика обязаны идти с defer — они читают DOM")
if re.search(r"\son[a-z]+\s*=", html):
    ERR.append("inline-обработчик on*= в разметке (CSP его режет, а браузер молчит)")
if re.search(r"""["']on(?:click|error|load|input|change|submit)["']\s*:""", app_js):
    ERR.append("inline-обработчик on*= генерируется из JS")
if re.search(r"""\son(?:click|error|load|input|change|submit)\s*=\s*["']""", app_js):
    ERR.append("JS подвешает on*-атрибут строкой: под жёсткой CSP он мёртвый код, обработчик вешают "
               "через addEventListener, а цвет фолбэка — из data-fb-*")
for pat, why in ((r"\beval\s*\(", "eval"), (r"new\s+Function\s*\(", "new Function"),
                 (r"document\.write\s*\(", "document.write")):
    if re.search(pat, js):
        ERR.append(f"JS: {why} — под жёсткой CSP это либо смерть, либо дыра")
for m in re.finditer(r"innerHTML\s*=\s*([^;]{0,220})", js):
    if re.search(r"location\.|URLSearchParams|decodeURIComponent|\.hash\b|\.search\b", m.group(1)):
        ERR.append("JS подставляет в innerHTML данные из адреса страницы: чужая ссылка подшьёт разметку")

# ======================================================= 4. ХОСТЫ И ССЫЛКИ ====
for src_name, text in (("index.html", html), ("css/style.css", css), ("js", js)):
    for host in sorted(set(re.findall(r"https?://([A-Za-z0-9.-]+)", text)) - ALLOWED_HOSTS):
        ERR.append(f"{src_name}: хост не в белом списке: {host}")
for u in re.findall(r"""["']((?:https?:)?//[^"']+|/[^"'\s]*\.(?:js|css|png|jpe?g|svg|webp|woff2))["']""", js):
    host = re.sub(r"^https?:", "", u).lstrip("/").split("/")[0]
    if u.startswith(("http://", "//")) and host not in ALLOWED_HOSTS:
        ERR.append(f"js: ссылка не на https по нашему пути: {u[:60]}")

# ============================================ 5. КОНТРАКТ JS ↔ DOM ↔ ДАННЫЕ ====
js_ids = set(re.findall(r"""getElementById\(\s*['"]([\w-]+)""", js))
js_ids |= set(re.findall(r"""\$\(\s*['"]#([\w-]+)""", js))
js_ids |= set(re.findall(r"""querySelector(?:All)?\(\s*['"]#([\w-]+)""", js))
dead_ids = sorted(i for i in js_ids if i not in known_ids)
if dead_ids:
    ERR.append("JS обращается к id, которых нет в разметке: " + ", ".join(dead_ids[:8]))
if len(js_ids) < 15:
    ERR.append(f"JS трогает лишь {len(js_ids)} id — разбор кода слепой, гейт ничего не проверяет")
# динамические in-page ссылки из JS (хэш пакета, якоря каталога)
dyn_ids = set(re.findall(r'id="([\w-]+)"', app_js)) | set(re.findall(r"""id='([\w-]+)'""", app_js))
for h in set(re.findall(r"""["']#([\w-]+)["']""", app_js)):
    if h not in known_ids and h not in dyn_ids and h not in {"cart"} and len(h) > 2 and not h.startswith("i-"):
        NOTES.append(f"js ссылается на #{h}, такого id нет ни в разметке, ни в его шаблонах")
# Атрибуты, которые JS вычитывает из DOM: они обязаны существовать — либо в разметке,
# либо в шаблонах, которые сам JS и печатает. Селекторы вида [data-x] выкидываем, иначе
# запрос сам себе доказывал бы, что атрибут есть.
tpl_text = re.sub(r"\[[^\]]*?\bdata-[a-z-]+[^\]]*?\]", " ", js)
declared_attrs = set(re.findall(r"\b(data-[a-z-]+)", html)) | set(re.findall(r"\b(data-[a-z-]+)", tpl_text))
for camel in set(re.findall(r"dataset\.([A-Za-z][A-Za-z0-9]*)\s*=(?!=)", js)):
    declared_attrs.add("data-" + re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), camel))
queried = set(re.findall(r"""(?:querySelector(?:All)?|closest)\(\s*['"][^'"]*?\[(data-[a-z-]+)""", app_js))
queried |= {"data-" + re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), c)
            for c in set(re.findall(r"\.dataset\.([A-Za-z][A-Za-z0-9]*)", app_js))}
for a in sorted(queried - declared_attrs):
    ERR.append(f"JS читает [{a}], которого нет ни в разметке, ни в его шаблонах")

keys_block = re.search(r"const KEYS\s*=\s*\{([^}]*)\}", data_js)
if not keys_block:
    ERR.append("data.js: нет таблицы KEYS")
else:
    declared = dict(re.findall(r"(\w+):\s*['\"]([^'\"]+)['\"]", keys_block.group(1)))
    used_props = set(re.findall(r"KEYS\.(\w+)", js))
    if not used_props <= set(declared):
        ERR.append("JS читает KEYS, которых нет в таблице: " + ", ".join(sorted(used_props - set(declared))))
    if not {"cart", "orders", "favs"} <= set(declared) or not {"cart", "orders", "favs"} <= used_props:
        ERR.append("KEYS: пакет/заявки/избранное не сохранятся — всё живёт до перезагрузки")
    for key in declared.values():
        if not re.fullmatch(r"fd\.[a-zA-Z]+(\.v\d+)?", key):
            ERR.append(f"ключ localStorage {key!r} вне неймспейса fd.* — можно столкнуться с другим сайтом")
    if re.search(r"localStorage\.(get|set|remove)Item\(\s*['\"](?!fd\.)", js):
        ERR.append("localStorage трогается мимо KEYS")

# ============================================================== 6. ДАННЫЕ ====
ctx = quickjs.Context()
data = json.loads(ctx.eval(data_js + "\n;JSON.stringify({P: PRODUCTS, G: GALLERY_ITEMS, D: DAILY_HITS,"
                                 " A: AISLES, PR: PROMOS, T: THEME_LABELS, M: MONTHS, CM: CURRENT_MONTH})"))
PRODUCTS, GALLERY = data["P"], data["G"]
if len(PRODUCTS) < 20:
    ERR.append(f"каталог усох до {len(PRODUCTS)} позиций — гейт слепой")
ids = [p["id"] for p in PRODUCTS]
if len(ids) != len(set(ids)):
    ERR.append("в каталоге повторяющиеся id")
aisle_ids = {a["id"] for a in data["A"]}
for p in PRODUCTS:
    miss = [k for k in ("id", "name", "cat", "unit", "weightKg", "photo", "color", "season", "note")
            if p.get(k) in (None, "", [])]
    if "price" not in p or "oldPrice" not in p:
        miss.append("price/oldPrice (должны быть null)")
    if p.get("price") is not None or p.get("oldPrice") is not None:
        ERR.append(f"{p['id']}: в данных появилась цена — на витрине их нет намеренно")
    if p.get("photo") and not re.fullmatch(r"\d+", str(p["photo"])):
        ERR.append(f"{p['id']}: photo должен быть числовым id Pexels")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(p.get("color", ""))):
        ERR.append(f"{p['id']}: color вне формата #RRGGBB — плейсхолдер не отрисуется")
    if p.get("cat") and p["cat"] not in aisle_ids:
        ERR.append(f"{p['id']:12} лежит в ряду {p['cat']}, которого нет в AISLES")
    if miss:
        ERR.append(f"{p['id']}: пустые поля {miss}")
for p in PRODUCTS:
    for t in p.get("together", []):
        if t not in ids:
            ERR.append(f"«часто берут вместе» у {p['id']} ссылается на снятую позицию {t}")
for h in data["D"]:
    if h not in ids:
        ERR.append(f"хит дня {h} отсутствует в каталоге")
if len(data["D"]) < 3:
    ERR.append("хитов дня меньше трёх — доска «утренний завоз» пустая")
if not (1 <= int(data["CM"]) <= 12):
    ERR.append("CURRENT_MONTH вне 1..12")
if len(data["M"]) != 12:
    ERR.append("MONTHS должен содержать 12 месяцев — сезонная шкала иначе врёт")
for g in GALLERY:
    if not g.get("photo") or not g.get("caption"):
        ERR.append("галерея: кадр без фото или подписи")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(g.get("color", ""))):
        ERR.append("галерея: color вне формата #RRGGBB")
if not GALLERY:
    ERR.append("галерея пуста")
for code, promo in data["PR"].items():
    if not re.fullmatch(r"[А-ЯЁA-Z0-9]+", code):
        ERR.append(f"промокод {code!r} не в верхнем регистре — поле его не распознает")
    if not promo.get("label"):
        ERR.append(f"промокод {code}: нет человеческой расшифровки")
    if re.search(r"примен|итог|сумм", promo.get("label", ""), re.I):
        ERR.append(f"промокод {code}: обещает пересчёт суммы, которого на витрине нет")
    if re.search(r"\d+\s*%|минус\s*\d|\d+\s*₽", promo.get("label", ""), re.I):
        ERR.append(f"промокод {code}: в подписи обещана скидка цифрой, а цен на витрине нет")

# ==================================================== 7. ЧЕСТНОСТЬ ТЕКСТА ====
FORBIDDEN = [
    (r"\bСБП\b", "упоминание СБП — онлайн-оплаты у магазина нет"),
    (r"\bCVC\b|\bCVV\b", "поля платёжной карты"),
    (r"[Оо]плачен[оае]", "текст про оплату"),
    (r"[Ээ]квайринг", "эквайринг"),
    (r"[Кк]арта онлайн|оплатить картой", "приём карт онлайн"),
    (r"priceRange", "priceRange в разметке — цен нет"),
    (r"Мадина|Madina", "выдуманное лицо продавца"),
    (r"100 ?% гаранти|гарантируем качество", "гарантийное обещание"),
    (r"самые низкие цены|лучшие цены в|дешевле всех", "ценовое обещание"),
    (r"более \d+ (?:клиентов|покупателей|отзывов)", "выдуманная аудитория"),
    (r"\d+ (?:лет|года) на рынке", "выдуманный стаж"),
    (r"(?:5\.0|4\.9|5 зв)", "рейтинг, которого нет на Яндекс Картах"),
    (r"(?i:wa\.me|whatsapp)", "чужой мессенджер: у лавки один канал связи — Telegram-чат"),
    (r"(?i:viber\.com|m\.me|facebook\.com|vk\.com|instagram\.com|max\.ru|discord\.)",
     "посторонняя соцсеть: ссылки на чаты ведут в Telegram магазина"),
]
for pat, why in FORBIDDEN:
    for src_name, text in (("index.html", html), ("css/style.css", css), ("js", js)):
        if re.search(pat, text):
            ERR.append(f"{src_name}: {why}")
if re.search(r"price:\s*[0-9]", data_js):
    ERR.append("data.js: числовая цена в каталоге")
if "по запросу" not in app_js:
    ERR.append("в карточках нет заглушки «по запросу» — посетитель увидит пустоту вместо цены")
# обещания про цены и наличие: если и звучат, то только как «уточнит продавец»
for claim in ("доставка за 30", "доставим за 30", "круглосуточн"):
    if claim in plain.lower():
        NOTES.append(f"в тексте встретилось «{claim}» — сверить, что это правда")

# ============================================ 7a. КОНТАКТЫ И ЗОНА ДОСТАВКИ ====
# Витрина обещает один телефон, один чат и одну зону доставки. Всё это живёт в js/data.js:
# до этого номер и мессенджер были вписаны руками в шести местах, и правка одного из них
# молча уводила заявку в чужой чат, а страница продолжала показывать «наш» номер.
shop = re.search(r"const SHOP\s*=\s*\{([^}]*)\}", data_js)
shop_fields = dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", shop.group(1))) if shop else {}
if not shop:
    ERR.append("data.js: нет таблицы SHOP — сверять контакты не с чем")
    shop_fields = {}
SHOP_PHONE = re.sub(r"\D", "", shop_fields.get("phone", ""))
SHOP_TG = shop_fields.get("tg", "")
if not re.fullmatch(r"7\d{10}", SHOP_PHONE):
    ERR.append(f"data.js: SHOP.phone {shop_fields.get('phone')!r} не читается как +7 (XXX) XXX-XX-XX")
if not re.fullmatch(r"[A-Za-z]\w{4,31}", SHOP_TG):
    ERR.append(f"data.js: SHOP.tg {SHOP_TG!r} — не telegram-имя")

tel_links = {re.sub(r"\D", "", h) for h in re.findall(r'href="tel:([^"]+)"', html)}
if not tel_links:
    ERR.append("на витрине не осталось ни одной tel:-ссылки — позвонить гостю не предлагается")
elif tel_links != {SHOP_PHONE}:
    ERR.append("tel:-ссылки ведут не на номер из data.js: " + ", ".join(sorted(tel_links)))
shown_nums = {re.sub(r"\D", "", x) for x in re.findall(r"\+7[\d\s()\-]{9,}", plain)}
if shown_nums != {SHOP_PHONE}:
    ERR.append("видимый номер на странице расходится с data.js: "
               + (", ".join(sorted(shown_nums)) or "ни одного номера на витрине не видно"))
chat_links = {c for c in re.findall(r"https?://t\.me/([^\"'\s/$\\]+)", html + "\n" + js)}
if not chat_links:
    ERR.append("ссылок в чат магазина нет вообще — заявку отправлять некуда")
elif chat_links != {SHOP_TG}:
    ERR.append("ссылки t.me ведут не в чат из data.js: " + ", ".join(sorted(chat_links)))
if not re.search(r"t\.me/\$\{SHOP\.tg\}", data_js):
    ERR.append("data.js: ссылка чата собрана не из SHOP.tg — чат может уехать на сторону")

# Зона доставки: одна формулировка на чип, счёт, бейдж заявки и ответы чата.
zone = re.search(r"const DELIVERY_ZONE\s*=\s*'([^']+)'", data_js)
zone_short = re.search(r"const DELIVERY_ZONE_SHORT\s*=\s*'([^']+)'", data_js)
fee = re.search(r"const COURIER_FEE\s*=\s*(\d+)", data_js)
if not zone or not zone_short:
    ERR.append("data.js: нет DELIVERY_ZONE — каждая надпись про доставку называет зону сама")
else:
    ZONE, ZONE_SHORT = zone.group(1), zone_short.group(1)
    for claim in ("по СПб", "по Петербургу", "по всему городу", "по всей области", "по Москве"):
        if claim in html or claim in js:
            ERR.append(f"зона доставки «{claim}» никем не подтверждена — в data.js «{ZONE}»")
    named = set(re.findall(r"[КК]урьер по ([А-ЯЁ][а-яё]+)|[ДД]оставка по ([А-ЯЁ][а-яё]+)", html + "\n" + js))
    off = sorted({a or b for a, b in named if (a or b) not in ZONE})
    if off:
        ERR.append("зона доставки разошлась с data.js: " + ", ".join(off) + f" против «{ZONE}»")
    chip = re.search(r'data-delivery="courier"[^>]*>([^<]+)<', html)
    if not chip:
        ERR.append("в пакете нет чипа курьера — способ доставки выбирается непонятно чем")
    elif ZONE_SHORT not in chip.group(1) or not fee or f"{fee.group(1)} ₽" not in chip.group(1):
        ERR.append(f"чип курьера разошёлся с данными: «{chip.group(1).strip()}», а ждём «{ZONE_SHORT}» "
                   f"и {fee.group(1) if fee else 'неизвестный'} ₽")

rv = re.search(r'<section[^>]*id="reviews"[\s\S]*?</section>', html)
if not rv:
    ERR.append("нет блока отзывов")
else:
    block = rv.group(0)
    if "yandex.ru/sprav/widget/rating-badge" not in block:
        ERR.append("блок отзывов без виджета Яндекс Карт — откуда тогда рейтинг?")
    if "yandex.ru/maps/org/" not in block:
        ERR.append("блок отзывов без ссылки на настоящие отзывы")
    if re.search(r"<blockquote|review-text|fake-review", block):
        ERR.append("в блоке отзывов появились hand-written цитаты — их никто не писал")
    score = re.search(r'<div class="review-score">\s*<b[^>]*>([0-9],[0-9])</b>', block)
    aria = re.search(r'aria-label="Оценка ([0-9],[0-9]) из 5"', block)
    if not (score and aria):
        ERR.append("блок отзывов: цифра рейтинга или её озвучка не найдены — гейт слепой")
    elif score.group(1) != aria.group(1):
        ERR.append(f"рейтинг {score.group(1)} разошёлся с озвученным {aria.group(1)}")
    stars = block.count("#ic-star")
    if not 4 <= stars <= 6:
        ERR.append(f"в звёздном рейтинге {stars} звёзд")

ld_blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
if len(ld_blocks) < 2:
    ERR.append("ожидались JSON-LD магазина+FAQ и каталог от сборки")
store = faq = catalog = None
for b in ld_blocks:
    try:
        j = json.loads(b)
    except Exception as exc:
        ERR.append(f"JSON-LD не разбирается: {exc}")
        continue
    nodes = j.get("@graph", [j] if isinstance(j, dict) else [])
    for node in nodes:
        if node.get("@type") in ("GroceryStore", "Store", "SuperMarket", "FoodEstablishment"):
            store = node
        elif node.get("@type") == "FAQPage":
            faq = node
        elif node.get("@type") == "ItemList":
            catalog = node
if not store:
    ERR.append("JSON-LD: нет карточки магазина")
else:
    for k in ("name", "telephone", "address", "openingHoursSpecification", "url"):
        if k not in store:
            ERR.append(f"JSON-LD: у магазина нет {k}")
    if store.get("name") != BRAND:
        ERR.append("JSON-LD: название магазина не совпадает с вывеской")
    if store.get("url") != SITE_URL:
        ERR.append(f"JSON-LD: url {store.get('url')} не равен canonical {SITE_URL}")
    if not str(store.get("@id", "")).startswith(SITE_URL):
        ERR.append("JSON-LD: @id магазина вне нашего домена")
    street = store.get("address", {}).get("streetAddress", "")
    if street and re.sub(r"\s+", " ", street.replace("\u00a0", " ")).strip().lower() not in plain.lower():
        ERR.append(f"JSON-LD: адрес {street!r} не читается на странице")
    hours = store.get("openingHoursSpecification", [{}])[0]
    if len(store.get("openingHoursSpecification", [])) != 7 and hours.get("dayOfWeek") and len(hours["dayOfWeek"]) != 7:
        NOTES.append("JSON-LD: часы заявлены не на все дни — проверить вывеску")
    ld_phone = re.sub(r"\D", "", store.get("telephone", ""))
    visible = {re.sub(r"\D", "", x) for x in re.findall(
        r"\+7[\d\s()\-]{9,}", re.sub(r'<script type="application/ld\+json"[^>]*>[\s\S]*?</script>', " ", html))}
    if ld_phone and ld_phone not in visible:
        ERR.append("JSON-LD: телефон магазина не совпадает ни с одним видимым номером")
    if ld_phone != SHOP_PHONE:
        ERR.append("JSON-LD: телефон магазина не совпадает с номером из js/data.js")
def visible_faq_pairs(src):
    pairs = []
    for body in re.findall(r'<details class="faq-item"[^>]*>([\s\S]*?)</details>', src):
        q = re.search(r"<summary>([\s\S]*?)</summary>", body)
        a = re.search(r"<p>([\s\S]*?)</p>", body)
        if q and a:
            clean = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()
            # «+» из декоративного span — не часть вопроса
            pairs.append((clean(re.sub(r"<span>\+</span>", "", q.group(1))), clean(a.group(1))))
    return pairs


faq_visible = visible_faq_pairs(html)
faq_ld = [(q.get("name", ""), q.get("acceptedAnswer", {}).get("text", ""))
          for q in (faq or {}).get("mainEntity", [])]
if faq_visible and faq_ld != faq_visible:
    ERR.append("JSON-LD FAQ разошёлся с вопросами и ответами, которые видит посетитель")
if faq_visible and not faq:
    ERR.append("FAQ на странице есть, а в JSON-LD его нет — поисковик не увидит ни одного вопроса")
if faq:
    for q in faq.get("mainEntity", []):
        if not q.get("name") or not q.get("acceptedAnswer", {}).get("text"):
            ERR.append("JSON-LD: вопрос FAQ без ответа")
        if "цена" in q.get("name", "").lower() and "telegram" not in q.get("acceptedAnswer", {}).get("text", "").lower():
            NOTES.append("FAQ про цены: сверить, что ответ ведёт в Telegram, а не обещает сумму")
if catalog:
    names = [i.get("name") for i in catalog.get("itemListElement", [])]
    if len(names) != len(PRODUCTS):
        ERR.append(f"ld-catalog: {len(names)} позиций против {len(PRODUCTS)} в js/data.js — сборка не прогнана")
    elif set(names) != {p["name"] for p in PRODUCTS}:
        ERR.append("ld-catalog разошёлся с каталогом")
    if [i.get("position") for i in catalog.get("itemListElement", [])] != list(range(1, len(names) + 1)):
        ERR.append("ld-catalog: позиции перепутаны")

# ==================================================== 8. СБОРКА И ФАЙЛЫ =====
build_src = (ROOT / "tools" / "build.py").read_text(encoding="utf-8")
PS = re.search(r"PRODUCT_SIZES = \[([^\]]*)\]", build_src)
GS = re.search(r"GALLERY_SIZES = \[([^\]]*)\]", build_src)
if not PS or not GS:
    ERR.append("build.py: не разобрать списки размеров — гейт слепой")
else:
    p_sizes = [tuple(map(int, s)) for s in re.findall(r"\((\d+),\s*(\d+)\)", PS.group(1))]
    g_sizes = [tuple(map(int, s)) for s in re.findall(r"\((\d+),\s*(\d+)\)", GS.group(1))]
    call_p = {tuple(map(int, s)) for s in re.findall(r"photoSrc\(p\.photo,\s*(\d+),\s*(\d+)\)", app_js)}
    call_g = {tuple(map(int, s)) for s in re.findall(r"photoSrc\((?:g|item)\.photo,\s*(\d+),\s*(\d+)\)", app_js)}
    for size in sorted(call_p - set(p_sizes)):
        ERR.append(f"build.py не скачивает {size[0]}x{size[1]} — карточка останется без фото")
    for size in sorted(call_g - set(g_sizes)):
        ERR.append(f"build.py не скачивает галерейный {size[0]}x{size[1]}")
    for size in sorted(set(p_sizes) - call_p - set(g_sizes) - set(call_g)):
        NOTES.append(f"build.py тащит неиспользуемый размер товаров {size[0]}x{size[1]}")
    if not re.search(r"photoSrc\(", app_js):
        ERR.append("js/app.js не вызывает photoSrc() — картинки собираются незнамо откуда")
    want = {f"{p['photo']}-{w}x{h}.jpg" for p in PRODUCTS for w, h in p_sizes}
    want |= {f"{g['photo']}-{w}x{h}.jpg" for g in GALLERY for w, h in g_sizes}
    want |= {f"{m[0]}-{m[1]}x{m[2]}.jpg" for m in re.findall(r"assets/img/(\d+)-(\d+)x(\d+)\.jpg", html)}
    if not SKIP:
        for f in sorted(want):
            if not (ROOT / "assets" / "img" / f).exists():
                ERR.append(f"нет собранного фото assets/img/{f}")
        live_ids = {str(p["photo"]) for p in PRODUCTS} | {str(g["photo"]) for g in GALLERY}
        orphan = sorted(p.name for p in (ROOT / "assets" / "img").glob("*.jpg") if p.name.split("-")[0] not in live_ids)
        if orphan:
            ERR.append("в assets/img мусор от снятых позиций: " + ", ".join(orphan[:5]))
        heavy = sorted((ROOT / "assets" / "img").glob("*.jpg")) + [ROOT / "assets" / "og.png"]
        big = [f"{p.relative_to(ROOT).as_posix()} {p.stat().st_size // 1024} KB" for p in heavy
               if p.exists() and p.stat().st_size > 260_000]
        if big:
            ERR.append("фото не прожаты (тяжёлый первый экран): " + ", ".join(big[:4]))

fonts_css_path = ROOT / "assets" / "fonts.css"
families = set()
for val in re.findall(r"font-family:([^;}]+)", css):
    for part in val.split(","):
        part = part.strip().strip("'\"")
        if part and part not in GENERIC_FONTS:
            families.add(part)
if SKIP:
    NOTES.append("пропущена проверка собранных ассетов (--skip-assets)")
else:
    if not fonts_css_path.exists():
        ERR.append("нет assets/fonts.css — сборка не прогнана")
    else:
        fcss = fonts_css_path.read_text(encoding="utf-8")
        faces = re.findall(r'@font-face\{font-family:"([^"]+)";font-style:(\w+);font-weight:(\d+)', fcss)
        if not faces:
            ERR.append("assets/fonts.css без @font-face")
        have_families = {f for f, _, _ in faces}
        for fam in sorted(families - have_families):
            ERR.append(f"css зовёт гарнитуру {fam}, которой нет в assets/fonts.css — браузер подставит системную")
        for fam in sorted(have_families - families):
            ERR.append(f"шрифт {fam} скачан, но в css не вызывается — лишние байты каждому гостю")
        weights = {}
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            fam_m = re.search(r"font-family:\s*'([^']+)'", body)
            w_m = re.search(r"font-weight:\s*(\d+)", body)
            if fam_m and w_m:
                weights.setdefault(fam_m.group(1), set()).add(int(w_m.group(1)))
        for fam, ws in sorted(weights.items()):
            have_w = {int(w) for f, _, w in faces if f == fam}
            for w in sorted(ws - have_w):
                ERR.append(f"{fam} {w}: вес вызывается, а face не скачан (есть {sorted(have_w)})")
        for url in re.findall(r'url\("([^"]+\.woff2)"\)', fcss):
            if not (fonts_css_path.parent / url).exists():
                ERR.append(f"fonts.css зовёт отсутствующий {url}")
        if "font-display:swap" not in fcss:
            ERR.append("шрифты без font-display:swap — текст мигает при загрузке")

for u in re.findall(r'url\("([^"]+)"\)', css):
    if u.startswith(("data:", "http")):
        continue
    if not (css_path.parent / u).exists() and not (ROOT / u.lstrip("./")).exists() and not SKIP:
        ERR.append(f'css: url("{u}") ведёт в никуда')
for tag, dd, line in doc.tags:
    if tag in ("link", "script"):
        target = dd.get("href") or dd.get("src") or ""
        if target.startswith(("js/", "css/", "assets/", "manifest")) and not (ROOT / target).exists() and not SKIP:
            ERR.append(f"head: нет файла {target}")

manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
if manifest.get("name") != BRAND:
    ERR.append(f"манифест: name {manifest.get('name')!r} не равен вывеске")
for icon in manifest.get("icons", []):
    if not (ROOT / icon["src"]).exists() and not SKIP:
        ERR.append(f"манифест: нет иконки {icon['src']}")
    if not re.fullmatch(r"\d+x\d+", icon.get("sizes", "")):
        ERR.append(f"манифест: sizes иконки {icon['src']} кривые")
if not any(i.get("purpose") == "maskable" for i in manifest.get("icons", [])):
    ERR.append("манифест: нет maskable-иконки — на Android край обрежут")
for key in ("background_color", "theme_color"):
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", manifest.get(key, "")):
        ERR.append(f"манифест: {key} должен быть #RRGGBB")
tm = " ".join(metas(doc, "theme-color"))
if tm.lower() != manifest.get("theme_color", "").lower():
    ERR.append(f"theme-color в <head> ({tm}) и в манифесте ({manifest.get('theme_color')}) разошёлся")
if manifest.get("start_url") != "./" or manifest.get("scope") != "./":
    ERR.append("манифест: start_url/scope обязаны быть './' — сайт живёт в подпадке Pages")

sw_src = (ROOT / "sw.js").read_text(encoding="utf-8")
core_list = re.search(r"CORE\s*=\s*\[([^\]]*)\]", sw_src)
core = re.findall(r'"(\./[^"]*)"', core_list.group(1)) if core_list else []
if not core:
    ERR.append("sw.js: пустой CORE — офлайн-режим не соберётся")
for f in core:
    rel = f[2:]
    if rel and not (ROOT / rel).exists() and not SKIP:
        ERR.append(f"sw.js кэширует несуществующий {f}")
for must in ("./index.html", "./css/style.css", "./js/app.js", "./js/data.js", "./js/app-head.js",
             "./assets/fonts.css", "./manifest.webmanifest", "./assets/qr.svg"):
    if must not in core:
        ERR.append(f"sw.js: оболочка офлайна неполная — нет {must}")
if "assets/img" in sw_src:
    ERR.append("sw.js тащит фото в прекеши: это мегабайты, а не оболочка")
for retired in ("js/main.js", "js/theme.js", "css/themes.css", "vendor/", "assets/qr.png"):
    if retired in sw_src or retired in html or retired in js:
        ERR.append(f"след удалённого файла {retired} всё ещё подключается")
if not re.search(r"navigator\.serviceWorker\.register", js):
    ERR.append("sw.js лежит в репозитории, но его никто не регистрирует")

# ======================================================= 8a. QR-КОД ВИТРИНЫ ====
# Камера читает то, что нарисовано, а не то, что задумано: разбираем геометрию
# assets/qr.svg в матрицу модулей и сверяем её с адресом из canonical. Код печатает
# tools/build.py, поэтому расхождение значит, что в прод уехал чужой адрес.
def qr_modules(svg):
    """Тёмные модули из SVG-геометрии (M/m/H/h/V/v), обрезанные по габариту. None — мусор."""
    sc, wd = re.search(r'transform="scale\((\d+(?:\.\d+)?)\)"', svg), re.search(r'\bwidth="(\d+)"', svg)
    if not (sc and wd):
        return None
    scale = float(sc.group(1))
    side = int(round(int(wd.group(1)) / scale))
    if not 21 <= side <= 177:
        return None
    cells = [[False] * side for _ in range(side)]
    runs = 0
    for path in re.findall(r'<path[^>]*\bstroke="[^"]+"[^>]*\bd="([^"]+)"', svg):
        x = y = 0.0
        for cmd, nums in re.findall(r"([A-Za-z])([^A-Za-z]*)", path):
            vals = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", nums)]
            if cmd in "Mm":
                if len(vals) < 2:
                    return None
                x, y = (x + vals[0], y + vals[1]) if cmd.islower() else (vals[0], vals[1])
            elif cmd in "HhVv":
                for d in vals:
                    if cmd in "Hh":
                        row, c0, c1 = int(y), min(x, x + d), max(x, x + d)
                        if not 0 <= row < side:
                            return None
                        for c in range(int(math.floor(c0)), int(math.ceil(c1))):
                            if not 0 <= c < side:
                                return None
                            cells[row][c] = True
                        x += d
                    else:
                        col, r0, r1 = int(x), min(y, y + d), max(y, y + d)
                        if not 0 <= col < side:
                            return None
                        for r in range(int(math.floor(r0)), int(math.ceil(r1))):
                            if not 0 <= r < side:
                                return None
                            cells[r][col] = True
                        y += d
                    runs += 1
            elif cmd not in "Zz":
                return None
    rows = [r for r in cells if any(r)]
    if runs < 40 or len(rows) < 21:
        return None
    lo = min(r.index(True) for r in rows)
    hi = max(len(r) - 1 - r[::-1].index(True) for r in rows)
    crop = [row[lo:hi + 1] for row in rows]
    if len(crop) != len(crop[0]):          # QR-символ всегда квадратный
        return None
    return crop


qr_file = ROOT / "assets" / "qr.svg"
qr_err = re.search(r'QR_ERROR = "([A-Za-z])"', build_src)
qr_html = re.findall(r'<img[^>]*\bsrc="\./assets/qr\.svg"[^>]*>', html)
if len(qr_html) != 1:
    ERR.append(f"QR-код на витрине должен стоять ровно один раз, а их {len(qr_html)}")
elif not re.search(r'alt="[^"]*QR', qr_html[0]):
    ERR.append("у картинки с QR нет alt со словом QR — скринридер молчит, гость не поймёт, что там")
if "./assets/qr.svg" not in core:
    ERR.append("sw.js: QR не лежит в прекеши — офлайн-страница покажет пустой квадрат")
if not qr_err:
    ERR.append("build.py: не разобрать QR_ERROR — матрицу кода сверить нечем")
if not qr_file.exists():
    if not SKIP:
        ERR.append("нет собранного assets/qr.svg — гостю нечего сканировать")
else:
    qr_svg = qr_file.read_text(encoding="utf-8")
    drawn = qr_modules(qr_svg)
    if drawn is None:
        ERR.append("assets/qr.svg: матрица модулей не читается — на витрине не QR")
    elif "xmlns" not in qr_svg:
        ERR.append("assets/qr.svg: нет xmlns — как файл его браузер не покажет")
    elif qr_err:
        try:
            import segno
            want = [list(map(bool, row)) for row in segno.make(SITE_URL, error=qr_err.group(1)).matrix]
        except ImportError:
            NOTES.append("нет модуля segno — содержимое assets/qr.svg сверить нечем (pip install segno)")
        else:
            if drawn != want:
                ERR.append(f"assets/qr.svg ведёт не на {SITE_URL}: матрица модулей другая")


# ================================================== 9. CSS: ПАЛИТРЫ И ПРАВИЛА ====
palettes = {}
for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css, re.S):
    sel = " ".join(sel.split())
    keys = re.findall(r'html\[data-theme="([a-z]+)"\]', sel)
    if ":root" in sel:
        keys.append("root")
    if not keys or not re.search(r"--[a-z0-9-]+\s*:", body):
        continue
    for key in keys:
        palettes[key] = palettes.get(key, "") + body
if not palettes:
    ERR.append("CSS: ни одной палитры не разобрано")
default_vars = set(re.findall(r"(--[a-z0-9-]+)\s*:", palettes.get("root", "") + palettes.get(DEFAULT_THEME, "")))
if not default_vars:
    ERR.append("CSS: в дефолтной палитре нет ни одного токена — красить нечем")
for name, body in palettes.items():
    if name == "root":
        continue
    missing = sorted(default_vars - set(re.findall(r"(--[a-z0-9-]+)\s*:", body)))
    if missing:
        ERR.append(f'[data-theme="{name}"] не переопределяет токены: {", ".join(missing[:6])}'
                   + ("…" if len(missing) > 6 else ""))
declared_themes = set(data["T"])
css_themes = {n for n in palettes if n != "root"}
if declared_themes != css_themes:
    ERR.append(f"темы разошлись: data.js {sorted(declared_themes)} против css {sorted(css_themes)}")
swatch_themes = set(re.findall(r'data-set-theme="([a-z]+)"', html))
if swatch_themes != declared_themes:
    ERR.append(f"переключатель предлагает {sorted(swatch_themes)}, а палитр заявлено {sorted(declared_themes)}")
if DEFAULT_THEME not in declared_themes:
    ERR.append(f"дефолтная палитра {DEFAULT_THEME} не объявлена в THEME_LABELS")
labels = set(data["T"].values())
for lbl in sorted(labels):
    if lbl not in html:
        ERR.append(f"подпись палитры «{lbl}» нигде не показана")

var_refs = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", css))
js_written = {"--" + v for v in re.findall(r"setProperty\(\s*['\"]--([\w-]+)", js) + re.findall(r"--([a-z0-9-]+)\s*:", js)}
undeclared = sorted(var_refs - set(re.findall(r"(--[a-z0-9-]+)\s*:", css)) - js_written)
if undeclared:
    ERR.append("css зовёт незадекларированные переменные: " + ", ".join(undeclared[:8]))
if css.count("{") != css.count("}"):
    ERR.append(f"css: скобки не сходятся ({css.count('{')} против {css.count('}')})")
flat = squash(css)
for prop in ("backdrop-filter",):
    for v in sorted({x for x in re.findall(r"[;{]" + prop + r":([^;}]+)", flat)}):
        if f"-webkit-{prop}:{v}" not in flat:
            ERR.append(f"css: {prop}:{v.strip()} без -webkit- — на Safari стекло потухнет")

# --- контраст токенов ------------------------------------------------------
# Пиксели меряет headless-прогон, но разъехавшийся токен палитры видно и здесь:
# так регресс («осветлили --accent») ловится до сборки, а не после снимка экрана.
def _lin(x):
    x /= 255
    return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4


def _lum(rgb):
    r, g, b = rgb
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _ratio(fg, bg):
    a, b = _lum(fg), _lum(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _color(val):
    if not val:
        return None
    val = val.strip()
    if val.startswith("#"):
        h = val[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            return None
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)), 1.0
    m = re.match(r"rgba?\(([^)]+)\)", val)
    if not m:
        return None
    p = [x for x in re.split(r"[ ,/]+", m.group(1).strip()) if x]
    try:
        rgb = tuple(int(float(p[i])) for i in (0, 1, 2))
    except (ValueError, IndexError):
        return None
    return rgb, (float(p[3]) if len(p) > 3 else 1.0)


def _over(color, base):
    """Полупрозрачный цвет — смешивание с подложкой, а не «дырка»."""
    if not color or not base:
        return None
    (r, g, b), a = color
    base = base[0] if isinstance(base[0], tuple) else base
    if a >= 1:
        return (r, g, b)
    return tuple(round(a * c + (1 - a) * d) for c, d in zip((r, g, b), base))


def _toks(body):
    return {k: " ".join(v.split()) for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", body)}


def _tok(name, tree, root_tree, depth=0):
    v = tree.get(name, root_tree.get(name))
    m = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", v or "")
    if m and depth < 6:
        return _tok(m.group(1), tree, root_tree, depth + 1)
    return v


TEXT_PAIRS = [
    ("основная кнопка", "--accent-ink", "--accent"),
    ("бренд-кнопка", "--brand-ink", "--brand"),
    ("золотая кнопка", "--gold-ink", "--gold"),
    ("текст на карточке", "--ink", "--surface"),
    ("текст на странице", "--ink", "--bg"),
    ("вторичный текст", "--ink-muted", "--surface"),
    ("бейдж «в сезоне»", "--badge-ink", "--fresh"),
    ("надзаголовок", "--eyebrow", "--bg"),
    ("шапка", "--header-ink", "--header-bg"),
    ("шапка вторично", "--header-muted", "--header-bg"),
    ("герой вторично", "--hero-muted", "--hero-bg-2"),
    ("грифельная доска", "--chalk-ink", "--chalk-bg-2"),
    ("мел на доске", "--chalk-accent", "--chalk-bg-2"),
]
root_toks = _toks(palettes.get("root", ""))
for name, body in sorted(palettes.items()):
    if name == "root":
        continue
    tree = dict(root_toks)
    tree.update(_toks(body))
    base = _color(_tok("--bg", tree, root_toks))
    for what, fg, bg in TEXT_PAIRS:
        b0 = _over(_color(_tok(bg, tree, root_toks)), base)
        f0 = _over(_color(_tok(fg, tree, root_toks)), b0)
        if not f0 or not b0:
            ERR.append(f"[{name}] «{what}»: не разобрались цвета {fg} на {bg}")
        elif _ratio(f0, b0) < 4.5:
            ERR.append(f"[{name}] «{what}» {fg} на {bg} = {_ratio(f0, b0):.2f} — ниже 4.5 по WCAG")

# Кольцо фокуса — не текст, но WCAG 1.4.11 требует у индикатора состояния те же 3:1 к
# соседу. Обводка и ореол — пара: на пергаменте работает тёмная обводка, на грифельной
# доске её место занимает светлый ореол. Претензия, только если оба слоя бледнее 3:1.
RING_SURFACES = ("--bg", "--bg-alt", "--surface", "--header-bg", "--hero-bg-2", "--chalk-bg-2")
for name, body in sorted(palettes.items()):
    if name == "root":
        continue
    tree = dict(root_toks)
    tree.update(_toks(body))
    base = _color(_tok("--bg", tree, root_toks))
    layers = [_over(_color(_tok(t, tree, root_toks)), base) for t in ("--focus-ring", "--focus-halo")]
    if not all(layers):
        ERR.append(f"[{name}] в палитре нет пары --focus-ring/--focus-halo")
        continue
    for surf in RING_SURFACES:
        b0 = _over(_color(_tok(surf, tree, root_toks)), base)
        if not b0:
            ERR.append(f"[{name}] «кольцо фокуса»: не разобрался фон {surf}")
        elif max(_ratio(l, b0) for l in layers) < 3:
            ERR.append(f"[{name}] кольцо фокуса на {surf}: оба слоя бледнее {max(_ratio(l, b0) for l in layers):.2f}:1 — WCAG 1.4.11")

# Кольцо фокуса ищем по всем правилам с :focus-visible: первое попавшееся
# «:focus-visible { border-bottom-color }» не доказывает, что фокус видно.
rings = [body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if ":focus-visible" in sel]
ring_ok = any(re.search(r"(?<![-\w])outline\s*:\s*(?!none\b|0\b)\S", b) for b in rings)
if not ring_ok:
    ERR.append("css: нет правила :focus-visible с outline — клавиатурный фокус не видно")
if re.search(r"outline\s*:\s*(?:none|0)\b", css) and not ring_ok:
    ERR.append("css снимает outline, не заменив его кольцом")
for killer in ("-webkit-tap-highlight-color: transparent", "-webkit-tap-highlight-color:transparent"):
    if killer in css:
        NOTES.append("tap-highlight выключен — палец не подтверждает нажатие цветом")
rm = media_block(css, "(prefers-reduced-motion: reduce)")
if rm is None:
    ERR.append("css: нет @media (prefers-reduced-motion: reduce)")
elif not re.search(r"animation|transition", rm):
    ERR.append("@media (prefers-reduced-motion: reduce) ничего не гасит")
# Плавный перелёт по якорям — анимация из взаимодействия (WCAG 2.3.3): флаг reduce обязан
# выключить и её, иначе клик по меню у чувствительного человека всё равно «летит».
elif "scroll-behavior: auto" not in rm.replace("  ", " ").replace(":auto", ": auto"):
    ERR.append("в @media (prefers-reduced-motion: reduce) прокрутка по якорям остаётся плавной")
if "matchMedia('(prefers-reduced-motion: reduce)')" not in js and 'matchMedia("(prefers-reduced-motion: reduce)")' not in js:
    ERR.append("JS не смотрит на prefers-reduced-motion: 3D-наклон и перелёты крутятся всегда")
coarse = media_block(css, "(pointer: coarse)")
if coarse is None:
    ERR.append("css: нет @media (pointer: coarse) — тап-цели на телефоне никто не гарантирует")
else:
    for mnum in re.findall(r"min-height:\s*(\d+)px", coarse):
        if int(mnum) < 24:
            ERR.append(f"в @media (pointer: coarse) min-height {mnum}px — меньше WCAG 2.5.8")
    if "44" not in coarse:
        ERR.append("в @media (pointer: coarse) нет планки 44px для пальцев")
if "@media print" not in css:
    ERR.append("css: нет @media print — список покупок нельзя вменяемо распечатать")

# Список «спрятать в печати» живёт отдельно от разметки: селектор, который ничего не
# находит, молча возвращает на лист кнопку, которую все считали убранной.
_print_blk = media_block(css, "print")
if _print_blk:
    _corpus = html + "\n" + app_js + "\n" + head_js + "\n" + data_js
    _dead = []
    for _sel in re.findall(r"([^{}]+)\{[^{}]*display:\s*none\s*!important", re.sub(r"/\*[\s\S]*?\*/", " ", _print_blk)):
        for _tok in _sel.split(","):
            _parts = _tok.strip().split()
            _tok = _parts[-1] if _parts else ""
            if re.fullmatch(r"[.#][A-Za-z][\w-]*", _tok) and _tok[1:] not in _corpus:
                _dead.append(_tok)
    if _dead:
        ERR.append("в @media print прячут несуществующее: " + ", ".join(sorted(set(_dead))))

# Меню в шапке держится на двух правилах: навигацию показывают, бургер прячут. Пороги
# обязаны совпадать: если разойдутся, на ширине между ними не останется ни одного способа
# открыть разделы (бургер уже спрятан, а ссылок ещё нет).
def _header_bp(sel, action):
    m = re.search(r"@media \(min-width:\s*(\d+)px\)\s*\{\s*" + re.escape(sel) + r"\s*\{\s*" + action, css)
    return None if m is None else int(m.group(1))

_nav_bp = _header_bp(".main-nav", r"display:\s*flex")
_burger_bp = _header_bp(".burger-btn", r"display:\s*none")
if _nav_bp is None:
    ERR.append("css: .main-nav не включается ни одним @media — меню раздела недоступно даже на большом экране")
elif _burger_bp is None:
    ERR.append("css: .burger-btn нигде не прячется — на десктопе под шапкой второе меню")
elif _nav_bp != _burger_bp:
    ERR.append(f"пороги шапки разошлись: ссылки показывают с {_nav_bp}px, бургер прячут с {_burger_bp}px")

def class_tokens(tpl):
    """Классы из шаблона: из ${peak ? 'is-peak' : ''} берём строковые литералы."""
    flat = re.sub(r"\$\{([^}]*)\}", lambda m: " " + " ".join(re.findall(r"""['"]([\w-]+)['"]""", m.group(1))) + " ", tpl)
    return [x for x in flat.split() if re.fullmatch(r"[\w-]+", x)]


used_classes = set(doc.classes) | set(d404.classes)
for src_text in (app_js, head_js, data_js):
    for raw in re.findall(r"""class(?:Name)?\s*=\s*["'`]([^"'`]*)["'`]""", src_text):
        used_classes |= {x for x in class_tokens(raw) if not x.startswith(("is-", "has-"))}
    used_classes |= set(re.findall(r"""classList\.(?:add|remove|toggle)\(\s*['"]([\w-]+)""", src_text))
# только селекторы: иначе «.html» и «.py» из комментариев и путей считаются классами
css_classes = set()
bare_css = re.sub(r"/\*[\s\S]*?\*/", "", css)
for sel in re.findall(r"(?:^|[;}{])\s*([^{};@]*?)\s*\{", bare_css):
    css_classes |= set(re.findall(r"\.([A-Za-z][\w-]*)", sel))
undefined = sorted(c for c in used_classes - css_classes if not c.startswith(("is-", "has-")) and len(c) > 2)
if undefined:
    ERR.append("класс в разметке/JS без единого правила в css: " + ", ".join(undefined[:10]))
# is-*/has-* — состояния, которые навешиваются условно и именами из переменных: статикой не свести
unused = sorted(c for c in css_classes - used_classes if not c.startswith(("is-", "has-")))
if len(unused) > 6:
    NOTES.append(f"правил css не востребовано: {len(unused)} шт.: " + ", ".join(unused))
elif unused:
    NOTES.append("правил css не востребовано: " + ", ".join(unused))

for f in ("robots.txt", "sitemap.xml"):
    txt = (ROOT / f).read_text(encoding="utf-8")
    for u in re.findall(r"https?://[^\s<>\"]+", txt):
        if not u.startswith(SITE_URL) and "sitemaps.org/schemas" not in u:
            ERR.append(f"{f}: чужой адрес {u}")
    if SITE_URL not in txt:
        ERR.append(f"{f}: нет canonical {SITE_URL}")
sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
if re.findall(r"<loc>([^<]+)</loc>", sm) != [SITE_URL]:
    ERR.append("sitemap: <loc> не равен canonical")
if "index.html" in sm:
    ERR.append("sitemap: index.html должен быть каноничен через /")
robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
if "Sitemap:" not in robots:
    ERR.append("robots.txt: нет строки Sitemap — сканер не найдёт карту")

if not ERR:
    print(f"гейты: {len(doc.ids)} id, {len(PRODUCTS)} позиций, {len(imgs)} картинок, "
          f"{len(doc.symbols)} иконок, {len(css_classes)} классов, {len(declared_themes)} палитр")
for note in NOTES:
    print("NOTE:", note)
if ERR:
    print("FAIL:")
    for e in ERR:
        print(" -", e)
    sys.exit(1)
print("ALL CHECKS PASSED")
