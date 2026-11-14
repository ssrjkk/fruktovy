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
for cssp in (ROOT / "css" / "style.css", ROOT / "assets" / "fonts.css"):
    if not cssp.exists():
        if not SKIP: ERR.append("missing " + str(cssp))
        continue
    css = cssp.read_text(encoding="utf-8")
    if css.count("{") != css.count("}"): ERR.append(f"CSS braces {cssp.name}")
    for u in re.findall(r'url\("([^"]+)"\)', css):
        if u.startswith("data:"): continue
        if not (cssp.parent / u).resolve().exists() and not SKIP: ERR.append("css url " + u)

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
used = set(re.findall(r'ico\(\'([a-z0-9-]+)\'\)', (ROOT / "js" / "main.js").read_text(encoding="utf-8")))
used.update(re.findall(r'<use href="#i-([a-z0-9-]+)"', html))
if len(symbols) < 20: ERR.append("sprite scan blind")
if used - symbols: ERR.append(f"icons used but not in sprite: {sorted(used - symbols)}")
if symbols - used: ERR.append(f"sprite icons never used: {sorted(symbols - used)}")

# Подсказки по хранению: их иконки лежат в data.js, и до этого блока спрайт для них
# не проверялся вовсе.
gtabs = set(re.findall(r'data-tab="([^"]+)"',
                       re.search(r'id="guideTabs".*?</div>', html, re.S).group(0)))
cat_ids = {c["id"] for c in data["CATS"] if c["id"] not in ("all", "fav")}
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
    ("footer links", "#e6dcd3", "--fig", [], 4.5),
    ("primary button label", "#2b1a06", "--persimmon", [], 4.5),
    ("whatsapp button label", "#062718", "#22c55e", [], 4.5),
]
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
dark_ring = re.search(r"([^{}]*:focus-visible)\{outline-color:var\(--ring-dark\)\}", CSS_MAIN)
DARK_SCOPES = (".hero", ".promo", ".p-media", ".sec-dark")
if not dark_ring:
    ERR.append("no light focus ring for dark surfaces (outline-color:var(--ring-dark))")
else:
    lost = [s for s in DARK_SCOPES if s + " :focus-visible" not in dark_ring.group(1)]
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

for n in NOTES: print("NOTE:", n)
if ERR:
    print("FAIL:")
    for e in ERR: print(" -", e)
    sys.exit(1)
print("ALL CHECKS PASSED")