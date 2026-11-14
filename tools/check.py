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
if len(faq) != html.count("<details"): ERR.append("FAQ mismatch")

import quickjs
ctx = quickjs.Context()
ctx.eval((ROOT / "js" / "data.js").read_text(encoding="utf-8"))
data = json.loads(ctx.eval("JSON.stringify({PRODUCTS: PRODUCTS, GALLERY: GALLERY})"))
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
for n in NOTES: print("NOTE:", n)
if ERR:
    print("FAIL:")
    for e in ERR: print(" -", e)
    sys.exit(1)
print("ALL CHECKS PASSED")