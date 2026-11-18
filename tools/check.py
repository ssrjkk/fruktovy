#!/usr/bin/env python3
"""Гейт качества перед деплоем. python tools/check.py [--skip-assets]"""
import json, re, sys
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SKIP = "--skip-assets" in sys.argv
ERR, NOTES = [], []
VOID = {"meta", "link", "img", "br", "hr", "input", "source", "path", "circle", "rect", "ellipse", "line", "stop", "use", "polyline", "polygon"}


class C(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack = []; self.imgs = []; self.err = []
    def handle_starttag(self, t, a):
        d = dict(a)
        if t == "img": self.imgs.append(d)
        if t not in VOID: self.stack.append(t)
    def handle_endtag(self, t):
        if t in VOID: return
        if self.stack and self.stack[-1] == t: self.stack.pop()
        elif t in self.stack:
            while self.stack and self.stack[-1] != t: self.err.append("unclosed " + self.stack.pop())
            self.stack.pop()
        else: self.err.append("stray /" + t)


for name in ("index.html", "404.html"):
    c = C(); c.feed((ROOT / name).read_text(encoding="utf-8"))
    if c.err or c.stack: ERR.append(f"{name}: {c.err} {c.stack}")
    if not c.imgs and name == "index.html": ERR.append("index.html: no imgs scanned (blind)")
    for i, a in enumerate(c.imgs):
        for r in ("alt", "width", "height"):
            if r not in a: ERR.append(f"{name} img#{i} no {r}")

html = (ROOT / "index.html").read_text(encoding="utf-8")
blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
if len(blocks) < 2: ERR.append("expected main JSON-LD + ld-catalog")
for b in blocks:
    try: json.loads(b)
    except Exception as e: ERR.append(f"JSON-LD: {e}")
main = json.loads(blocks[0])
faq = [x for x in main["@graph"] if x["@type"] == "FAQPage"][0]["mainEntity"]
if not faq: ERR.append("FAQ empty (blind)")

import quickjs
ctx = quickjs.Context()
ctx.eval((ROOT / "js" / "data.js").read_text(encoding="utf-8"))
data = json.loads(ctx.eval("JSON.stringify({PRODUCTS: PRODUCTS, GALLERY: GALLERY, GUIDE: GUIDE, CATS: CATS})"))
if len(data["PRODUCTS"]) < 20: ERR.append("products scan blind")
cat = json.loads(re.search(r'id="ld-catalog">(.*?)</script>', html, re.S).group(1))
if not SKIP and len(cat.get("itemListElement", [])) != len(data["PRODUCTS"]): ERR.append("ld-catalog not injected")

json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
for cssp in sorted((ROOT / "css").glob("*.css")) + [ROOT / "assets" / "fonts.css"]:
    if not cssp.exists():
        if not SKIP: ERR.append("missing " + str(cssp))
        continue
    css = cssp.read_text(encoding="utf-8")
    if css.count("{") != css.count("}"): ERR.append(f"CSS braces {cssp.name}")
    for u in re.findall(r'url\("([^"]+)"\)', css):
        if u.startswith("data:"): continue
        if not (cssp.parent / u).resolve().exists() and not SKIP: ERR.append("css url " + u)

# Кавычка в стеке шрифтов, которой нет в assets/fonts.css, в проде молча
# подменяется системной гарнитурой: метрики плывут, а в браузере всё «нормально».
SYS_FACES = {"Arial Narrow", "Roboto Condensed", "Liberation Sans Narrow",
             "Franklin Gothic Medium", "Segoe UI", "Times New Roman", "Noto Sans"}
_fonts = ROOT / "assets" / "fonts.css"
if _fonts.exists():
    hosted = set(re.findall(r'font-family:"([^"]+)"', _fonts.read_text(encoding="utf-8")))
    used = set()
    decl = re.compile(r'(?:font-family|--[\w-]*(?:font|display|body|heading)[\w-]*)\s*:\s*([^;}]+)')
    for cssp in sorted((ROOT / "css").glob("*.css")):
        for value in decl.findall(cssp.read_text(encoding="utf-8")):
            used |= set(re.findall(r'"([^"]+)"', value))
    for fam in sorted(used - SYS_FACES - hosted):
        ERR.append(f"шрифт {fam} используется в CSS, но не самохостed в assets/fonts.css")

try:
    import esprima
    for p in sorted((ROOT / "js").glob("*.js")) + [ROOT / "sw.js"]:
        try: esprima.parseScript(p.read_text(encoding="utf-8"))
        except Exception as e: ERR.append(f"JS {p.name}: {e}")
except ImportError:
    NOTES.append("esprima missing")

refs = set(re.findall(r'(?:href|src|data-full)="([^"#]+)"', html))
for ss in re.findall(r'(?:srcset|imagesrcset)="([^"]+)"', html):
    refs.update(x.strip().split(" ")[0] for x in ss.split(","))
checked = 0
for u in refs:
    if u.startswith(("http", "tel:", "mailto:", "data:")) or u == "./": continue
    checked += 1
    if not (ROOT / u).exists() and not SKIP: ERR.append("missing " + u)
if not checked: ERR.append("no local refs scanned (blind)")

symbols = set(re.findall(r'<symbol id="i-([a-z0-9-]+)"', html))
MAINJS = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
DATAJS = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
used = set(re.findall(r'ico\(\'([a-z0-9-]+)\'\)', MAINJS))
used.update(re.findall(r'<use href="#i-([a-z0-9-]+)"', html))
# Глифы вызываются и из данных: HOW-шаги в main.js и подсказки GUIDE в data.js.
# Без этого блока новый глиф, заявленный только в данных, считался бы неиспользованным.
used.update(re.findall(r"i:\s*'([a-z0-9-]+)'", MAINJS))
used.update(re.findall(r"i:\s*'([a-z0-9-]+)'", DATAJS))
if len(symbols) < 20: ERR.append("sprite scan blind")
if used - symbols: ERR.append(f"icons used but not in sprite: {sorted(used - symbols)}")
if symbols - used: ERR.append(f"sprite icons never used: {sorted(symbols - used)}")

# Подсказки по хранению: их иконки лежат в data.js, и до этого блока спрайт для них
# не проверялся вовсе.
gtabs = set(re.findall(r'data-tab="([^"]+)"',
                       re.search(r'id="guideTabs".*?</div>', html, re.S).group(0)))
cat_ids = {c["id"] for c in data["CATS"] if c["id"] not in ("all", "fav")}
# У CATS только вывеска: поля товаров, затёсанные сюда же, читаются молча и ничего не ломают.
cat_extra = sorted({c["id"]: sorted(set(c) - {"id", "name", "icon"}) for c in data["CATS"] if set(c) - {"id", "name", "icon"}}.items())
if cat_extra:
    ERR.append(f"category rows carrying product fields: {cat_extra}")
GUIDE = data["GUIDE"]
noguide = sorted(cat_ids - set(GUIDE))
if noguide:
    ERR.append(f"catalog categories without guide tips: {noguide}")
untabbed = sorted(set(GUIDE) - gtabs)
if untabbed:
    ERR.append(f"guide tips without a tab: {untabbed}")
badicons = sorted({t["i"] for tips in GUIDE.values() for t in tips} - symbols)
if badicons:
    ERR.append(f"guide icons missing from sprite: {badicons}")
shorth = [f"{k}/{t['t']}" for k, tips in GUIDE.items() for t in tips if len(t.get("d", "")) < 40]
if shorth:
    ERR.append("guide tips shorter than 40 chars: " + repr(shorth))
# Два совета в одной вкладке с одним глифом читаются как одна и та же мысль:
# подпись различить их не помогает, когда список проглядывают по иконкам.
dup = {tab: sorted({t["i"] for t in tips if [x["i"] for x in tips].count(t["i"]) > 1})
       for tab, tips in GUIDE.items()}
dup = {k: v for k, v in dup.items() if v}
if dup:
    ERR.append("guide tabs reusing one glyph for two tips: " + repr(dup))

# Контракт загрузки картинок: всё до каталога грузится жадно (это первый экран),
# всё после — лениво. Первая же обязана быть заявлена как LCP.
real_imgs = [(m.start(), m.group(0)) for m in re.finditer(r"<img\b[^>]*>", html) if 'src="data:' not in m.group(0)]
if len(real_imgs) < 3:
    ERR.append("index.html has almost no imgs to police (blind)")
cat_at = html.find('id="catalog"')
if cat_at < 0:
    ERR.append("no catalog anchor: cannot tell what is below the fold")
eager = 0
for pos, tag in real_imgs:
    src = (re.search(r'src="([^"]+)"', tag) or [None, "?"])[1]
    lm = re.search(r'loading="([^"]+)"', tag)
    if not lm:
        ERR.append(f"img without an explicit loading decision: {src}")
        continue
    if pos < cat_at:
        eager += 1
        if lm.group(1) != "eager":
            ERR.append(f"first-screen img is lazy and will pop in: {src}")
    elif lm.group(1) != "lazy":
        ERR.append(f"img below the catalog is not lazy-loaded: {src}")
if sum('fetchpriority="high"' in t for _, t in real_imgs) != 1:
    ERR.append('exactly one img may claim fetchpriority="high" (the LCP hero art)')
if eager > 4:
    ERR.append(f"{eager} eager imgs above the catalog: first paint pays for every one")
jsn = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
lazy_miss = sorted({re.search(r"<img\b[^>]*>", t).group(0)[:56] for t in re.findall(r"<img\b[^>]*>", jsn) if "loading=" not in t})
if lazy_miss:
    ERR.append("JS-rendered imgs without a loading decision: " + repr(lazy_miss[:4]))

if not SKIP:
    for v in ("swiper-bundle.min.js", "swiper-bundle.min.css", "lenis.min.js", "gsap.min.js", "ScrollTrigger.min.js"):
        if not (ROOT / "vendor" / v).exists(): ERR.append("vendor " + v)
    for f in ("og.png", "icon-192.png", "icon-512.png", "fonts.css"):
        if not (ROOT / "assets" / f).exists(): ERR.append("assets " + f)
    if "__BUILD_ID__" in (ROOT / "sw.js").read_text(encoding="utf-8"): ERR.append("sw not stamped")
import xml.etree.ElementTree as ET
ET.fromstring((ROOT / "sitemap.xml").read_text(encoding="utf-8"))
if "Content-Security-Policy" not in html: ERR.append("no CSP")
if 'rel="canonical"' not in html: ERR.append("no canonical")
if "https://ssrjkk.github.io/fruktovy/sitemap.xml" not in (ROOT / "robots.txt").read_text(encoding="utf-8"):
    ERR.append("robots sitemap drift")
CANON = "https://ssrjkk.github.io/fruktovy/"

# Наполнение каталога: у каждой позиции свой вкус и своё хранение. Раньше peek
# брал первый совет категории, и яблокам показывалось про бананы.
DECOR = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
PIDS = [p["id"] for p in data["PRODUCTS"]]
if len(PIDS) < 20:
    ERR.append("product content scan blind")
baduse = sorted(p["id"] for p in data["PRODUCTS"] if not 45 <= len(p.get("use", "")) <= 115)
if baduse:
    ERR.append(f"taste text out of 45..115 chars: {baduse}")
badstore = sorted(p["id"] for p in data["PRODUCTS"] if not 30 <= len(p.get("store", "")) <= 100)
if badstore:
    ERR.append(f"storage note out of 30..100 chars: {badstore}")
for field, label in (("use", "taste"), ("store", "storage")):
    vals = [p.get(field, "") for p in data["PRODUCTS"]]
    dup = sorted({v for v in vals if v and vals.count(v) > 1})
    if dup:
        ERR.append(f"same {label} text on several products: {dup}")
if 'id="peekDesc"' not in html:
    ERR.append("peek dialog has no place for the product taste text")
for frag, what in (("+esc(p.use)+", "taste text never rendered on a card"),
                   ("$('#peekDesc').textContent=p.use", "taste text never rendered in peek"),
                   ("p.store||", "peek still uses the category note instead of the product one")):
    if frag not in jsn:
        ERR.append(what)
for sel in (".p-use", ".peek-desc"):
    m = re.search(re.escape(sel) + r"\{([^}]*)\}", DECOR)
    if not m:
        ERR.append(f"no style for {sel}")
    elif sel == ".p-use" and "line-clamp" not in m.group(1):
        ERR.append(".p-use has no line clamp: cards of different lengths will tear the grid")

# Фон витрины: мягкий цвет и бумажное зерно. Сетка-«квадраты» и ходящие лучи — ровно то,
# из-за чего магазин выглядит сгенерированным; их убрали по прямой просьбе.
for cls in (".bg-grid", ".bg-rays"):
    if cls in DECOR or cls[1:] in html:
        ERR.append(f"decorative square layer still wired: {cls}")
if re.search(r"data:image/svg\+xml[^)]*?M0 \d+h\d+M\d+ 0v\d+", DECOR):
    ERR.append("square-grid pattern painted as a background overlay")
for need in ("bg-mesh", "bg-grain"):
    if need not in html:
        ERR.append(f"background layer missing: {need}")


def metaval(prop):
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), html)
    return m.group(1) if m else None


