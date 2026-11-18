#!/usr/bin/env python3
"""Доказательство, что каждый новый гейт tools/check.py кусается: мутируем файл,
запускаем гейт, требуем конкретную ошибку, восстанавливаем байты из git."""
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FILES = ["index.html", "sw.js", "css/style.css", "css/themes.css", "js/theme.js",
         "assets/og.png", "assets/icon-512.png", "js/data.js", "js/main.js"]
# Если прогон убили посреди мутации, дерево остаётся испорченным и следующий
# check.py валится на чужом изменении. Снимок лежит вне репозитория и вычищается
# при следующем старте.
JDIR = Path(tempfile.gettempdir()) / "frukti_gate_snapshot"


def _jpath(f):
    return JDIR / f.replace("/", "__")


def recover():
    if not JDIR.is_dir():
        return
    for f in FILES:
        jp = _jpath(f)
        if not jp.exists():
            continue
        cur = (ROOT / f).read_bytes() if (ROOT / f).exists() else None
        if cur != jp.read_bytes():
            _io((ROOT / f).write_bytes, jp.read_bytes())
            print("РЕКАВЕРИ: восстановлен обрывок прошлого прогона -> " + f, flush=True)


def _io(fn, *a, **kw):
    """Файл секунду может быть занят Chrome из только что законченного прогона гейта."""
    for _ in range(40):
        try:
            return fn(*a, **kw)
        except OSError:
            time.sleep(0.25)
    raise SystemExit(f"file busy: {a[0] if a else fn}")


