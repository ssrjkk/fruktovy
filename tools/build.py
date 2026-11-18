#!/usr/bin/env python3
"""Сборка: vendor-библиотеки + шрифты (OFL) + фото (Pexels) + og/иконки + SEO-каталог
из js/data.js + минификация + версия SW + дата sitemap.
Запуск: python tools/build.py [--no-minify]   Зависимости: pip install pillow rcssmin rjsmin quickjs
"""
import argparse, datetime, io, json, re, ssl, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "assets"; IMG = A / "img"; FONTS = A / "fonts"; VEND = ROOT / "vendor"
CTX = ssl.create_default_context()
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
FIG, FIG_D, GOLD, PERSIMMON, PARCH = (27, 18, 32), (18, 12, 22), (217, 165, 33), (226, 98, 44), (246, 239, 228)

VENDORS = {
    "swiper-bundle.min.js": "swiper@11/swiper-bundle.min.js",
    "swiper-bundle.min.css": "swiper@11/swiper-bundle.min.css",
    "lenis.min.js": "lenis@1/dist/lenis.min.js",
    "gsap.min.js": "gsap@3/dist/gsap.min.js",
    "ScrollTrigger.min.js": "gsap@3/dist/ScrollTrigger.min.js",
}
FONTS_MAP = {}
for w in (400, 500, 600, 700, 800):
    for sub in ("cyrillic", "latin"):
        FONTS_MAP[f"manrope-{sub}-{w}.woff2"] = ("@fontsource/manrope", "manrope", sub, w, "normal")
for w in (600, 700):
    for style in ("normal", "italic"):
        for sub in ("cyrillic", "latin"):
            FONTS_MAP[f"cormorant-garamond-{sub}-{w}-{style}.woff2"] = (
                "@fontsource/cormorant-garamond", "cormorant-garamond", sub, w, style)
# Узкий гротеск для заголовков темы market. Без него «Oswald» в --display
# доезжает только до Windows и Android, а на macOS/iOS заголовки становятся обычным
# Helvetica — рынок на паллетах теряет свой вид. Вес один: в CSS везде 700.
for w in (700,):
    for sub in ("cyrillic", "latin"):
        FONTS_MAP[f"oswald-{sub}-{w}.woff2"] = ("@fontsource/oswald", "oswald", sub, w, "normal")
FONT_NAMES = {"manrope": "Manrope", "cormorant-garamond": "Cormorant Garamond", "oswald": "Oswald"}
RANGES = {
    "cyrillic": "U+0301, U+0400-045F, U+0490-0491, U+04B0-04B1, U+2116",
    "latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2212, U+FEFF, U+FFFD",
}
PRODUCT_SIZES = [(640, 480), (160, 130), (120, 120), (900, 1100)]
GALLERY_SIZES = [(640, 427), (1500, 1000)]
SITE_URL = 'https://ssrjkk.github.io/fruktovy/'
EXTRA_PHOTOS = [(1171170, 900, 1100), (38701943, 620, 520), (678414, 560, 420),
                (38701943, 900, 1200), (27207183, 1280, 720)]


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
    import quickjs
    ctx = quickjs.Context()
    ctx.eval((ROOT / "js" / "data.js").read_text(encoding="utf-8"))
    return json.loads(ctx.eval("JSON.stringify({PRODUCTS: PRODUCTS, GALLERY: GALLERY})"))


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
               (cx, cy - h / 2), (cx + w / 4, cy + h / 8), (cx + w / 2, cy - h / 6), (cx + w / 2, cy + h / 2)], fill=GOLD)


def gradient(img, top, bottom):
    d = ImageDraw.Draw(img); w, h = img.size
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))


def placeholder(key, w, h):
    img = Image.new("RGB", (w, h)); gradient(img, FIG, FIG_D); d = ImageDraw.Draw(img)
    crown(d, w / 2, h * 0.42, w * 0.16)
    d.text((w / 2, h * 0.62), str(key), font=font_path(max(18, w // 24)), fill=PARCH, anchor="mm")
    return img


def photo_job(args):
    pid, w, h = args
    url = f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?auto=compress&cs=tinysrgb&fit=crop&w={w}&h={h}"
    try:
        im = Image.open(io.BytesIO(fetch(url)))
        if im.size != (w, h):
            im = im.resize((w, h))
        im.convert("RGB").save(IMG / f"{pid}-{w}x{h}.jpg", "JPEG", quality=82, optimize=True, progressive=True)
        return None
    except Exception as e:
        placeholder(pid, w, h).save(IMG / f"{pid}-{w}x{h}.jpg", "JPEG", quality=82)
        return f"{pid}-{w}x{h}: {str(e)[:70]}"


def build_photos(data):
    jobs = set(EXTRA_PHOTOS)
    for p in data["PRODUCTS"]:
        jobs.update((p["photo"], w, h) for w, h in PRODUCT_SIZES)
    for g in data["GALLERY"]:
        jobs.update((g["id"], w, h) for w, h in GALLERY_SIZES)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fails = [r for r in ex.map(photo_job, sorted(jobs)) if r]
    print(f"photos: {len(jobs) - len(fails)}/{len(jobs)} ok" + (f" PLACEHOLDERS: {fails}" if fails else ""))
    # Плейсхолдер — это не «почти фото», а другой продукт: градиент с номером Pexels вместо
    # снимка. Молча залить его в прод опаснее, чем покраснить CI: красная сборка перезапускается,
    # а витрина с фейковыми плитками висит, пока кто-то заметит.
    if fails:
        raise SystemExit(f"PHOTO FAIL: {len(fails)}/{len(jobs)} not downloaded")


def dl_job(item):
    local, path = item
    for u in mirrors(path):
        try:
            (VEND / local).write_bytes(fetch(u, tries=2)); return None
        except Exception:
            continue
    return local


def build_vendors():
    with ThreadPoolExecutor(max_workers=6) as ex:
        fails = [r for r in ex.map(dl_job, VENDORS.items()) if r]
    if fails:
        raise SystemExit(f"VENDOR FAIL: {fails}")
    print(f"vendors: {len(VENDORS)}/{len(VENDORS)} ok (self-hosted)")


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


def build_catalog_ld(data):
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "name": "Ассортимент «Фруктового»",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p["name"]}
                              for i, p in enumerate(data["PRODUCTS"])]}
    idx = ROOT / "index.html"; html = idx.read_text(encoding="utf-8")
    html, n = re.subn(r'(<script type="application/ld\+json" id="ld-catalog">).*?(</script>)',
                      lambda m: m.group(1) + json.dumps(ld, ensure_ascii=False) + m.group(2), html, flags=re.S)
    if n != 1:
        raise SystemExit("ld-catalog marker not found in index.html")
    idx.write_text(html, encoding="utf-8")
    print(f"catalog JSON-LD: {len(data['PRODUCTS'])} товаров внедрено в index.html")