for prop in ("og:image", "twitter:image"):
    v = metaval(prop)
    if not v:
        ERR.append("missing " + prop)
    elif not v.startswith(CANON):
        ERR.append(f"{prop} must be absolute, crawlers drop relative: {v}")
if not metaval("twitter:card"):
    ERR.append("no twitter:card")
for node in main["@graph"]:
    imgv = node.get("image")
    if isinstance(imgv, str) and not imgv.startswith(CANON):
        ERR.append("JSON-LD image must be absolute: " + imgv)

# Витринные данные магазина в JSON-LD обязаны совпадать с data.js: поисковик читает
# именно их, а карточку на странице человек правит в другом месте.
gs = next((n for n in main["@graph"] if n.get("@type") == "GroceryStore"), None)
if not gs:
    ERR.append("no GroceryStore node in JSON-LD (blind)")
else:
    shop = json.loads(ctx.eval("JSON.stringify(SHOP)"))
    dig = lambda v: re.sub(r"\D", "", str(v or ""))
    if dig(gs.get("telephone")) != dig(shop["phone"]):
        ERR.append("JSON-LD telephone drifted from SHOP.phone")
    alt = [dig(x.get("telephone")) for x in (gs.get("alternateTelephone") or []) if isinstance(x, dict)]
    if dig(shop["phone2"]) not in alt:
        ERR.append("SHOP.phone2 is missing from JSON-LD alternateTelephone")
    if not re.fullmatch(r"[₽$€£]", str(gs.get("priceRange", ""))):
        ERR.append("priceRange must be a currency symbol, not prose: " + repr(gs.get("priceRange")))
    oh = (gs.get("openingHoursSpecification") or [{}])[0]
    if (oh.get("opens"), oh.get("closes")) != (shop["open"], shop["close"]):
        ERR.append(f"JSON-LD hours {oh.get('opens')}-{oh.get('closes')} != SHOP {shop['open']}-{shop['close']}")
    if len(oh.get("dayOfWeek") or []) != 7:
        ERR.append("JSON-LD opening hours must list all 7 days")
    geo = gs.get("geo") or {}
    if abs(float(geo.get("latitude") or 0) - 59.957835) > 0.001 or abs(float(geo.get("longitude") or 0) - 30.30879) > 0.001:
        ERR.append("JSON-LD geo drifted from the address on Сытнинская")
    sameas = gs.get("sameAs") or []
    if not any(str(shop["map"]).split("oid=")[-1].split("&")[0] in u for u in sameas):
        ERR.append("JSON-LD sameAs does not point at the Yandex organisation from SHOP.map")