def snapshot():
    JDIR.mkdir(parents=True, exist_ok=True)
    st = {}
    for f in FILES:
        b = _io((ROOT / f).read_bytes)
        _io(_jpath(f).write_bytes, b)
        st[f] = b
    return st


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
    # Дочерний python печатает кириллицу в пайп; без UTF-8 он выдаёт cp1251, и
    # родитель не может это прочитать — мутация кажется некусающейся.
    import os
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, str(ROOT / "tools" / "check.py")], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
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
    ("в precache тащатся тяжёлые ассеты", "assets/icon-512.png", 300_000, None,
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
    ("гайд: иконка советa не из спрайта", "js/data.js",
     "держите их в стороне.',i:'apart'", "держите их в стороне.',i:'apartx'",
     "guide icons missing from sprite"),
    ("гайд: совет выродился в слово", "js/data.js",
     "{t:'Мягкие — в холодильник',d:'Финики и мягкий чернослив лучше хранить в холодильнике.',i:'cold'}",
     "{t:'Мягкие',d:'в холод',i:'cold'}", "guide tips shorter than 40 chars"),
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
    # --- геометрия иконок: каждый новый пункт гейта должен кусаться ---
    ("штрих стал волосяным", "css/style.css",
     "stroke-width:2.15", "stroke-width:1.05",
     "icon stroke"),
    ("у .ic сняли round caps — спрайт наследует", "css/style.css",
     "stroke:currentColor;fill:none;stroke-width:2.15;stroke-linecap:round",
     "stroke:currentColor;fill:none;stroke-width:2.15",
     ".ic lost stroke-linecap:round"),
    ("штрих срезан до точки", "index.html",
     "M12 9.4v4.8", "M12 9.4v1.2",
     "stroke shorter than"),
    ("к глифу прилепился осколок", "index.html",
     '<path d="m21.4 21.4-5-5"/>', '<path d="m21.4 21.4-5-5"/><circle cx="2.2" cy="21.8" r="0.9"/>',
     "px at 16px"),
    ("один штрих распался на два с зазором", "index.html",
     "M12 6.5V12l3.8 2.2", "M12 6.5V12M12.6 12.6l3.2 1.8",
     "two stroke ends left"),
    ("лист стал копией глаза", "index.html",
     "M11.4 20.6A7.6 7.6 0 0 1 10 6.4C16 5.2 17.6 4.6 19.8 2c1.1 2.2 2.2 4.6 2.2 8.6 0 5.9-5.2 10.6-10.6 10z",
     "M1.5 12S5.5 4.5 12 4.5 22.5 12 22.5 12 18.5 19.5 12 19.5 1.5 12 1.5 12z",
     "are the same silhouette"),
    ("магазин залили жирным штрихом", "index.html",
     '<path d="M2.6 9 4.8 3.4h14.4L21.4 9z"/>',
     '<path stroke-width="6" d="M2.6 9 4.8 3.4h14.4L21.4 9z"/>',
     "ink weight"),
    ("звезда осталась и залита, и обведена", "index.html",
     '<path fill="currentColor" stroke="none" d="m12 2 2.9',
     '<path fill="currentColor" d="m12 2 2.9',
     "both filled and stroked"),
    ("в одной вкладке два совета с одним глифом", "js/data.js",
     "{t:'Тёмный шкаф, не полка у плиты',d:'Свет и тепло забирают эфирные масла. В закрытом шкафу молотые специи держат аромат заметно дольше.',i:'dark'}",
     "{t:'Тёмный шкаф, не полка у плиты',d:'Свет и тепло забирают эфирные масла. В закрытом шкафу молотые специи держат аромат заметно дольше.',i:'clock'}",
     "reusing one glyph for two tips"),
    # --- темы: переключатель и слой market ---
    ("тема market забыла цвет палитры", "css/themes.css",
     "--quince-hi:#ffe08a;", "",
     "не переопределяет цвета базовой палитры"),
    ("токен темы стал не-hex", "css/themes.css",
     "--parch:#cbb08a;", "--parch:#cbb08aa;",
     "не 6-ричный hex"),
    ("слой целился в несуществующий класс", "css/themes.css",
     "[data-theme=market] .panel", "[data-theme=market] .panelz",
     "нацелена на классы, которых нет в разметке"),
    ("контраст market поплыл на крафте", "css/themes.css",
     "--persimmon-d:#6c200c;", "--persimmon-d:#b06a4a;",
     "contrast market accent link"),
    ("акцент базовой темы проиграл зерну бумаги", "css/style.css",
     "--persimmon-d:#aa4316;", "--persimmon-d:#b8481b;",
     "contrast accent label on grained paper"),
    ("акцент market проиграл зерну доски", "css/themes.css",
     "--persimmon-d:#6c200c;", "--persimmon-d:#7a2410;",
     "contrast market accent label on grained kraft"),
    ("блик бейджа снова светлее 0.20", "css/style.css",
     "rgba(255,255,255,.16)", "rgba(255,255,255,.45)",
     "блик бейджа"),
    ("правило блика бейджа пропало", "css/style.css",
     ".p-badge::after{", ".p-badge2::after{",
     "блик .p-badge::after не найден"),
    # --- шапка market: тёмная доска, и любой предмет на ней без перекраски исчезает ---
    ("логотип в шапке market стал тёмным", "css/themes.css",
     "[data-theme=market] .site-head .logo-text{color:var(--parch)}",
     "[data-theme=market] .site-head .logo-text{color:var(--fig)}",
     "шапка market: «надпись логотипа» больше не ссылается"),
    ("правило логотипа в шапке market пропало", "css/themes.css",
     "[data-theme=market] .site-head .logo-text{",
     "[data-theme=market] .site-head2 .logo-text{",
     "шапка market: правило «надпись логотипа» пропало"),
    ("корзина в шапке market слилась с доской", "css/themes.css",
     "[data-theme=market] .cart-btn{border-color:var(--quince-hi);color:var(--quince-hi)}",
     "[data-theme=market] .cart-btn{border-color:var(--fig);color:var(--fig)}",
     "шапка market: «обводка корзины» больше не ссылается"),
    ("бургер market слился с доской", "css/themes.css",
     "[data-theme=market] .burger span{background:var(--quince-hi)}",
     "[data-theme=market] .burger span{background:var(--fig)}",
     "шапка market: «полоски бургера» больше не ссылается"),
    ("точка статуса market проиграла бумажной этикетке", "css/themes.css",
     "--ok:#2f6f38;", "--ok:#9ed3a8;",
     "contrast market status dot open"),
    ("этикетка часов market ушла с бумаги на крафт", "css/themes.css",
     "[data-theme=market] .head-live{background:var(--surface)",
     "[data-theme=market] .head-live{background:var(--parch)",
     "«этикетка часов» больше не ссылается на var(--surface)"),
    ("защита ссылок market шире реального брейкпоинта", "css/themes.css",
     "@media(min-width:769px){[data-theme=market] .nav a{color:var(--parch)}}",
     "@media(min-width:1101px){[data-theme=market] .nav a{color:var(--parch)}}",
     "ссылки market должны быть защищены @media(min-width:769px)"),
    ("брейкпоинт панели навигации перестал находиться", "css/style.css",
     ".nav{position:fixed", ".navxx{position:fixed",
     "не нашли, на какой ширине .nav уходит в панель"),
    ("в переключателе осталась одна тема", "index.html",
     '<button type="button" data-theme-set="parchment" aria-pressed="true">Пергамент</button>',
     "",
     "переключатель тем предлагает"),
    ("подпись у переключателя потеряла выбор", "index.html",
     "Два варианта одного сайта. Какую тему согласуете — ту и оставим.",
     "Тема оформления страницы.",
     "не обещает заказчику выбор темы"),
    ("theme.js отложили — вспышка темы", "index.html",
     '<script src="js/theme.js"></script>',
     '<script defer src="js/theme.js"></script>',
     "будет вспышка базовой темы"),
    ("theme.js уехал после стилей", "index.html",
     '<script src="js/theme.js"></script>\n<link rel="stylesheet" href="vendor/swiper-bundle.min.css">',
     '<link rel="stylesheet" href="vendor/swiper-bundle.min.css">\n<script src="js/theme.js"></script>',
     "атрибут темы встанет поздно"),
    ("с <html> сняли дефолтную тему", "index.html",
     '<html lang="ru" data-theme="parchment">', '<html lang="ru">',
     "нет дефолтного data-theme"),
    ("main.js перестал сохранять тему", "js/main.js",
     "if(persist)writeLS(THEME_KEY,name)", "if(persist)writeLS(name,name)",
     "нет writeLS(THEME_KEY"),
    ("обработчик темы уехал из IIFE", "js/main.js",
     "$$('[data-theme-set]').forEach(function(b){b.addEventListener('click',function(){setTheme(b.getAttribute('data-theme-set'),true);});});\n"
     "setTheme(document.documentElement.getAttribute('data-theme'),false);})();",
     "})();\n"
     "$$('[data-theme-set]').forEach(function(b){b.addEventListener('click',function(){setTheme(b.getAttribute('data-theme-set'),true);});});\n"
     "setTheme(document.documentElement.getAttribute('data-theme'),false);",
     "вне IIFE"),
    ("переключатель полез на печать", "css/themes.css",
     "@media print{.theme-switch{display:none!important}}", "@media print{.ts-note{display:none!important}}",
     "попадёт на печать"),
    ("themes.css выпал из прекеша", "sw.js",
     '"./css/style.css", "./css/themes.css",', '"./css/style.css",',
     "not precached"),
    ("заголовок market просит несамохостed шрифт", "css/themes.css",
     '--display:"Oswald"', '--display:"Playfair Display"',
     "не самохостed"),
    # --- кольцо фокуса: обрезка рельсами, вписанные кольца, светлое на тёмном ---
    ("кольцо обрежет фильтр: у рельса нет запаса", "css/style.css",
     ".pills{padding:7px;margin:-7px}", ".pills{padding-bottom:3px;margin:0}",
     "обрежется в .pills"),
    ("кольцо обрежет ряд месяцев", "css/style.css",
     ".months{padding:7px;margin:-7px -7px 17px}", ".months{padding-bottom:6px;margin-bottom:24px}",
     "обрежется в .months"),
    ("кольцо обрежет галерею: .gal перестал выступать наружу", "css/style.css",
     ".gal{margin:-7px}", ".gal{margin:0}", "обрежет .gal"),
    ("плитки галереи уехали вместе с кольцом", "css/style.css",
     ".gal .swiper-wrapper,html.swiper-on .gal .swiper-wrapper{padding:7px}",
     ".gal .swiper-wrapper{padding:7px}",
     "обрежется в .gal .swiper-wrapper"),
    # Тот же дефект, собранный каскадом: правило с большей специфичностью возвращает
    # padding-bottom:0, текст запаса на месте — гейт обязан увидеть провал по победившему
    # объявлению, а не по наличию строки. (3 класса + 2 элемента = 32 против 31 у строки
    # запаса; цепочка матчера при этом остаётся той же, так что прятаться не за что.)
    ("каскад срезал кольцо плиток, оставив запас в тексте", "css/style.css",
     ".gal .swiper-wrapper,html.swiper-on .gal .swiper-wrapper{padding:7px}",
     ".gal .swiper-wrapper,html.swiper-on .gal .swiper-wrapper{padding:7px}"
     "html.swiper-on body .gal .swiper-wrapper{padding-bottom:0}",
     "обрежется в .gal .swiper-wrapper"),
    ("кольцо миниатюр лайтбокса обрезано", "css/style.css",
     ".lb-thumbs{padding:10px 7px 9px;margin:0 -7px}", ".lb-thumbs{padding:10px 0 2px;margin:0}",
     "обрежется в .lb-thumbs"),
    ("счётчик: кольцо снова рисуется снаружи обрезающего пилюли", "css/style.css",
     ".step button:focus-visible{outline-offset:-3px;border-radius:99px}",
     ".step button:focus-visible{border-radius:99px}", "фокус-кольцо .step button"),
    ("FAQ: кольцо строки вылезло за details с overflow:hidden", "css/style.css",
     ".faq summary:focus-visible{outline-offset:-3px;border-radius:12px}",
     ".faq summary:focus-visible{border-radius:12px}", "фокус-кольцо .faq summary"),
    ("skip-ссылка: кольцо уехало за край документа", "css/style.css",
     ".skip:focus-visible{outline-offset:-3px;border-radius:0 0 10px 10px}",
     ".skip:focus-visible{border-radius:0 0 10px 10px}", "фокус-кольцо .skip"),
    ("тап-цель точки пагинации снова 9px", "css/style.css",
     ".gal-dots .swiper-pagination-bullet{width:24px;height:24px;",
     ".gal-dots .swiper-pagination-bullet{width:9px;height:9px;",
     "тап-цель точки пагинации меньше 24px"),
    ("точка пагинации стала серым квадратом 24px", "css/style.css",
     ".gal-dots .swiper-pagination-bullet::before{content:\"\";position:absolute;inset:7px;border-radius:50%;background:var(--fig)",
     ".gal-dots .swiper-pagination-bullet::before{content:\"\";position:absolute;inset:7px;border-radius:50%;background:none",
     "потеряла кружок"),
    ("подвал потерял светлое кольцо", "css/style.css",
     ".site-foot :focus-visible,#lightbox :focus-visible,", "#lightbox :focus-visible,",
     "dark surfaces without the light focus ring"),
    ("лайтбокс потерял светлое кольцо", "css/style.css",
     "#lightbox :focus-visible,.skip:focus-visible", ".skip:focus-visible",
     "dark surfaces without the light focus ring"),
    # Бургер снимаем с группы ВЦЕЛОМ (класс остаётся живым): замена класса на burgerx
    # ломала сразу два гейта — и про классы разметки, и про кольцо, — и в отчёте стоял
    # не тот дефект. Мутация обязана менять только то, что проверяет assertion.
    ("доска бара market: бургер снова с тёмным кольцом", "css/themes.css",
     "[data-theme=market] .site-head .burger:focus-visible,\n", "",
     "предметы бара без светлого фокус-кольца"),
    ("светлое кольцо ссылок menus сошло с медиа-страха бара", "css/themes.css",
     "@media(min-width:769px){[data-theme=market] .nav a:focus-visible{outline-color:var(--ring-dark)}}",
     "[data-theme=market] .nav a:focus-visible{outline-color:var(--ring-dark)}",
     "обязано светлеть только в баре"),
]

recover()
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
        print(("BITES  " if ok else "WEAK   ") + name + f"  (rc={rc}, want={want!r})", flush=True)
        if not ok:
            fails.append((name, out.strip().splitlines()[:6]))
        restore(state)
finally:
    restore(state)
    # Снимок живёт только пока идёт прогон. Если оставить его после падежной смерти
    # (анкор мутации не нашёлся — SystemExit мимо хвоста файла), следующий запуск
    # своим recover() вернёт на дерево байты прошлого прогона и перепишет всё, что
    # между прогонами было починено. Один раз так подменили jsmin-версию main.js,
    # и гейт упал уже на собственном осколке.
    shutil.rmtree(JDIR, ignore_errors=True)

rc, out = run_gate()
print("restored tree gate rc=%d %s" % (rc, out.strip().splitlines()[-1:]))
for name, det in fails:
    print("---- " + name)
    for line in det:
        print("   " + line)
sys.exit(1 if fails or rc != 0 else 0)