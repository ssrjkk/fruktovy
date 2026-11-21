#!/usr/bin/env python3
"""Сборка витрины «Фруктовый дворец».

Из читаемых источников (index.html, css/style.css, js/*.js) собирает то, чего в
репозитории нет и не должно быть: шрифты (OFL), фотографии (Pexels), og-превью,
PWA-иконки, каталожный JSON-LD, прекеширующий список SW, минифицированные CSS/JS.

Запуск:
    python tools/build.py                 — собрать ассеты; читаемые источники остаются как есть
    python tools/build.py --minify        — то же плюс минификация css/js на месте
    python tools/build.py --minify-only   — ничего не качать, только штампы и минификация

Минификацию на месте включаем только в CI: рабочее дерево она необратимо съедает,
а проверяющие гейты умеют читать и собранный вид. CI идёт двумя шагами
(build → тесты и мутации → --minify-only), чтобы артефакт на Pages собирался
после того, как гейты доказали, что кусаются, и без второй качки фото.

Зависимости: pip install pillow rcssmin rjsmin quickjs
"""
import argparse, datetime, io, json, re, ssl, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "assets"; IMG = A / "img"; FONTS = A / "fonts"
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

# Палитра market (data-theme="market" — тема по умолчанию) из css/style.css.
# og.png и иконки рисуются именно в ней: превью ссылается на него человек,
# открывший вкладку в WhatsApp, а не посетитель другой палитры.
CREAM, INK, BRAND, ACCENT, CEDAR = (250, 245, 236), (34, 27, 21), (27, 77, 62), (200, 75, 40), (140, 94, 60)

SITE_URL = "https://ssrjkk.github.io/fruktovy/"

# Только те гарнитуры, что реально названы в css/style.css, и только те веса,
# которые там объявлены: лишний файл — это байты, уезжающие каждому гостю.
FONTS_MAP = {}
for w in (400, 600, 700, 800):
    for sub in ("cyrillic", "latin"):
        FONTS_MAP[f"manrope-{sub}-{w}.woff2"] = ("@fontsource/manrope", "manrope", sub, w, "normal")
for w in (600, 700):
    for style in ("normal", "italic"):
        for sub in ("cyrillic", "latin"):
            FONTS_MAP[f"cormorant-garamond-{sub}-{w}-{style}.woff2"] = (
                "@fontsource/cormorant-garamond", "cormorant-garamond", sub, w, style)
FONT_NAMES = {"manrope": "Manrope", "cormorant-garamond": "Cormorant Garamond"}
RANGES = {
    "cyrillic": "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116",
    "latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
             "U+2000-206F, U+20AC, U+2122, U+2212, U+FEFF, U+FFFD",
}

# Размеры сняты с вызовов pexels(...) в js/app.js и со статичных <img> в index.html:
# плитка каталога, крупные фото подглядывания, миниатюры корзины/избранного, галерея.
PRODUCT_SIZES = [(640, 480), (900, 675), (240, 180), (200, 200), (140, 140), (120, 120)]
GALLERY_SIZES = [(640, 480), (1200, 900)]
OG_HERO = (31665655, 1200, 900)

# Всё, что обязано быть в офлайн-кэше оболочки. Список пишется в sw.js на сборке,
# чтобы он не разъезжался с реальным набором файлов.
SW_CORE = ["./", "./index.html", "./404.html", "./css/style.css", "./assets/fonts.css",
           "./js/app-head.js", "./js/data.js", "./js/app.js", "./assets/logo.svg",
           "./manifest.webmanifest", "./assets/icon-192.png", "./assets/icon-512.png"]


def fetch(url, tries=4, timeout=30):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout, context=CTX) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"{url} -> {last}")


def mirrors(path):
    return [f"https://cdn.jsdelivr.net/npm/{path}", f"https://unpkg.com/{path}"]