vis = re.findall(r'<details[^>]*>\s*<summary>(.*?)</summary>\s*<div class="faq-body">(.*?)</div>\s*</details>', html, re.S)
if not vis:
    ERR.append("FAQ visible blocks not parsed (blind)")
elif len(vis) != len(faq):
    ERR.append(f"FAQ count: visible {len(vis)} != JSON-LD {len(faq)}")


def plain(t):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


for i, (q, a) in enumerate(vis):
    if i >= len(faq):
        break
    if plain(q) != plain(faq[i]["name"]):
        ERR.append(f"FAQ#{i} question differs from JSON-LD")
    if plain(a) != plain(faq[i]["acceptedAnswer"]["text"]):
        ERR.append(f"FAQ#{i} answer differs from JSON-LD")

forms = set(re.findall(r"\d\d:\d\d([–—-])\d\d:\d\d", html))
if len(forms) > 1:
    ERR.append("hours use mixed dash forms: " + repr(sorted(forms)))
elif forms:
    dash = next(iter(forms))
    bsrc = (ROOT / "tools" / "build.py").read_text(encoding="utf-8")
    for other in set(re.findall(r"\d\d:\d\d([–—-])\d\d:\d\d", bsrc)) - {dash}:
        ERR.append(f"build.py writes hours with '{other}', site uses '{dash}'")

SELF_HOST, EMBEDS = "ssrjkk.github.io", {"yandex.ru"}
hosts = {m.group(1).lower() for m in re.finditer(r'<(?:iframe|script|img|link)[^>]+(?:src|href)="https?://([^/"\']+)/', html)}
undeclared = (hosts - {SELF_HOST}) - EMBEDS
if undeclared:
    ERR.append("undeclared third-party embed hosts: " + repr(sorted(undeclared)))
if EMBEDS & hosts:
    if re.search(r"сторонних трекеров", html):
        ERR.append("page embeds third-party origins but still claims 'нет сторонних трекеров'")
    if "cookie" not in html.lower():
        ERR.append("third-party embed present without cookie disclosure")

sw = (ROOT / "sw.js").read_text(encoding="utf-8")
core = re.findall(r'"\./([^"]*)"', sw)
if len(core) < 10:
    ERR.append(f"sw CORE has only {len(core)} entries (blind)")
shell = set(re.findall(r'<link rel="(?:stylesheet|manifest)" href="([^"]+)"', html)) | set(re.findall(r'<script[^>]+src="([^"]+)"', html))
notcached = sorted(s for s in shell if not s.startswith(("http", "//")) and s not in core)
if notcached:
    ERR.append("not precached, offline shell incomplete: " + repr(notcached))
heavy, tot = [], 0
for u in ["index.html", "404.html"] + core:
    f = ROOT / u
    if u and f.is_file():
        sz = f.stat().st_size
        tot += sz
        if sz > 200_000:
            heavy.append((u, sz))
if heavy:
    ERR.append("precache carries display-only bulk: " + repr(heavy))
if tot > 1_200_000:
    ERR.append(f"sw precache total {tot} B > 1.2 MB")

