#!/usr/bin/env python3
"""Доказательство, что каждый новый гейт tools/check.py кусается: мутируем файл,
запускаем гейт, требуем конкретную ошибку, восстанавливаем байты из git."""
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FILES = ["index.html", "sw.js", "css/style.css", "assets/og.png", "js/data.js", "js/main.js"]


def _io(fn, *a, **kw):
    """Файл секунду может быть занят Chrome из только что законченного прогона гейта."""
    for _ in range(40):
        try:
            return fn(*a, **kw)
        except OSError:
            time.sleep(0.25)
    raise SystemExit(f"file busy: {a[0] if a else fn}")


def snapshot():
    return {f: _io((ROOT / f).read_bytes) for f in FILES}


def restore(state):
    for f, b in state.items():
        _io((ROOT / f).write_bytes, b)


def mutate(path, old, new, count=1):
    p = ROOT / path
    t = _io(p.read_text, encoding="utf-8")
    if t.count(old) < count:
        raise SystemExit(f"mutation anchor missing in {path}: {old[:60]!r}")
    _io(p.write_text, t.replace(old, new, count), encoding="utf-8")


def mutate_bytes(path, extra):
    p = ROOT / path
    _io(p.write_bytes, _io(p.read_bytes) + extra)


def run_gate():
    r = subprocess.run([PY, str(ROOT / "tools" / "check.py")], cwd=str(ROOT), capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


CASES = [
    ("og:image относительный", "index.html",
     '<meta property="og:image" content="https://ssrjkk.github.io/fruktovy/assets/og.png">',
     '<meta property="og:image" content="assets/og.png">',
     "og:image must be absolute"),
    ("twitter:card удалён", "index.html",
     '<meta name="twitter:card" content="summary_large_image">',
     '<meta name="twitter:cardx" content="summary_large_image">',
     "no twitter:card"),
    ("JSON-LD image относительный", "index.html",
     '"image":"https://ssrjkk.github.io/fruktovy/assets/og.png"',
     '"image":"assets/og.png"',
     "JSON-LD image must be absolute"),
    ("видимый FAQ ответ разъехался с JSON-LD", "index.html",
     "сама карта подгружается только после нажатия.</p></div></details>",
     "карта открывается по кнопке.</p></div></details>",
     "answer differs from JSON-LD"),
    ("тире в часах смешано", "index.html",
     "<span>08:00–21:00</span>",
     "<span>08:00—21:00</span>",
     "dash"),
    ("незаявленный сторонний хост", "index.html",
     '<link rel="manifest" href="manifest.webmanifest">',
     '<link rel="prefetch" href="https://cdn.example.com/pixel.png"><link rel="manifest" href="manifest.webmanifest">',
     "undeclared third-party embed hosts"),
    ("оболочка офлайна неполная", "sw.js", '"./js/data.js", ', "",
     "offline shell incomplete"),
    ("в precache тащатся тяжёлые ассеты", "sw.js", '"./assets/icon-512.png",',
     '"./assets/icon-512.png", "./assets/img/1002778-1500x1000.jpg",',
     "display-only bulk"),
    ("og.png раздулся", "assets/og.png", 300_000, None, "260 KB"),
    ("печать: карточки рвёт по страницам", "css/style.css", "break-inside:avoid", "",
     "break-inside:avoid"),
    ("печать: ссылки без адресов на бумаге", "css/style.css",
     'content:" (" attr(href) ")"', 'content:""', "attr(href)"),
    ("печать: декор не снят", "css/style.css", "background-image:none!important", "",
     "background-image:none"),
    ("печать: карта осталась на листе", "css/style.css", "#mapBox{display:none!important}",
     "#mapBox{display:inline!important}", "#mapBox display:none"),
    ("печать: правило по мёртвому классу", "css/style.css", ".burger,.skip",
     ".burger,.skipped-away", "classes the markup never uses"),
    ("контраст: зелёный промо стал светлым", "css/style.css", "--leaf-d:#26543a;",
     "--leaf-d:#6fbf8f;", "contrast promo heading"),
    ("контраст: бейдж вернулся на persimmon", "css/style.css",
     "linear-gradient(132deg,var(--beet),var(--persimmon-d))",
     "linear-gradient(132deg,var(--beet),var(--persimmon))", "contrast contract broken at .p-badge"),
    ("контраст: muted посветлел", "css/style.css", "--muted:#6d6259;", "--muted:#a89c90;",
     "contrast muted body copy"),
    ("контраст: ticker потерял читаемый цвет", "css/style.css",
     "overflow:hidden;font-size:.86rem;color:var(--chip-ink)",
     "overflow:hidden;font-size:.86rem", "contrast contract broken at .hero-ticker"),
    ("контраст: токен вырезан из :root", "css/style.css", "--chip-ink:#e8dfd6;", "",
     "token --chip-ink missing"),
    ("rail-точки потеряли зону нажатия", "css/style.css", ".rail a::before", ".rail a::zzz",
     "enlarged hit area"),
    ("гайд: вкладка специй пропала", "index.html",
     '<button class="tab" type="button" data-tab="spices">Специи</button>', "",
     "guide tips without a tab"),
    ("гайд: категория без своих советов", "js/data.js", ",spices:[{", ",spicex:[{",
     "categories without guide tips"),
    ("гайд: иконка советa не из спрайта", "js/data.js", "и сразу закрывайте.',i:'leaf'}]}",
     "и сразу закрывайте.',i:'leafx'}]}", "guide icons missing from sprite"),
    ("гайд: совет выродился в слово", "js/data.js",
     "{t:'Мягкие — в холодильник',d:'Финики и мягкий чернослив лучше хранить в холодильнике.',i:'clock'}",
     "{t:'Мягкие',d:'в холод',i:'clock'}", "guide tips shorter than 40 chars"),
    ("LCP-арт потерял fetchpriority", "index.html",
     'alt="" fetchpriority="high" loading="eager"', 'alt="" loading="eager"',
     "exactly one img may claim fetchpriority"),
    ("QR ниже каталога стал грузиться жадно", "index.html",
     '<img src="assets/qr.png" alt="QR-код на сайт" width="132" height="132" loading="lazy" decoding="async">',
     '<img src="assets/qr.png" alt="QR-код на сайт" width="132" height="132" loading="eager" decoding="async">',
     "not lazy-loaded"),
    ("у картинки пропало решение о загрузке", "index.html",
     '<img src="assets/qr.png" alt="QR-код на сайт" width="132" height="132" loading="lazy" decoding="async">',
     '<img src="assets/qr.png" alt="QR-код на сайт" width="132" height="132" decoding="async">',
     "without an explicit loading decision"),
    ("шаблон корзины рендерит img без lazy", "js/main.js",
     'alt="" width="160" height="130" loading="lazy" decoding="async"',
     'alt="" width="160" height="130"', "JS-rendered imgs without a loading decision"),
    ("фокус-кольцо выключено через outline:none", "css/style.css",
     "color:var(--ink)}.field-search input:focus-visible",
     "color:var(--ink);outline:none}.field-search input:focus-visible",
     "kills a focus ring"),
    ("фокус-кольцо стало тоньше 3px", "css/style.css", ":focus-visible{outline:3px",
     ":focus-visible{outline:1px", "focus ring thinner than 3px"),
    ("кольцо поиска слезло с focus-visible", "css/style.css",
     ".field-search input:focus-visible{outline:3px solid var(--ring)",
     ".field-search input:focus{outline:3px solid var(--ring)",
     "search field lost its own focus ring"),
    ("токен кольца посветлел", "css/style.css", "--ring:#b8481b;", "--ring:#f7c3a1;",
     "contrast focus ring --ring on parchment"),
    ("герой потерял светлое кольцо", "css/style.css",
     ".promo :focus-visible,.p-media :focus-visible,", ".p-media :focus-visible,",
     "dark surfaces without the light focus ring"),
    ("кольцо съехало с --ring токена", "css/style.css",
     ":focus-visible{outline:3px solid var(--ring);",
     ":focus-visible{outline:3px solid var(--persimmon);",
     "must use the --ring token"),
    ("JSON-LD телефон разъехался с data.js", "index.html",
     '"telephone":"+79000000000"', '"telephone":"+79000000001"',
     "JSON-LD telephone drifted"),
    ("JSON-LD второй телефон потерялся", "index.html",
     '"alternateTelephone":[{"@type":"TelecommunicationFormat","telephone":"+79000000000"}],', "",
     "SHOP.phone2 is missing"),
    ("priceRange снова прозой", "index.html", '"priceRange":"₽"', '"priceRange":"по запросу"',
     "priceRange must be a currency symbol"),
    ("JSON-LD часы разошлись с магазином", "index.html", '"opens":"08:00"', '"opens":"09:00"',
     "JSON-LD hours"),
    ("JSON-LD день недели потерялся", "index.html", ',"Sunday"', "",
     "must list all 7 days"),
    ("JSON-LD sameAs ведёт не на ту организацию", "index.html",
     "https://yandex.ru/maps/org/fruktovy_dvorets/60838532953/",
     "https://yandex.ru/maps/org/fruktovy/10000000000/",
     "sameAs does not point"),
    ("JSON-LD гео уехало с Сытнинской", "index.html", '"latitude":59.957835', '"latitude":59.99',
     "geo drifted"),
    ("карточка без вкуса: esc(p.use) выкинут", "js/main.js",
     """<p class="p-use">'+esc(p.use)+'</p>""", """<p class="p-use">'+esc(p.name)+'</p>""",
     "taste text never rendered on a card"),
    ("peek без описания товара", "js/main.js",
     """$('#peekDesc').textContent=p.use;""", "",
     "taste text never rendered in peek"),
    ("peek снова берёт совет категории", "js/main.js",
     "esc(p.store||tips[0].d)", "esc(tips[0].d)",
     "peek still uses the category note"),
    ("в peek нет места для описания", "index.html", 'id="peekDesc"', 'id="peekDescx"',
     "peek dialog has no place"),
    ("у текста на карточке нет клампа", "css/style.css",
     "-webkit-line-clamp:2;-webkit-box-orient:vertical;", "",
     ".p-use has no line clamp"),
    ("описание в peek осталось без стиля", "css/style.css",
     ".peek-desc{margin:0 0 16px;", ".peek-descx{margin:0 0 16px;",
     "no style for .peek-desc"),
    ("у позиции вкус стал обрывком", "js/data.js",
     ",use:'Хрустят в салате и в шарлотке, дольками уходят в чай вместо печенья.'",
     ",use:'Хрустят в салате.'",
     "taste text out of 45..115"),
    ("вкусы двух позиций слились", "js/data.js",
     "use:'Разотрите между ладонями прямо над кастрюлей — так раскрывается дух.'",
     "use:'Отмеряйте сухой ложкой и сразу закрывайте банку; молотые сыпьте в конце.'",
     "same taste text on several products"),
    ("хранение позиции уехало в CATS", "js/data.js",
     "{id:'fruits',name:'Фрукты'}", "{id:'fruits',name:'Фрукты',store:'В прохладе'}",
     "category rows carrying product fields"),
    ("сетка-квадраты вернулась в фон", "index.html",
     '<div class="bg-grain"', '<div class="bg-grid" aria-hidden="true"></div><div class="bg-grain"',
     "decorative square layer still wired"),
    ("ходящие лучи вернулись", "css/style.css",
     "#progress{position:fixed", ".bg-rays{position:fixed;inset:0}#progress{position:fixed",
     "decorative square layer still wired"),
    ("паттерн-клетка вернулась в CSS", "css/style.css",
     '.bg-grain{position:fixed',
     '.bg-grain{position:fixed;background-image:url("data:image/svg+xml,%3Csvg '
     "xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cpath "
     "d='M0 60h120M60 0v120' stroke='%231b1220' stroke-opacity='.045'/%3E%3C/svg%3E\")",
     "square-grid pattern painted"),
    ("бумажное зерно сняли", "index.html",
     '<div class="bg-grain" aria-hidden="true"></div>', "",
     "background layer missing: bg-grain"),
]

state = snapshot()
fails = []
try:
    for name, target, a, b, want in CASES:
        if isinstance(a, int):
            mutate_bytes(target, b"\0" * a)
        else:
            mutate(target, a, b)
        rc, out = run_gate()
        ok = rc == 1 and want in out
        print(("BITES  " if ok else "WEAK   ") + name + f"  (rc={rc}, want={want!r})")
        if not ok:
            fails.append((name, out.strip().splitlines()[:6]))
        restore(state)
finally:
    restore(state)

rc, out = run_gate()
print("restored tree gate rc=%d %s" % (rc, out.strip().splitlines()[-1:]))
for name, det in fails:
    print("---- " + name)
    for line in det:
        print("   " + line)
sys.exit(1 if fails or rc != 0 else 0)