def load_data():
    """Продукты и галерею читаем из js/data.js тем же движком, что и браузер."""
    import quickjs
    src = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
    ctx = quickjs.Context()
    raw = ctx.eval(src + "\n;JSON.stringify({PRODUCTS: PRODUCTS, GALLERY: GALLERY_ITEMS});")
    return json.loads(raw)


def font_path(size, serif=False):
    base = "DejaVuSerif-Bold.ttf" if serif else "DejaVuSans-Bold.ttf"
    cands = [base, "/usr/share/fonts/truetype/dejavu/" + base,
             "C:/Windows/Fonts/" + ("georgiab.ttf" if serif else "arialbd.ttf")]
    for n in cands:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def crown(d, cx, cy, w):
    h = w * 0.55
    d.polygon([(cx - w / 2, cy + h / 2), (cx - w / 2, cy - h / 6), (cx - w / 4, cy + h / 8),
               (cx, cy - h / 2), (cx + w / 4, cy + h / 8), (cx + w / 2, cy - h / 6), (cx + w / 2, cy + h / 2)],
              fill=(212, 155, 42))


def gradient(img, top, bottom):
    d = ImageDraw.Draw(img); w, h = img.size
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def placeholder(key, w, h):
    img = Image.new("RGB", (w, h)); gradient(img, BRAND, INK); d = ImageDraw.Draw(img)
    crown(d, w / 2, h * 0.42, w * 0.16)
    d.text((w / 2, h * 0.62), str(key), font=font_path(max(18, w // 24)), fill=CREAM, anchor="mm")
    return img


def photo_job(args):
    pid, w, h = args
    url = (f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg"
           f"?auto=compress&cs=tinysrgb&fit=crop&w={w}&h={h}")
    try:
        im = Image.open(io.BytesIO(fetch(url)))
        if im.size != (w, h):
            im = im.resize((w, h))
        im.convert("RGB").save(IMG / f"{pid}-{w}x{h}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
        return None
    except Exception as e:
        placeholder(pid, w, h).save(IMG / f"{pid}-{w}x{h}.jpg", "JPEG", quality=82)
        return f"{pid}-{w}x{h}: {str(e)[:70]}"


def build_photos():
    data = load_data()
    jobs = {OG_HERO}
    jobs.update((p["photo"], w, h) for p in data["PRODUCTS"] for w, h in PRODUCT_SIZES)
    jobs.update((g["photo"], w, h) for g in data["GALLERY"] for w, h in GALLERY_SIZES)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fails = [r for r in ex.map(photo_job, sorted(jobs)) if r]
    print(f"photos: {len(jobs) - len(fails)}/{len(jobs)} ok" + (f" PLACEHOLDERS: {fails}" if fails else ""))
    # Плейсхолдер — это не «почти фото», а чужой продукт: градиент с номером Pexels
    # вместо снимка. Молча залить его в прод опаснее, чем покраснить CI.
    if fails:
        raise SystemExit(f"PHOTO FAIL: {len(fails)}/{len(jobs)} not downloaded")
    want = {f"{pid}-{w}x{h}.jpg" for pid, w, h in jobs}
    # Снятые позиции и старые размеры: файл, который никто не зовёт, уезжает в прод мёртвым весом.
    called = set()
    for f in ("index.html", "404.html", "sw.js", "manifest.webmanifest"):
        fp = ROOT / f
        if fp.exists():
            called |= set(re.findall(r"[\w./-]*img/(\d+-\d+x\d+\.jpg)", fp.read_text(encoding="utf-8")))
    for f in (ROOT / "css" / "style.css", *(ROOT / "js").glob("*.js")):
        if f.exists():
            called |= set(re.findall(r"(\d+-\d+x\d+\.jpg)", f.read_text(encoding="utf-8")))
    stale = [q for q in IMG.glob("*.jpg") if q.name not in want and q.name not in called]
    for q in stale:
        q.unlink()
    if stale:
        print(f"photos: убрано лишнего {len(stale)} шт.")
    return sorted(want)


def font_job(item):
    local, (pkg, family, sub, w, style) = item
    for u in mirrors(f"{pkg}@5/files/{family}-{sub}-{w}-{style}.woff2"):
        try:
            (FONTS / local).write_bytes(fetch(u, tries=2)); return None
        except Exception:
            continue
    return local


def build_fonts():
    with ThreadPoolExecutor(max_workers=6) as ex:
        fails = [r for r in ex.map(font_job, FONTS_MAP.items()) if r]
    if fails:
        raise SystemExit(f"FONT FAIL: {fails}")
    faces = []
    for local, (pkg, family, sub, w, style) in FONTS_MAP.items():
        name = FONT_NAMES[family]
        faces.append(
            f'@font-face{{font-family:"{name}";font-style:{style};font-weight:{w};font-display:swap;'
            f'src:url("fonts/{local}") format("woff2");unicode-range:{RANGES[sub]}}}')
    (A / "fonts.css").write_text("\n".join(faces) + "\n", encoding="utf-8")
    print(f"fonts: {len(FONTS_MAP)}/{len(FONTS_MAP)} ok (OFL) + assets/fonts.css")


def build_catalog_ld():
    """Список позиций поисковик читает из JSON-LD, а не из отрисованного каталога."""
    data = load_data()
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": "Ассортимент «Фруктового дворца»",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p["name"]}
                              for i, p in enumerate(data["PRODUCTS"])]}
    idx = ROOT / "index.html"; html = idx.read_text(encoding="utf-8")
    html, n = re.subn(r'(<script type="application/ld\+json" id="ld-catalog">).*?(</script>)',
                      lambda m: m.group(1) + json.dumps(ld, ensure_ascii=False) + m.group(2), html, flags=re.S)
    if n != 1:
        raise SystemExit("ld-catalog marker not found in index.html")
    idx.write_text(html, encoding="utf-8")
    print(f"catalog JSON-LD: {len(data['PRODUCTS'])} позиций внедрено в index.html")


def build_og():
    img = Image.new("RGB", (1200, 630)); hero = IMG / f"{OG_HERO[0]}-{OG_HERO[1]}x{OG_HERO[2]}.jpg"
    if hero.exists():
        bg = Image.open(hero).convert("RGB").resize((1200, 675)).crop((0, 22, 1200, 652))
        bg = ImageEnhance.Brightness(bg).enhance(0.42); img.paste(bg, (0, 0))
        ov = Image.new("RGBA", (1200, 630), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        for x in range(1200):
            od.line([(x, 0), (x, 630)], fill=(INK[0], INK[1], INK[2], int(210 * max(0, 1 - x / 900))))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    else:
        gradient(img, BRAND, INK)
    d = ImageDraw.Draw(img); crown(d, 150, 92, 104)
    d.text((92, 140), "Фруктовый дворец", font=font_path(64, serif=True), fill=CREAM)
    d.text((95, 258), "Фрукты · Овощи · Орехи · Сухофрукты · Специи", font=font_path(34), fill=(212, 155, 42))
    d.text((95, 318), "Соберите пакет на сайте — продавец пришлёт расчёт в WhatsApp",
           font=font_path(28), fill=CREAM)
    for y, txt, bg in [(430, "СПб, Сытнинская ул., 12 · м. Горьковская", CREAM),
                       (520, "Ежедневно 08:00–21:00 · 4,7 на Яндекс Картах", (212, 155, 42))]:
        f = font_path(26); w = d.textlength(txt, font=f)
        d.rounded_rectangle([92, y, 92 + w + 56, y + 66], 33, fill=bg)
        d.text((120, y + 14), txt, font=f, fill=INK)
    # 256 цветов без дизеринга: 622 KB -> ~250 KB, текст не мылится, а превью ползут краулеры.
    img.quantize(colors=256, method=Image.FASTOCTREE, dither=0).save(A / "og.png", optimize=True)
    print(f"og.png ok ({(A / 'og.png').stat().st_size // 1024} KB)")


def build_icons_pwa():
    for s in (192, 512):
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, s - 1, s - 1], int(s * 0.22), fill=BRAND)
        crown(d, s / 2, s * 0.30, s * 0.52)
        r = s * 0.21; cx, cy = s / 2, s * 0.66
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT)
        d.line([cx, cy - r, cx + r * 0.25, cy - r * 1.4], fill=CEDAR, width=max(3, int(r * 0.12)))
        d.ellipse([cx + r * 0.15, cy - r * 1.6, cx + r * 0.95, cy - r * 1.15], fill=(121, 194, 103))
        img.save(A / f"icon-{s}.png", optimize=True)
    print("pwa icons ok")