og = ROOT / "assets" / "og.png"
if og.exists() and og.stat().st_size > 260_000:
    ERR.append(f"og.png {og.stat().st_size} B > 260 KB — every link preview pays this")

def css_blocks(text, marker):
    out, i = [], 0
    while True:
        j = text.find(marker, i)
        if j < 0:
            return out
        k, depth, e = text.find("{", j), 0, text.find("{", j)
        while e < len(text):
            if text[e] == "{":
                depth += 1
            elif text[e] == "}":
                depth -= 1
                if depth == 0:
                    break
            e += 1
        out.append(text[k + 1:e])
        i = e


if css_text := next((c for c in [str(ROOT / "css" / "style.css")] if Path(c).exists()), ""):
    css = Path(css_text).read_text(encoding="utf-8")
    if not re.search(r"\.rail a::before[^{]*\{[^}]*inset:-\d+px", css):
        ERR.append("rail dots lost their enlarged hit area (.rail a::before inset)")
    pblk = "".join(css_blocks(css, "@media print"))
    if not pblk:
        ERR.append("no @media print block: dark sections print as a black sheet")
    else:
        need = {
            "white sheet (background:#fff)": "background:#fff",
            "black text (color:#000)": "color:#000",
            "decor stripped (background-image:none)": "background-image:none",
            "cards not split across pages (break-inside:avoid)": "break-inside:avoid",
            "link targets on paper (attr(href))": "attr(href)",
        }
        for label, needle in need.items():
            if needle not in pblk:
                ERR.append("print: missing " + label)
        if not re.search(r"#mapBox\{[^}]*display:none", pblk):
            ERR.append("print: the Yandex iframe is not hidden (#mapBox display:none)")
        src_all = html + sw + (ROOT / "js" / "main.js").read_text(encoding="utf-8") \
            + (ROOT / "js" / "data.js").read_text(encoding="utf-8")
        dead = sorted({c for b in css_blocks(css, "@media print")
                       for sel in re.findall(r"(?:^|[};])([^{};]+)\{", b)
                       for c in re.findall(r"\.([A-Za-z][\w-]*)", sel)
                       if not re.search(r"[\"'\s.:-]" + re.escape(c) + r"\b", src_all)})
        if dead:
            ERR.append("print rules name classes the markup never uses: " + repr(dead[:8]))

CSS_MAIN = (ROOT / "css" / "style.css").read_text(encoding="utf-8")
VARS = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", CSS_MAIN.split("}", 1)[0]))


def col(v):
    if isinstance(v, tuple):
        return v
    if v.startswith("--"):
        if v not in VARS:
            return (0, 0, 0)          # отсутствующий токен отдельный гейт репортит
        v = VARS[v]
    m = re.match(r"rgba?\(([^)]+)\)", v)
    if m:
        p = [float(x) for x in re.split(r"[ ,/]+", m.group(1).strip()) if x]
        return (p[0], p[1], p[2], p[3] if len(p) > 3 else 1.0)
    return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))


def chan(c):
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def lum(c):
    return 0.2126 * chan(c[0]) + 0.7152 * chan(c[1]) + 0.0722 * chan(c[2])


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def fold(base, layers):
    out = col(base)
    for spec in layers:
        c = col(spec[0])
        out = tuple(c[i] * spec[1] + out[i] * (1 - spec[1]) for i in range(3))
    return out


# (метка, цвет текста, непрозрачная подложка, слои поверх неё снизу вверх, минимальный контраст)
# Числа сверены с реальным DOM 1366x900 и с покомпонентным смешиванием.
PAIRS = [
    ("product badge caption", "#ffffff", "--persimmon-d", [], 4.5),
    ("promo heading", "--quince-l", "--leaf-d", [("--persimmon", 0.36)], 3.0),
    ("promo body", "#eae2d7", "--leaf-d", [("--persimmon", 0.36)], 4.5),
    ("season month chip", "--parch", "--leaf-d", [], 4.5),
    ("map placeholder hint", "--map-ink", "#e9e3d6", [("--leaf", 0.16)], 4.5),
    ("hero ticker line", "--chip-ink", "--fig2", [("--persimmon", 0.28)], 4.5),
    ("hero rating number", "--quince-hi", "--fig2", [("--persimmon", 0.28), ("#ffffff", 0.10)], 4.5),
    ("basket composition chips", "--chip-ink", "--fig2", [("--persimmon", 0.26)], 4.5),
    ("muted body copy", "--muted", "--parch", [], 4.5),
    ("muted copy on surface", "--muted", "--surface", [], 4.5),
    ("accent link on paper", "--persimmon-d", "--parch", [], 4.5),
    # По замерам с реальных пикселей зерно и виньетка съедают светимость бумаги:
    # подпись .overline лежит на #f1e8da, а не на токене --parch.
    ("accent label on grained paper", "--persimmon-d", "#f1e8da", [], 4.5),
    ("footer links", "#e6dcd3", "--fig", [], 4.5),
    ("primary button label", "#2b1a06", "--persimmon", [], 4.5),
    ("whatsapp button label", "#062718", "#22c55e", [], 4.5),
]

# Блик на бейдже — прозрачный белый слой поверх подписи. Считаем его по тому же
# alpha, что лежит в CSS, иначе гейт расходится с картинкой.
_sheen = re.search(r"\.p-badge::after\{[^}]*rgba\(255,\s*255,\s*255,\s*([.\d]+)\)", CSS_MAIN)
if not _sheen:
    SHEEN = 0.0
    ERR.append("контракт бейджа: блик .p-badge::after не найден — светлую полосу над подписью нечем проверить")
else:
    SHEEN = float(_sheen.group(1))
    if SHEEN > 0.20:
        ERR.append(f"блик бейджа rgba(255,255,255,{SHEEN:g}) светлее 0.20: белая подпись на пике блика уходит под 4.5")
    PAIRS.append(("badge caption under sheen", "#ffffff", "--beet", [("#ffffff", SHEEN)], 4.5))
for label, fg, base, over, need in PAIRS:
    rt = ratio(col(fg), fold(base, over))
    if rt < need:
        ERR.append(f"contrast {label}: {rt:.2f} < {need}")