def build_qr():
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(SITE_URL); qr.make(fit=True)
    img = qr.make_image(fill_color="#1b1220", back_color="#fffbf4")
    out = A / "qr.png"; img.save(out)
    print(f"qr.png ok ({out.stat().st_size // 1024} KB, v{qr.version})")


def build_og():
    img = Image.new("RGB", (1200, 630)); hero = IMG / "27207183-1280x720.jpg"
    if hero.exists():
        bg = Image.open(hero).convert("RGB").resize((1200, 675)).crop((0, 22, 1200, 652))
        bg = ImageEnhance.Brightness(bg).enhance(0.42); img.paste(bg, (0, 0))
        ov = Image.new("RGBA", (1200, 630), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
        for x in range(1200):
            od.line([(x, 0), (x, 630)], fill=(18, 12, 22, int(200 * max(0, 1 - x / 900))))
        img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    else:
        gradient(img, FIG, FIG_D)
    d = ImageDraw.Draw(img); crown(d, 140, 92, 104)
    d.text((92, 150), "Фруктовый", font=font_path(72, serif=True), fill=PARCH)
    d.text((95, 262), "Каталог · Корзина · Заказ в WhatsApp", font=font_path(36), fill=GOLD)
    d.text((95, 322), "Фрукты · Овощи · Орехи · Сухофрукты · Специи", font=font_path(30), fill=GOLD)
    for y, txt, bg in [(425, "СПб, Сытнинская ул., 12 · м. Горьковская", PARCH),
                       (515, "Ежедневно 08:00–21:00 · 4,7 на Яндекс Картах", GOLD)]:
        f = font_path(26); w = d.textlength(txt, font=f)
        d.rounded_rectangle([92, y, 92 + w + 56, y + 66], 33, fill=bg)
        d.text((120, y + 14), txt, font=f, fill=FIG_D)
    # 256 цветов без дизеринга: 622 KB -> ~250 KB, текст не мылится, а это превью ползут краулеры.
    img.quantize(colors=256, method=Image.FASTOCTREE, dither=0).save(A / "og.png", optimize=True)
    print(f"og.png ok ({(A / 'og.png').stat().st_size // 1024} KB)")


def build_icons_pwa():
    for s in (192, 512):
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, s - 1, s - 1], int(s * 0.22), fill=FIG)
        crown(d, s / 2, s * 0.30, s * 0.52)
        r = s * 0.21; cx, cy = s / 2, s * 0.66
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PERSIMMON)
        d.line([cx, cy - r, cx + r * 0.25, cy - r * 1.4], fill=(107, 67, 16), width=max(3, int(r * 0.12)))
        d.ellipse([cx + r * 0.15, cy - r * 1.6, cx + r * 0.95, cy - r * 1.15], fill=(121, 194, 103))
        img.save(A / f"icon-{s}.png", optimize=True)
    print("pwa icons ok")


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
    credits += [f"  {g['id']}: https://www.pexels.com/photo/{g['id']}/" for g in data["GALLERY"]]
    credits += ["", f"Шрифты — SIL OFL 1.1: {', '.join(FONT_NAMES.values())}",
                "Библиотеки (self-hosted): Swiper (MIT), Lenis (MIT), GSAP + ScrollTrigger (GreenSock standard license)",
                "Иконки — inline SVG-спрайт в index.html",
                f"QR-код (assets/qr.png) — {SITE_URL}, закодирован напрямую (qrcode, MIT)"]
    (A / "CREDITS.txt").write_text("\n".join(credits), encoding="utf-8")
    print(f"build id: fd-{stamp}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--no-minify", action="store_true")
    args = ap.parse_args()
    for d in (IMG, FONTS, VEND):
        d.mkdir(parents=True, exist_ok=True)
    data = load_data()
    build_vendors(); build_fonts(); build_photos(data)
    build_catalog_ld(data); build_qr(); build_og(); build_icons_pwa()
    finalize(minify=not args.no_minify)
    total = sum(p.stat().st_size for p in A.rglob("*") if p.is_file()) + sum(p.stat().st_size for p in VEND.rglob("*") if p.is_file())
    print(f"DONE. assets+vendor: {total // 1024} KB")