def build_sw():
    """Версия оболочки + прекешируемый список: кэшируем витрину, а не устаревший набор файлов."""
    sw = ROOT / "sw.js"
    core = ", ".join(f'"{p}"' for p in SW_CORE)
    text, n1 = re.subn(r'var CORE = \[[^\]]*\];', f"var CORE = [{core}];", sw.read_text(encoding="utf-8"))
    if n1 != 1:
        raise SystemExit("CORE list marker not found in sw.js")
    sw.write_text(text, encoding="utf-8")


def finalize(minify=True):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    sw = ROOT / "sw.js"
    sw.write_text(re.sub(r'"fd-[^"]+"', f'"fd-{stamp}"', sw.read_text(encoding="utf-8")), encoding="utf-8")
    sm = ROOT / "sitemap.xml"
    sm.write_text(re.sub(r"<lastmod>[^<]+</lastmod>", f"<lastmod>{datetime.date.today().isoformat()}</lastmod>",
                         sm.read_text(encoding="utf-8")), encoding="utf-8")
    if minify:
        import rcssmin, rjsmin
        for p in [ROOT / "css" / "style.css", A / "fonts.css"]:
            p.write_text(rcssmin.cssmin(p.read_text(encoding="utf-8")), encoding="utf-8")
        for p in (ROOT / "js").glob("*.js"):
            p.write_text(rjsmin.jsmin(p.read_text(encoding="utf-8")), encoding="utf-8")
        print("minify ok")
    data = load_data()
    credits = ["Фото — Pexels (https://www.pexels.com/license/):"]
    credits += [f"  {p['photo']}: https://www.pexels.com/photo/{p['photo']}/" for p in data["PRODUCTS"]]
    credits += [f"  {g['photo']}: https://www.pexels.com/photo/{g['photo']}/" for g in data["GALLERY"]]
    credits += ["", f"Шрифты — SIL OFL 1.1: {', '.join(sorted(set(FONT_NAMES.values())))} (@fontsource)",
                "Иконки — inline SVG-спрайт в index.html",
                "Виджет рейтинга — Яндекс Карты (iframe, frame-src разрешён CSP)"]
    (A / "CREDITS.txt").write_text("\n".join(credits) + "\n", encoding="utf-8")
    print(f"build id: fd-{stamp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minify", action="store_true",
                    help="собрать ассеты и тут же минифицировать css/js (читаемые источники будут съедены)")
    ap.add_argument("--minify-only", action="store_true",
                    help="только штампы и минификация: в CI ассеты уже собраны предыдущим шагом, "
                         "второй прогон за фото — это лишние полторы сотни запросов к Pexels")
    args = ap.parse_args()
    if args.minify_only:
        files = list(IMG.glob("*.jpg"))
    else:
        for d in (IMG, FONTS):
            d.mkdir(parents=True, exist_ok=True)
        build_fonts(); files = build_photos()
        build_catalog_ld(); build_og(); build_icons_pwa(); build_sw()
    finalize(minify=args.minify or args.minify_only)
    total = sum(p.stat().st_size for p in A.rglob("*") if p.is_file())
    print(f"DONE. assets: {total // 1024} KB, {len(files)} фото")