RULE_CONTRACT = [
    (".p-badge", ["var(--persimmon-d)"], "badge gradient lightened back onto persimmon"),
    (".promo", ["var(--leaf-d)"], "promo block no longer uses the dark produce green"),
    (".month.on", ["var(--leaf-d)"], "active month chip no longer uses the dark produce green"),
    (".hero-rating b", ["var(--quince-hi)"], "rating number lost its brightened token"),
    (".compose span", ["var(--chip-ink)"], "composition chips lost their readable ink"),
    (".hero-ticker", ["var(--chip-ink)"], "ticker line lost its readable ink"),
    (".map-ph", ["var(--map-ink)"], "map placeholder hint lost its ink"),
]
for sel, needles, why in RULE_CONTRACT:
    m = re.search(re.escape(sel) + r"\s*\{([^}]*)\}", CSS_MAIN)
    if not m:
        ERR.append(f"contrast contract: rule {sel} not found ({why})")
    elif any(n not in m.group(1) for n in needles):
        ERR.append(f"contrast contract broken at {sel}: {why}")
for tok in ("--leaf-d", "--map-ink", "--chip-ink", "--quince-hi", "--ring", "--ring-dark"):
    if tok not in VARS:
        ERR.append(f"contrast contract: token {tok} missing from :root")

# Контракт видимого фокуса: одно кольцо на весь сайт, вариант для тёмных плоскостей,
# и никто не имеет права гасить outline.
fv = re.search(r":focus-visible\{([^}]*)\}", CSS_MAIN)
if not fv:
    ERR.append("no :focus-visible ring contract rule")
else:
    fm = re.search(r"outline:\s*(\d+)px\s+solid\s+var\((--[\w-]+)\)", fv.group(1))
    if not fm:
        ERR.append(":focus-visible contract is not a solid outline of a colour token")
    else:
        if int(fm.group(1)) < 3:
            ERR.append(f"focus ring thinner than 3px: {fm.group(1)}px")
        if fm.group(2) != "--ring":
            ERR.append("focus ring must use the --ring token, not " + fm.group(2))
dark_ring = " ".join(re.findall(r"([^{}]*:focus-visible)\{outline-color:var\(--ring-dark\)\}", CSS_MAIN))
DARK_SCOPES = (".hero", ".promo", ".p-media", ".sec-dark", ".site-foot", "#lightbox")
if not dark_ring:
    ERR.append("no light focus ring for dark surfaces (outline-color:var(--ring-dark))")
else:
    lost = [s for s in DARK_SCOPES if s + " :focus-visible" not in dark_ring]
    if lost:
        ERR.append("dark surfaces without the light focus ring: " + repr(lost))
if not re.search(r"input:focus-visible\{outline:3px solid var\(--ring\)", CSS_MAIN):
    ERR.append("the search field lost its own focus ring rule (it sits inside a pill wrapper)")
dead_ring = re.findall(r"[^{}]{0,70}outline\s*:\s*(?:none|0)\s*[;}]", CSS_MAIN)
if dead_ring:
    ERR.append("outline:none/0 kills a focus ring: " + repr([d.strip()[-56:] for d in dead_ring[:3]]))
# WCAG 1.4.11: граница фокуса обязана давать 3:1 к фону, на котором её видят.
for tok, bgs in (("--ring", (("paper", "--surface"), ("parchment", "--parch"))),
                 ("--ring-dark", (("fig", "--fig"), ("fig2", "--fig2"), ("fig3", "--fig3")))):
    for label, bg in bgs:
        rt = ratio(col(tok), col(bg))
        if rt < 3.0:
            ERR.append(f"contrast focus ring {tok} on {label}: {rt:.2f} < 3.0 (WCAG 1.4.11)")

# --- Гейт «кольцо доезжает до всех сторон» ------------------------------------
# Зеркало пиксельной проверки fs_focus3: outline рисуется СНАРУЖИ border-box'а
# (3px + offset 3px = 6px), а любой ancestor с overflow режет его. Either у
# клиппера запас под кольцо, либо кольцо вписано внутрь самого элемента.
def css_last_decl(sel, prop):
    """Значение свойства из последнего выигрывающего правила (каскад = порядок в файле)."""
    for body in reversed(re.findall(r"(?<![\w-])" + re.escape(sel) + r"\{([^{}]*)\}", CSS_MAIN)):
        d = re.search(r"(?:^|;)\s*" + re.escape(prop) + r":([^;]*)", body)
        if d:
            return d.group(1).strip()
    return None

SIDES = ("top", "right", "bottom", "left")

def css_px4(value):
    # 'padding:0' и 'margin:0 -7px' — те же 0px; без подмены нулевой шортханд более
    # специфичного правила вообще не доходил до сравнения каскада.
    v = re.sub(r"(?<![\w.%-])0(?![\w.%])", "0px", value or "")
    n = [float(x) for x in re.findall(r"(-?[\d.]+)px", v)]
    if len(n) == 1:
        n = n * 4
    elif len(n) == 2:
        n = [n[0], n[1], n[0], n[1]]
    elif len(n) == 3:
        n = [n[0], n[1], n[2], n[1]]
    return n if len(n) == 4 else []

def css_spec(sel):
    """Специфичность: id / (классы, атрибуты, псевдоклассы) / элементы."""
    n_id = len(re.findall(r"#[\w-]+", sel))
    n_cls = len(re.findall(r"\.[\w-]+|\[[^\]]*\]|:[\w-]+", sel))
    n_el = len(re.findall(r"(?<![\w.#:-])[a-z][\w-]*", sel))
    return n_id * 100 + n_cls * 10 + n_el

def css_sides(chain, prop):
    """{сторона: (ключ, значение)} победившего каскада для элемента, описанного цепью
    chain ('.gal .swiper-wrapper'). Победитель — (специфичность, порядок в файле), а не
    порядок сам по себе: иначе правило html.swiper-on .gal .swiper-wrapper{padding-bottom:0}
    обходит запись .gal .swiper-wrapper{padding:7px} в браузере, а гейт про это молчит —
    ровно та ловушка, что срезала кольцо плиток галереи снизу (замер фокуса, 390/1440)."""
    eff = {}
    def win(side, key, val):
        prev = eff.get(side)
        if prev is None or key > prev[0]:
            eff[side] = (key, val)
    for ri, m in enumerate(re.finditer(r"([^{}]+)\{([^{}]*)\}", CSS_MAIN)):
        sels, body = m.group(1), m.group(2)
        if sels.lstrip().startswith("@"):
            continue
        for s in (" ".join(x.split()) for x in sels.split(",")):
            if s != chain and not s.endswith(" " + chain):
                continue
            key = (css_spec(s), ri)
            decls = dict(re.findall(r"([a-z-]+)\s*:\s*([^;]*)", body))
            if prop in decls:
                n = css_px4(decls[prop])
                if len(n) == 4:
                    for side, v in zip(SIDES, n):
                        win(side, key, v)
            for side in SIDES:
                v = decls.get(prop + "-" + side)
                if v is not None:
                    n = css_px4(v)
                    win(side, key, n[0] if n else 0.0)
    return eff

def css_side_span(chain, prop):
    """Четыре победившие стороны или None, если каскад закрывает не всё."""
    eff = css_sides(chain, prop)
    return [eff[s][1] for s in SIDES] if len(eff) == 4 else None

# Скролл-рельсы режут по padding-боксу: 6px запаса обязано остаться на каждой из четырёх
# сторон ПОСЛЕ каскада — иначе кольцо режет правило, которого гейт не видел.
for chain, why in ((".pills", "ряд фильтров"), (".months", "ряд месяцев"),
                   (".lb-thumbs", "миниатюры лайтбокса"), (".gal .swiper-wrapper", "плитки галереи")):
    sides = css_side_span(chain, "padding")
    if sides is None or min(sides) < 6:
        ERR.append(f"фокус-кольцо обрежется в {chain} ({why}): запас по худшей стороне {None if sides is None else min(sides)}px, нужно >=6px")
# Галерея: .gal не скроллится, но режет по своему боксу — клиппинг расширяем маргином
# наружу, а плитки держим на прежних координатах padding'ом внутреннего wrapper.
gal_m = css_side_span(".gal", "margin")
if gal_m is None or max(gal_m) > -6:
    ERR.append(f"фокус-кольцо плитки обрежет .gal: margin по лучшей стороне {None if gal_m is None else max(gal_m)}px, нужно <=-6px")
# Кольцо прижатому к краю контейнера элементу рисуем ВНУТРИ border-box'а.
for sel, why in ((".step button", "счётчик"), (".faq summary", "строка FAQ"), (".skip", "skip-ссылка")):
    off = css_last_decl(sel + ":focus-visible", "outline-offset")
    if not off or not off.startswith("-"):
        ERR.append(f"фокус-кольцо {sel} ({why}) обязано быть вписанным (outline-offset отрицательный), сейчас {off!r}")
# Тап-цель точки пагинации галереи: WCAG 2.5.8 требует не меньше 24×24 CSS px.
bw, bh = css_last_decl(".gal-dots .swiper-pagination-bullet", "width"), css_last_decl(".gal-dots .swiper-pagination-bullet", "height")
if not bw or not bh or float(re.sub(r"[^\d.]", "", bw) or 0) < 24 or float(re.sub(r"[^\d.]", "", bh) or 0) < 24:
    ERR.append(f"тап-цель точки пагинации меньше 24px: {bw}×{bh} (WCAG 2.5.8)")
if not re.search(r"\.gal-dots \.swiper-pagination-bullet::before\{[^}]*background:var\(--fig\)", CSS_MAIN):
    ERR.append("точка пагинации потеряла кружок на ::before: 24px бокс станет серым квадратом")

# --- Гейт геометрии иконок ---------------------------------------------------
# Пороги сняты с замера живых пикселей (headless Chrome, растер 16/20 px) и
# пересчитаны офлайн тем же движком: icon_geom воспроизводит те же числа, поэтому
# CI кусается без браузера. Каждый пункт — про то, что видно глазом, а не про вкус.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import icon_geom as IG

MIN_SUBLEN = 4.0      # короче — это точка, а не штрих: глаз читает мусор
MIN_COMP16 = 10       # связный кусок силыэта на 16 px меньше — обрывок
INK_LO, INK_HI = 0.05, 0.36   # доля залитых пикселей на 20 px: воздух или каша
ALPHA_FLOOR = 0.45    # средняя плотность чернил вдоль осевой линии на 16 px
DEV_STROKE_FLOOR = 1.30       # устройств-пикселей в самом мелком реальном размере
IOU_CAP = 0.55        # выше — два глифа неотличимы друг от друга
# Стрелки «назад/вперёд» и «−/+» зеркальны по смыслу и обязаны быть похожи.
TWIN_OK = {frozenset(("i-left", "i-right")), frozenset(("i-minus", "i-plus"))}

ic_rule = re.search(r"\.ic\{([^}]*)\}", CSS_MAIN)
ic_sw = None
if not ic_rule:
    ERR.append("no .ic base rule: icon stroke contract cannot be measured")
else:
    body = ic_rule.group(1).replace(" ", "")
    m = re.search(r"stroke-width:([\d.]+)", body)
    if not m:
        ERR.append(".ic lost stroke-width: sprite inherits it, glyphs go hairline")
    else:
        ic_sw = float(m.group(1))
    for need in ("stroke:currentColor", "fill:none", "stroke-linecap:round", "stroke-linejoin:round"):
        if need not in body:
            ERR.append(f".ic lost {need}: every icon in the sprite renders wrong without it")
    sizes = sorted({float(w) for sel, b in re.findall(r"([^{}]+)\{([^}]*)\}", CSS_MAIN)
                    for s in sel.split(",")
                    if re.search(r"(^|[\s>+~])\.ic(\b|$)", s.strip())
                    for w in re.findall(r"(?<![\w-])width:(\d+(?:\.\d+)?)px", b)})
    if not sizes:
        ERR.append("no .ic host sizes found (blind)")
    elif ic_sw and ic_sw * min(sizes) / 24.0 < DEV_STROKE_FLOOR:
        ERR.append("icon stroke %.2f px device at %gpx, floor %.2f"
                   % (ic_sw * min(sizes) / 24.0, min(sizes), DEV_STROKE_FLOOR))

syms = IG.load_symbols(html)
if len(syms) < 20:
    ERR.append("icon geometry scan blind")
masks, geo = {}, {}
for sid, s in sorted(syms.items()):
    span = max(s["box"])
    els = s["els"]
    els2 = [(t, dict(a)) for t, a in els]
    for t, a in els2:
        a.setdefault("fill", "none")
    mixed = [t for t, a in els2
             if a.get("fill", "none") not in ("none", "") and a.get("stroke") != "none"]
    if mixed:
        ERR.append(f"{sid}: element {mixed} is both filled and stroked (base .ic paints an outline over it)")
    g = IG.glyph_metrics(els2, span, ic_sw or 2.0)
    geo[sid] = g
    stroked_any = any(a.get("stroke") != "none" for t, a in els2)
    if g["minlen"] < MIN_SUBLEN:
        ERR.append(f"{sid}: stroke shorter than {MIN_SUBLEN} user units ({g['minlen']})")
    small = [c for c in g["c16"] if c < MIN_COMP16]
    if small:
        ERR.append(f"{sid}: fragment(s) of {small} px at 16px")
    if g["gaps"]:
        ERR.append(f"{sid}: two stroke ends left {g['gaps']} apart — one line drawn as two")
    if stroked_any:
        if not (INK_LO <= g["ink20"] <= INK_HI):
            ERR.append(f"{sid}: ink weight {g['ink20']} outside {INK_LO}..{INK_HI} at 20px")
        if g["alpha16"] < ALPHA_FLOOR:
            ERR.append(f"{sid}: stroke alpha {g['alpha16']} below {ALPHA_FLOOR} at 16px (hairline)")
    masks[sid] = IG.crop_norm([[1 if v >= 0.5 else 0 for v in row]
                               for row in IG.raster_float(els2, 40, span, ic_sw or 2.0)[0]], n=32)

ids = sorted(masks)
twins = []
for i, a in enumerate(ids):
    for b in ids[i + 1:]:
        v = IG.best_iou(masks[a], masks[b])
        if v > IOU_CAP and frozenset((a, b)) not in TWIN_OK:
            twins.append((round(v, 3), a, b))
for v, a, b in sorted(twins, reverse=True):
    ERR.append(f"icons {a}/{b} are the same silhouette (IoU {v} > {IOU_CAP})")

# ---- Темы: переключатель, слой второй темы, контраст обеих палитр ----
TCSS = ROOT / "css" / "themes.css"
THEME_KEY = "fd.theme.v1"
if not TCSS.exists():
    ERR.append("нет css/themes.css: второй теме негде жить")
else:
    tcss = TCSS.read_text(encoding="utf-8")
    mm = re.search(r"\[data-theme=market\]\s*\{([^}]*)\}", tcss)
    if not mm:
        ERR.append("тема market не объявлена блоком [data-theme=market]{…}")
        MVARS = {}
    else:
        blk = mm.group(1)
        MVARS = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", blk))
        missed = sorted(set(VARS) - set(MVARS))
        if missed:
            ERR.append("тема market не переопределяет цвета базовой палитры: " + repr(missed[:8]))
        raw = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+)", blk))
        sloppy = sorted(t for t in set(VARS) & set(raw) if not re.fullmatch(r"#[0-9a-fA-F]{6}", raw[t].strip()))
        if sloppy:
            ERR.append("в теме market токен(ы) не 6-ричный hex: " + repr(sloppy[:8]))
        # Мёртвые селекторы слоя: класс обязан жить в разметке или в базовом CSS.
        src_all = html + CSS_MAIN + (ROOT / "js" / "main.js").read_text(encoding="utf-8")
        dead = sorted({c for sel in re.findall(r"(\[data-theme=market\][^{}]*)\{", tcss)
                       for c in re.findall(r"\.([A-Za-z][\w-]*)", sel)
                       if not re.search(r"[\"'\s.:-]" + re.escape(c) + r"\b", src_all)})
        if dead:
            ERR.append("тема market нацелена на классы, которых нет в разметке: " + repr(dead[:8]))

    # Кольцо фокуса на тёмной доске бара: базовый --ring #7a2410 даёт на ней 1.7:1 (замер
    # fs_focus3), поэтому светлое кольцо обязаны получать предметы бара. Мобильная .nav —
    # бумажная панель, на ней верен базовый --ring, и ловить её в этом правиле нельзя.
    bar_ring = " ".join(re.findall(r"([^{}]*:focus-visible)\{outline-color:var\(--ring-dark\)\}", tcss))
    lost_bar = [s for s in (".site-head .logo", ".site-head .cart-btn", ".site-head .burger", ".site-head .head-call")
                if "[data-theme=market] " + s not in bar_ring]
    if lost_bar:
        ERR.append("тема market: предметы бара без светлого фокус-кольца: " + repr(lost_bar))
    # Ссылки меню светлеют кольцом только в баре (>=769px). Ниже — бумажная панель, и там
    # кремовое кольцо на кремовом фоне исчезает, поэтому правило обязано жить под медиа-страхом.
    flat = re.sub(r"\s+", "", tcss)
    if "@media(min-width:769px){[data-theme=market].nava:focus-visible{outline-color:var(--ring-dark)}}" not in flat:
        ERR.append("тема market: кольцо ссылок .nav обязано светлеть только в баре (media min-width:769px)")
    if flat.count("[data-theme=market].nava:focus-visible{outline-color:var(--ring-dark)}") > 1:
        ERR.append("тема market: второе светлое кольцо для .nav — на бумажной панели оно невидимо")

    # Контракт второй палитры — те же поверхности, что и в базовой таблице.
    # Бар шапки в market — доска rgba(36,23,8,.86); по замеру пикселей светимость
    # полосы даёт #2a1b0d, а не плоский --fig, поэтому считаем от замера.
    BAR_MKT = "#2a1b0d"
    PAIRS_MARKET = [
        ("header brand on the board", "--parch", BAR_MKT, [], 3.0),
        ("header nav on the board", "--parch", BAR_MKT, [], 4.5),
        ("header cart icon on the board", "--quince-hi", BAR_MKT, [], 4.5),
        ("header burger on the board", "--quince-hi", BAR_MKT, [], 3.0),
        ("header CTA label on the board", "--parch", BAR_MKT, [], 4.5),
        ("status label on its paper tag", "--fig", "--surface", [], 4.5),
        ("status dot open", "--ok", "--surface", [], 3.0),
        ("status dot shut", "--danger", "--surface", [], 3.0),
        ("badge caption", "#ffffff", "--persimmon-d", [], 4.5),
        ("promo heading", "--quince-hi", "--leaf-d", [("--persimmon", 0.34)], 3.0),
        ("promo body", "#e7dcc9", "--leaf-d", [("--persimmon", 0.34)], 4.5),
        ("active chip ink", "--chip-ink", "--fig2", [], 4.5),
        ("muted body on kraft", "--muted", "--parch", [], 4.5),
        ("accent link on kraft", "--persimmon-d", "--parch", [], 4.5),
        # Тот же поправочный замер, но на крафте: текстура доски темнее токена.
        ("accent label on grained kraft", "--persimmon-d", "#c0a682", [], 4.5),
        ("badge caption under sheen", "#ffffff", "--persimmon-d", [("#ffffff", SHEEN)], 4.5),
        ("primary button label", "#1c1004", "--persimmon", [], 4.5),
        ("hero text on wood", "#f4e8d6", "--fig2", [], 4.5),
        ("footer link", "#eadfce", "--fig", [], 4.5),
        ("estimate value", "--quince-l", "--fig2", [], 3.0),
        ("switcher caption", "#dccbb6", "--fig2", [], 4.5),
    ]
    if MVARS:
        _saved = dict(VARS)
        VARS.update(MVARS)
        for label, fg, base, over, need in PAIRS_MARKET:
            rt = ratio(col(fg), fold(base, over))
            if rt < need:
                ERR.append(f"contrast market {label}: {rt:.2f} < {need}")
        VARS.clear(); VARS.update(_saved)

    # Правила шапки market: бар — тёмная доска, поэтому каждый предмет на баре
    # обязан быть перекрашен явно. Иначе шапка сливается с доской (контраст 1.0),
    # и по одним токенам этого не увидеть.
    HEAD_MKT = [
        (r"\[data-theme=market\] \.site-head \.logo-text\{([^}]*)\}", "var(--parch)", "надпись логотипа"),
        (r"\[data-theme=market\] \.head-live\{([^}]*)\}", "var(--surface)", "этикетка часов"),
        (r"\[data-theme=market\] \.cart-btn\{([^}]*)\}", "var(--quince-hi)", "обводка корзины"),
        (r"\[data-theme=market\] \.burger span\{([^}]*)\}", "var(--quince-hi)", "полоски бургера"),
    ]
    for pat, needle, label in HEAD_MKT:
        hm = re.search(pat, tcss)
        if not hm:
            ERR.append(f"шапка market: правило «{label}» пропало — на тёмной доске предмет станет невидим")
        elif needle not in hm.group(1):
            ERR.append(f"шапка market: «{label}» больше не ссылается на {needle}")

    # Навигация прячется в светлую панель на брейкпоинте базовой темы. Если защита
    # стоит шире, на планшете ссылки останутся тёмными на тёмном баре.
    def _block(css, brace_pos):
        depth = 0
        for k in range(brace_pos, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    return css[brace_pos:k + 1]
        return ""

    nav_bp = next((int(m.group(1)) for m in re.finditer(r"@media\(max-width:(\d+)px\)\{", CSS_MAIN)
                   if ".nav{position:fixed" in _block(CSS_MAIN, m.end() - 1)), None)
    if nav_bp is None:
        ERR.append("не нашли, на какой ширине .nav уходит в панель — гейт ссылок market слепой")
    elif not re.search(r"@media\(min-width:%dpx\)\{\s*\[data-theme=market\] \.nav a\{[^}]*var\(--parch\)" % (nav_bp + 1), tcss):
        ERR.append(f"ссылки market должны быть защищены @media(min-width:{nav_bp + 1}px): ниже "
                   f"{nav_bp}px навигация живёт в светлой панели и просит базовые чернила")

    # Контракт переключателя.
    if 'data-theme="parchment"' not in html:
        ERR.append("на <html> нет дефолтного data-theme=parchment")
    opts = re.findall(r'data-theme-set="([^"]+)"', html)
    if sorted(set(opts)) != ["market", "parchment"]:
        ERR.append(f"переключатель тем предлагает {sorted(set(opts))}, ждали market+parchment")
    if len(opts) != 2:
        ERR.append(f"кнопок смены темы {len(opts)}, а вариантов два")
    if html.count('aria-pressed=') < 2 or 'ts-note' not in html:
        ERR.append("переключатель тем без aria-pressed или без подписи для заказчика")
    note = re.search(r'class="ts-note">([^<]{6,})<', html)
    if not note:
        ERR.append("подпись темы слишком короткая или пропала")
    elif not re.search(r"(согласу|выбер|остав)", note.group(1), re.I):
        ERR.append("подпись у переключателя не обещает заказчику выбор темы: " + note.group(1)[:60])
    tjs = ROOT / "js" / "theme.js"
    if not tjs.exists():
        ERR.append("нет js/theme.js: тема встанет только после первой отрисовки")
    else:
        tj = tjs.read_text(encoding="utf-8")
        if THEME_KEY not in tj:
            ERR.append("js/theme.js не читает " + THEME_KEY)
        tag = re.search(r'<script[^>]*src="js/theme\.js"[^>]*>', html)
        if not tag:
            ERR.append("js/theme.js не подключён")
        elif re.search(r"defer|async|type=.module", tag.group(0)):
            ERR.append("js/theme.js отложен — будет вспышка базовой темы")
        elif tag.start() > html.find('<link rel="stylesheet"'):
            ERR.append("js/theme.js идёт после стилей — атрибут темы встанет поздно")
    mj = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
    if THEME_KEY not in mj:
        ERR.append("main.js не сохраняет выбор темы в " + THEME_KEY)
    if not re.search(r"writeLS\(\s*THEME_KEY\s*,", mj):
        ERR.append("main.js не сохраняет выбор темы: нет writeLS(THEME_KEY, …)")
    # $$ и writeLS живут внутри IIFE: обработчик снаружи кинет ReferenceError на клике.
    iife_end = mj.find("})();if('serviceWorker'")
    bind = mj.find("$$('[data-theme-set]').forEach(function(b){b.addEventListener")
    if iife_end < 0 or bind < 0 or bind > iife_end:
        ERR.append("main.js вешает кнопки темы вне IIFE — $$ и writeLS там не видны")
    if "data-theme-set" not in mj:
        ERR.append("main.js не вешает обработчик на кнопки темы")
    if not re.search(r"@media\s+print\s*\{[^}]*\.theme-switch\s*\{[^}]*display\s*:\s*none", tcss):
        ERR.append("переключатель темы попадёт на печать")

for n in NOTES: print("NOTE:", n)
if ERR:
    print("FAIL:")
    for e in ERR: print(" -", e)
    sys.exit(1)
print("ALL CHECKS PASSED")