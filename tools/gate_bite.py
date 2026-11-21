#!/usr/bin/env python3
"""Доказательство, что гейты tools/check.py кусаются.

Каждый случай мутирует рабочий файл, прогоняет гейт и требует конкретную строку ошибки,
после чего дерево возвращается байтового снимка (снимок живёт в %TEMP%, вне репозитория).
Второй блок сверяет покрытие: из check.py вынимаются все тексты ERR.append и все
запрещённые обороты FORBIDDEN, и каждый обязан быть либо закрыт мутацией, либо стоять в
EXEMPT с причиной. Гейт, который нельзя заставить кричать, — это декорация.

Формат случая: (имя, файл, вид, какая ошибка ждётся)
  ("sub", старое, новое)          — первая подстрока
  ("sub_all", старое, новое)      — все вхождения
  ("cut", регулярка[, замена])    — вырезание одного места (по умолчанию — ничем)
  ("cut_all", регулярка[, замена])— вырезание всех мест (гейт кричит только на пустом наборе)
  ("append", текст)               — дописать в конец файла
  ("nul", N)                      — дописать N нулей (тяжёлый ассет)
  ("drop",)                       — удалить файл
  ("touch", N)                    — создать файл из N байт (для мусора в assets/img)
  ("multi", [(файл, вид, …), …])  — правки в нескольких файлах одним случаем

Прогон идёт по читаемому дереву: якоря кейсов написаны под него. Минифицированную
сборку этим же составом не гоняют — там другие пробелы; её проверяет tools/check.py.

Запуск: python tools/gate_bite.py [--only подстрока]
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
FILES = ["index.html", "404.html", "css/style.css", "js/data.js", "js/app.js", "js/app-head.js",
         "sw.js", "manifest.webmanifest", "robots.txt", "sitemap.xml", "tools/build.py",
         "assets/fonts.css", "assets/logo.svg", "assets/og.png", "assets/icon-512.png"]
# Снимок вне репозитория: если прогон убили посреди мутации, следующий старт вернёт дерево.
JDIR = Path(tempfile.gettempdir()) / "frukti_gate_snapshot"
CREATED = []


def _jpath(f):
    return JDIR / f.replace("/", "__")


def _io(fn, *a, **kw):
    """Файл секунду может быть занят антивирусом или только что закончившимся прогоном."""
    for _ in range(40):
        try:
            return fn(*a, **kw)
        except OSError:
            time.sleep(0.25)
    raise SystemExit(f"file busy: {a[0] if a else fn}")


def recover():
    if not JDIR.is_dir():
        return
    for f in FILES:
        jp = _jpath(f)
        if jp.exists():
            cur = (ROOT / f).read_bytes() if (ROOT / f).exists() else None
            if cur != jp.read_bytes():
                _io((ROOT / f).write_bytes, jp.read_bytes())
                print("РЕКАВЕРИ: восстановлен обрывок прошлого прогона -> " + f, flush=True)


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
    for f in CREATED:
        p = ROOT / f
        if p.exists():
            p.unlink()
    CREATED.clear()


def text_of(path):
    return _io((ROOT / path).read_text, encoding="utf-8")


def write_text(path, t):
    _io((ROOT / path).write_text, t, encoding="utf-8")


def sub(path, old, new, all_occurrences=False):
    t = text_of(path)
    if old not in t:
        raise SystemExit(f"mutation anchor missing in {path}: {old[:70]!r}")
    write_text(path, t.replace(old, new) if all_occurrences else t.replace(old, new, 1))


def edit(path, op, *args):
    if op in ("sub", "sub_all"):
        sub(path, args[0], args[1], op == "sub_all")
    elif op in ("cut", "cut_all"):
        t = text_of(path)
        out, n = re.subn(args[0], args[1] if len(args) > 1 else "", t, count=0 if op == "cut_all" else 1)
        if not n:
            raise SystemExit(f"cut pattern missed in {path}: {args[0][:70]!r}")
        write_text(path, out)
    elif op == "append":
        write_text(path, text_of(path) + args[0])
    elif op == "nul":
        _io((ROOT / path).write_bytes, _io((ROOT / path).read_bytes) + b"\0" * args[0])
    elif op == "drop":
        (ROOT / path).unlink()
    elif op == "touch":
        p = ROOT / path
        if p.exists():
            raise SystemExit(f"touch target already exists: {path}")
        p.parent.mkdir(parents=True, exist_ok=True)
        _io(p.write_bytes, b"\xff\xd8\xff" + b"\0" * args[0])
        CREATED.append(path)
    else:
        raise SystemExit("bad edit op " + op)


def apply_case(target, kind):
    if kind[0] == "multi":
        for entry in kind[1]:
            edit(entry[0], entry[1], *entry[2:])
    else:
        edit(target, *kind)


def run_gate():
    # Дочерний python печатает кириллицу в пайп; без UTF-8 он выдаёт cp1251, и родитель
    # не сможет прочитать вывод — мутация покажется некусающейся.
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, str(ROOT / "tools" / "check.py")], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def inject(what):
    """Кусок текста в конец <body> — для проверок «такого в витрине быть не должно»."""
    return ("multi", [("index.html", "sub", "</body>", '<p class="tnum">' + what + "</p></body>")])


# ============================================================== кейсы ====
CASES = [
    # --- исходники ---------------------------------------------------------
    ("css/style.css удалён", "css/style.css", ("drop",), "нет исходника css/style.css"),
    ("app-head пуст", "js/app-head.js", ("cut", r"[\s\S]+"), "пустой исходник js/app-head.js"),

    # --- разметка ----------------------------------------------------------
    ("не закрыт h1", "index.html",
     ("sub", '<h1 class="hero-title">Живой прилавок <em>свежих фруктов</em> на Петроградке</h1>',
      '<h1 class="hero-title">Живой прилавок <em>свежих фруктов</em> на Петроградке'), "не закрыт <h1>"),
    ("дубль id", "index.html", ("sub", "</body>", '<span id="mapBox"></span></body>'), "дубли id в index.html"),
    ("404 тянет несуществующий css", "404.html",
     ("sub", '<link rel="stylesheet" href="css/style.css">', '<link rel="stylesheet" href="css/gone.css">'),
     "404.html: нет файла css/gone.css"),
    ("404 зовёт спрайт из чужого документа", "404.html",
     ("sub", "</body>", '<svg class="icon"><use href="#ic-bag"/></svg></body>'), "404.html: <use> на спрайт"),
    ("картинок нет вообще", "index.html", ("sub_all", "<img ", "<image "), "ни одной картинки — гейт слепой"),
    ("картинка без alt", "index.html", ("sub", 'alt="Сладкие мандарины с веточкой" ', ""), "без alt"),
    ("loading=fast", "index.html",
     ("sub", 'fetchpriority="high" decoding="async"', 'fetchpriority="high" loading="fast" decoding="async"'),
     ": loading="),
    ("картинка с чужого cdn", "index.html",
     ("sub", 'src="./assets/img/1002778-640x480.jpg" alt="Сладкие', 'src="//cdn.example.com/mandarins.jpg" alt="Сладкие'),
     "картинка грузится не с нашего домена"),
    ("файл картинки не собран", "index.html",
     ("sub", 'src="./assets/img/1002778-640x480.jpg" alt="Сладкие', 'src="./assets/img/1002778-641x480.jpg" alt="Сладкие'),
     ": нет файла ./assets/img/1002778-641x480.jpg"),
    ("картинка ниже каталога грузится жадно", "index.html",
     ("sub", "</body>",
      '<img src="./assets/img/31665655-120x120.jpg" alt="хвост" width="60" height="60"></body>'),
     "без loading=lazy — телефон тянет весь прилавок"),
    ("кнопка без имени", "index.html",
     ("sub", "</body>", '<button type="button" class="btn btn-outline"></button></body>'),
     "без текста и без aria-label"),
    ("кнопка названа только title", "index.html",
     ("sub", "</body>",
      '<button type="button" class="btn btn-outline" title="Только подсказка">'
      '<svg class="icon"><use href="#ic-bag"/></svg></button></body>'),
     "без текста и без aria-label"),
    ("поле без доступного имени", "index.html",
     ("sub", "</body>", '<input type="text" class="select-ctrl" id="ghostInput"></body>'),
     "у поля нет доступного имени"),
    ("iframe без title", "index.html",
     ("sub", ' src="https://yandex.ru/sprav/widget/rating-badge/60838532953" title="Рейтинг организации на Яндекс Картах"',
      ' src="https://yandex.ru/sprav/widget/rating-badge/60838532953"'), "без title — скринридер читает пустоту"),
    ("iframe не из Яндекса", "index.html",
     ("sub", "yandex.ru/sprav/widget/rating-badge", "example.com/sprav/widget/rating-badge"),
     "источник вне белого списка"),
    ("javascript:-ссылка", "index.html",
     ("sub", "</body>", '<a href="javascript:void(0)" class="btn btn-outline">тк</a></body>'), "javascript:-ссылка"),
    ("target=_blank без noopener", "index.html",
     ("sub", '<a href="https://t.me/ssrjkk" target="_blank" rel="noopener noreferrer">',
      '<a href="https://t.me/ssrjkk" target="_blank">'), "target=_blank без rel"),
    ("якорь в никуда", "index.html", ("sub", 'href="#catalog"', 'href="#cataloggz"'), "якоря нет в разметке"),
    ("aria-controls на несуществующий id", "index.html",
     ("sub", 'aria-controls="mobileMenu"', 'aria-controls="mobileMeny"'), "несуществующий id"),
    ("<use> на несуществующий символ", "index.html",
     ("sub", '<use href="#ic-crown"/>', '<use href="#ic-crownX"/>'), "ссылается на несуществующий символ"),
    ("мёртвый символ в спрайте", "index.html",
     ("cut", r'[ ]*<svg class="icon" style="width:15px;height:15px;"><use href="#ic-share"/></svg>\n'),
     "символы не используются (мёртвый вес)"),
    ("спрайт вырезан", "index.html", ("cut_all", r"<symbol[\s\S]*?</symbol>\n?"), "спрайт пуст"),
    ("aria-live снята", "index.html", ("sub", 'aria-live="polite"', 'data-live="polite"'), "нет ни одной aria-live-зоны"),
    ("второй h1", "index.html", ("sub", "</body>", '<h1 class="serif">второй</h1></body>'), "заголовков h1"),

    # --- head --------------------------------------------------------------
    ("fonts.css не подключён", "index.html",
     ("cut", r'[ ]*<link rel="stylesheet" href="assets/fonts.css">\n'), "head: нет assets/fonts.css"),
    ("canonical не наш", "index.html",
     ("sub", '<link rel="canonical" href="https://ssrjkk.github.io/fruktovy/">',
      '<link rel="canonical" href="https://ssrjkk.github.io/other/">'), "head: нет canonical"),
    ("og:image относительный", "index.html",
     ("sub", 'content="https://ssrjkk.github.io/fruktovy/assets/og.png"', 'content="assets/og.png"'),
     "og-ссылка не абсолютная"),
    ("twitter:card удалён", "index.html",
     ("cut", r'[ ]*<meta name="twitter:card" content="summary_large_image">\n'), "head: нет twitter:card"),
    ("description усох", "index.html",
     ("cut", r'<meta name="description" content="[^"]*"', '<meta name="description" content="Лавка'),
     "head: нет description"),
    ("og:site_name разошёлся с вывеской", "index.html",
     ("sub", '<meta property="og:site_name" content="Фруктовый дворец">',
      '<meta property="og:site_name" content="Фруктовый ряд">'), "og:site_name не совпадает"),
    ("единственный high-флаг потерян", "index.html",
     ("sub", ' width="640" height="480" fetchpriority="high"', ' width="640" height="480"'),
     'картинок с fetchpriority="high"'),
    ("прелоад не совпадает с LCP", "index.html",
     ("sub", 'href="./assets/img/1002778-640x480.jpg" fetchpriority="high"',
      'href="./assets/img/38444064-640x480.jpg" fetchpriority="high"'), "картинка с fetchpriority=high"),
    ("прелоад тащит картинку из хвоста", "index.html",
     ("multi", [("index.html", "sub", 'href="./assets/img/1002778-640x480.jpg" fetchpriority="high"',
                 'href="./assets/img/31665655-120x120.jpg" fetchpriority="high"'),
                ("index.html", "sub", 'src="./assets/img/1002778-640x480.jpg" alt="Сладкие мандарины с веточкой" width="640" height="480" fetchpriority="high"',
                 'src="./assets/img/1002778-640x480.jpg" alt="Сладкие мандарины с веточкой" width="640" height="480"'),
                ("index.html", "sub", "</body>",
                 '<img src="./assets/img/31665655-120x120.jpg" alt="хвост" width="60" height="60" '
                 'loading="lazy" fetchpriority="high"></body>')]),
     "прелоад тащит картинку ниже каталога"),

    # --- CSP ---------------------------------------------------------------
    ("CSP снята", "index.html",
     ("sub", '<meta http-equiv="Content-Security-Policy"', '<meta http-equiv="X-Content-Security-Policy"'),
     "CSP: нет meta-политики"),
    ("CSP без connect-src", "index.html", ("sub", "connect-src 'self'; ", ""), "CSP: нет директивы connect-src"),
    ("script-src с unsafe-inline", "index.html",
     ("sub", "script-src 'self'; style-src", "script-src 'self' 'unsafe-inline'; style-src"),
     "script-src разрешает лишнее"),
    ("object-src не none", "index.html", ("sub", "object-src 'none'", "object-src 'self'"),
     "object-src должен быть 'none'"),
    ("base-uri отворён", "index.html", ("sub", "base-uri 'self'", "base-uri *"), "base-uri должен быть 'self'"),
    ("form-action отворён", "index.html", ("sub", "form-action 'self'", "form-action *"),
     "form-action должен быть 'self'"),
    ("img-src наружу", "index.html", ("sub", "img-src 'self' data:", "img-src 'self' data: https://pics.example.com"),
     "CSP: img-src отворён наружу"),
    ("frame-src не в Яндекс", "index.html", ("sub", "frame-src https://yandex.ru", "frame-src https://evil.example.com"),
     "frame-src пущен не только в yandex.ru"),
    ("inline-скрипт в разметке", "index.html",
     ("sub", '<script src="js/app-head.js"></script>', '<script>console.log(1)</script><script src="js/app-head.js"></script>'),
     "inline-скрипт с кодом в разметке"),
    ("data.js не подключён", "index.html", ("cut", r'[ ]*<script src="js/data\.js" defer></script>\n'),
     "ожидались три <script src=js/"),
    ("app-head ушёл в defer", "index.html",
     ("sub", '<script src="js/app-head.js"></script>', '<script src="js/app-head.js" defer></script>'),
     "должен грузиться синхронно"),
    ("data.js без defer", "index.html",
     ("sub", '<script src="js/data.js" defer></script>', '<script src="js/data.js"></script>'),
     "обязаны идти с defer"),
    ("onclick в разметке", "index.html",
     ("sub", 'class="swatch-btn swatch-market"', 'onclick="x()" class="swatch-btn swatch-market"'),
     "inline-обработчик on*= в разметке"),
    ("on*= ключом из JS", "js/app.js",
     ("sub", "el.innerHTML = `<span>${text}</span>", 'void {"onclick": 1}; el.innerHTML = `<span>${text}</span>'),
     "inline-обработчик on*= генерируется из JS"),
    ("onerror-атрибут строкой из JS", "js/app.js",
     ("sub", 'alt="${p.name}" width="640" height="480"', 'alt="${p.name}" onerror="__fdImgFallback(this)" width="640" height="480"'),
     "подвешает on*-атрибут строкой"),
    ("eval в JS", "js/app-head.js",
     ("sub", "img.src = 'data:image/svg+xml;charset=UTF-8,'", "img.src = eval('data:image/svg+xml;charset=UTF-8,')"),
     "под жёсткой CSP это либо смерть, либо дыра"),
    ("innerHTML из адреса страницы", "js/app.js",
     ("sub", "el.innerHTML = `<span>${text}</span>", "el.innerHTML = `<span>${location.hash}</span>"),
     "подставляет в innerHTML данные из адреса"),

    # --- хосты и ссылки ----------------------------------------------------
    ("чужой хост в css", "css/style.css",
     ("append", "\n/* https://evil.example.com/font.woff2 */\n"), "хост не в белом списке:"),
    ("js тянет sw.js с чужого cdn", "js/app.js",
     ("sub", "navigator.serviceWorker.register('sw.js')", "navigator.serviceWorker.register('//cdn.example.com/sw.js')"),
     "не на https по нашему пути"),

    # --- контракт JS ↔ DOM ↔ данные ---------------------------------------
    ("JS обращается к несуществующему id", "js/app.js",
     ("sub", "getElementById('sumGrand')", "getElementById('sumGrandzz')"), "обращается к id, которых нет в разметке"),
    ("атрибут из селектора исчез из разметки", "index.html",
     ("sub_all", 'data-set-theme="', 'data-xtheme="'), "JS читает [data-set-theme]"),
    ("JS читает dataset, которого нет", "js/app.js",
     ("sub", "tBtn.dataset.setTheme", "tBtn.dataset.setSkin"), "JS читает [data-set-skin]"),
    ("JS вырезан", "js/app.js", ("cut", r"[\s\S]+"), "разбор кода слепой"),
    ("таблица KEYS переименована", "js/data.js", ("sub", "const KEYS = {", "const LS_KEYS = {"), "нет таблицы KEYS"),
    ("JS читает несуществующий KEYS", "js/app.js",
     ("sub", "localStorage.setItem(KEYS.theme, name)", "localStorage.setItem(KEYS.themeV2, name)"),
     "читает KEYS, которых нет в таблице"),
    ("пакет и избранное не сохраняются", "js/data.js",
     ("multi", [("js/data.js", "sub", "cart:'fd.cart.v12',", "cartStore:'fd.cart.v12',"),
                ("js/data.js", "sub", "favs:'fd.favs.v12',", "favsStore:'fd.favs.v12',"),
                ("js/data.js", "sub", "orders:'fd.orders.v12'", "ordersStore:'fd.orders.v12'")]),
     "пакет/заявки/избранное не сохранятся"),
    ("ключ localStorage вне fd.*", "js/data.js", ("sub", "theme:'fd.theme',", "theme:'theme',"),
     "вне неймспейса fd.*"),
    ("localStorage мимо KEYS", "js/app-head.js",
     ("sub", "localStorage.getItem('fd.theme')", "localStorage.getItem('savedTheme')"), "localStorage трогается мимо KEYS"),

    # --- каталог и данные --------------------------------------------------
    ("каталог усох", "js/data.js",
     ("cut", r"const PRODUCTS = \[[\s\S]*?\n\];",
      "const PRODUCTS = [{id:'x',name:'Яблоки',cat:'fruits',unit:'кг',weightKg:1,price:null,oldPrice:null,"
      "photo:8138332,color:'#A8342E',season:[1],note:'нет'}];"),
     "усох до"),
    ("два товара с одним id", "js/data.js", ("sub", "id:'apple',", "id:'banana',"), "повторяющиеся id"),
    ("в данных появилась цена", "js/data.js", ("sub", "price:null,", "price:129,"), "появилась цена"),
    ("цена числом в data.js", "js/data.js", ("sub", "price:null,", "price:99,"), "data.js: числовая цена в каталоге"),
    ("photo не Pexels-id", "js/data.js", ("sub", "photo:8138332,", "photo:'banana.jpg',"),
     "photo должен быть числовым id Pexels"),
    ("color вне #RRGGBB", "js/data.js", ("sub", "color:'#A8342E',", "color:'A8342E',"), "color вне формата"),
    ("товар в несуществующем ряду", "js/data.js", ("sub", "cat:'fruits',", "cat:'greens',"), "лежит в ряду greens"),
    ("пустые поля у товара", "js/data.js", ("sub", "unit:'кг',", "unit:'',"), "пустые поля"),
    ("«часто берут вместе» на снятую позицию", "js/data.js",
     ("sub", "id:'grape',", "id:'grapezz',"), "ссылается на снятую позицию"),
    ("хит дня отсутствует в каталоге", "js/data.js",
     ("sub", "const DAILY_HITS = ['mandarin',", "const DAILY_HITS = ['mandarinzz',"), "отсутствует в каталоге"),
    ("хитов дня меньше трёх", "js/data.js",
     ("sub", "const DAILY_HITS = ['mandarin', 'tomato', 'walnut', 'churchkhela'];", "const DAILY_HITS = ['mandarin'];"),
     "хитов дня меньше трёх"),
    ("CURRENT_MONTH вне 1..12", "js/data.js",
     ("sub", "const CURRENT_MONTH=new Date().getMonth()+1;", "const CURRENT_MONTH=new Date().getMonth()+13;"),
     "CURRENT_MONTH вне 1..12"),
    ("в MONTHS тринадцать строк", "js/data.js",
     ("sub", "{num:12,short:'Дек'}", "{num:12,short:'Дек'},\n  {num:13,short:'Кто'}"),
     "MONTHS должен содержать 12 месяцев"),
    ("кадр галереи без подписи", "js/data.js",
     ("sub", "caption:'Свежие мандарины с зелёной веточкой'", "caption:''"), "кадр без фото или подписи"),
    ("color галереи вне формата", "js/data.js",
     ("sub", "{photo:1002778,color:'#D95823'", "{photo:1002778,color:'#D95'"), "галерея: color вне формата"),
    ("галерея пуста", "js/data.js",
     ("cut", r"const GALLERY_ITEMS = \[[\s\S]*?\n\];", "const GALLERY_ITEMS = [];"), "галерея пуста"),
    ("промокод в нижнем регистре", "js/data.js", ("sub", "'РЫНОК10'", "'рынок10'"), "не в верхнем регистре"),
    ("промокод без расшифровки", "js/data.js",
     ("sub", "label:'Промокод РЫНОК10 — минус 10%'", "label:''"), "нет человеческой расшифровки"),
    ("промокод обещает пересчёт суммы", "js/data.js",
     ("sub", "label:'Промокод ПРИВЕТ — минус 200 ₽'", "label:'Применяется к сумме заказа'"),
     "обещает пересчёт суммы"),

    # --- честность текстов -------------------------------------------------
    ("текст про СБП", "index.html", inject("СБП"), "упоминание СБП"),
    ("поле платёжной карты", "index.html", inject("CVC"), "поля платёжной карты"),
    ("текст про оплату", "index.html", inject("Оплачено"), "текст про оплату"),
    ("эквайринг", "index.html", inject("Эквайринг"), "эквайринг"),
    ("приём карт онлайн", "index.html", inject("оплатить картой"), "приём карт онлайн"),
    ("priceRange в разметке", "index.html", ("sub_all", '"@type": "GroceryStore"', '"priceRange": "100-500", "@type": "GroceryStore"'),
     "priceRange в разметке — цен нет"),
    ("выдуманное лицо продавца", "index.html", inject("Мадина"), "выдуманное лицо продавца"),
    ("гарантийное обещание", "index.html", inject("100% гарантия"), "гарантийное обещание"),
    ("ценовое обещание", "index.html", inject("самые низкие цены"), "ценовое обещание"),
    ("выдуманная аудитория", "index.html", inject("более 500 клиентов"), "выдуманная аудитория"),
    ("выдуманный стаж", "index.html", inject("12 лет на рынке"), "выдуманный стаж"),
    ("рейтинг, которого нет", "index.html", inject("4.9"), "рейтинг, которого нет на Яндекс Картах"),
    ("заглушка «по запросу» исчезла", "js/app.js", ("sub_all", "по запросу", "уточним"),
     "нет заглушки «по запросу»"),
    ("блок отзывов пропал", "index.html", ("sub", 'id="reviews"', 'id="reviewz"'), "нет блока отзывов"),
    ("рейтинг без виджета Яндекс Карт", "index.html",
     ("cut", r'[ ]*<iframe class="ya-badge"[\s\S]*?</iframe>\n'), "без виджета Яндекс Карт"),
    ("нет ссылки на настоящие отзывы", "index.html",
     ("sub_all", "yandex.ru/maps/org/fruktovy_dvorets/60838532953/reviews/", "yandex.ru/collections/card/x/"),
     "без ссылки на настоящие отзывы"),
    ("в блоке отзывов рукописные цитаты", "index.html",
     ("sub", '<h2 class="section-title">Отзывы <em>покупателей</em></h2>',
      '<h2 class="section-title">Отзывы <em>покупателей</em></h2><blockquote class="review-copy">«Вкусно»</blockquote>'),
     "появились hand-written цитаты"),
    ("цифра рейтинга и озвучка разошлись", "index.html",
     ("sub", '<b class="tnum">4,7</b>', '<b class="tnum">4,8</b>'), "разошёлся с озвученным"),
    ("гейт рейтинга ослеп", "index.html",
     ("sub", '<div class="review-stars" role="img" aria-label="Оценка 4,7 из 5">',
      '<div class="review-stars" role="img">'), "озвучка не найдены — гейт слепой"),
    ("звёздный рейтинг съехал", "index.html",
     ("sub_all", '              <svg class="icon"><use href="#ic-star"/></svg>\n', ""), "звёзд"),

    # --- JSON-LD -----------------------------------------------------------
    ("ld-catalog не подключён", "index.html",
     ("cut", r'[ ]*<script type="application/ld\+json" id="ld-catalog">[\s\S]*?</script>\n'),
     "ожидались JSON-LD магазина+FAQ"),
    ("JSON-LD битый", "index.html", ("sub", '"@type": "GroceryStore",', '"@type": "GroceryStore",,'),
     "JSON-LD не разбирается"),
    ("нет карточки магазина", "index.html", ("sub", '"@type": "GroceryStore"', '"@type": "Bakery"'),
     "нет карточки магазина"),
    ("у магазина нет телефона", "index.html", ("cut", r'[ ]*"telephone": "\+79000000000",\n'),
     "JSON-LD: у магазина нет "),
    ("вывеска в JSON-LD другая", "index.html",
     ("sub", '"name": "Фруктовый дворец",', '"name": "Фруктовый дворик",'), "название магазина не совпадает"),
    ("url в JSON-LD ≠ canonical", "index.html",
     ("sub", '"url": "https://ssrjkk.github.io/fruktovy/",', '"url": "https://ssrjkk.github.io/fruktovy/spb/",'),
     "не равен canonical"),
    ("@id магазина на чужом домене", "index.html",
     ("sub", '"@id": "https://ssrjkk.github.io/fruktovy/#store"', '"@id": "https://example.org/#store"'),
     "@id магазина вне нашего домена"),
    ("видимый FAQ разошёлся с JSON-LD", "index.html",
     ("sub", "<p>Да! Выберите в корзине", "<p>Да. Выберите в корзине"),
     "JSON-LD FAQ разошёлся"),
    ("адрес из JSON-LD не читается на странице", "index.html",
     ("sub", '"streetAddress": "Сытнинская ул., 12",', '"streetAddress": "Сытнинский проспект, 90",'),
     "не читается на странице"),
    ("телефон в JSON-LD не виден на странице", "index.html",
     ("sub", '"telephone": "+79000000000"', '"telephone": "+7-999-000-00-01"'),
     "не совпадает ни с одним видимым номером"),
    ("вопрос FAQ без ответа", "index.html",
     ("sub", '"name": "Как узнать точную цену дня перед покупкой?",\n            "acceptedAnswer": {\n              "@type": "Answer",\n              "text": "Цены на живой сезонный завоз обновляются утром. Сложите нужные позиции в пакет и отправьте список в WhatsApp — продавец сразу пришлёт актуальный расчёт и фото сегодняшней партии."',
      '"name": "Как узнать точную цену дня перед покупкой?",\n            "acceptedAnswer": {\n              "@type": "Answer",\n              "text": ""'),
     "вопрос FAQ без ответа"),
    ("ld-catalog короче каталога", "index.html",
     ("cut", r'\{"@type": "ListItem", "position": 1, "name": "Яблоки"\}, '), "против"),
    ("ld-catalog разошёлся с каталогом", "index.html",
     ("sub", '"position": 1, "name": "Яблоки"}', '"position": 1, "name": "Яблоко"}'), "разошёлся с каталогом"),
    ("порядок в ld-catalog перепутан", "index.html",
     ("sub", '"position": 2,', '"position": 22,'), "позиции перепутаны"),

    # --- сборка, фото, шрифты ---------------------------------------------
    ("PRODUCT_SIZES вырезан", "tools/build.py", ("cut", r"PRODUCT_SIZES = \[[^\]]*\]"),
     "не разобрать списки размеров"),
    ("размер карточки не скачивается", "js/app.js",
     ("sub", "pexels(p.photo, 640, 480)", "pexels(p.photo, 640, 481)"), "не скачивает 640x481"),
    ("галерейный размер не скачивается", "js/app.js",
     ("sub", "pexels(item.photo, 1200, 900)", "pexels(item.photo, 1200, 901)"), "не скачивает галерейный 1200x901"),
    ("app.js не зовёт pexels()", "js/app.js", ("sub_all", "pexels(", "px("), "картинки собираются незнамо откуда"),
    ("фото не собрано", "js/data.js", ("sub", "photo:8138332,", "photo:987654321,"), "нет собранного фото"),
    ("мусор от снятых позиций в assets/img", "assets/img/987654321-640x480.jpg", ("touch", 4096),
     "мусор от снятых позиций"),
    ("фото не прожаты", "assets/img/987654322-640x480.jpg", ("touch", 300_000), "фото не прожаты"),
    ("assets/fonts.css не собран", "assets/fonts.css", ("drop",), "нет assets/fonts.css"),
    ("fonts.css без @font-face", "assets/fonts.css", ("cut_all", r"@font-face\{[^}]*\}\n?"), "без @font-face"),
    ("css зовёт нескачанную гарнитуру", "css/style.css", ("sub_all", "'Manrope'", "'Manrope Extra'"),
     "которой нет в assets/fonts.css"),
    ("шрифт скачан, но не вызывается", "css/style.css",
     ("sub_all", "font-family: 'Cormorant Garamond', Georgia, serif;", "font-family: Georgia, serif;"),
     "скачан, но в css не вызывается"),
    ("вес 900 не скачан", "css/style.css",
     ("append", "\n.tnum { font-family: 'Manrope'; font-weight: 900; }\n"), "вес вызывается, а face не скачан"),
    ("fonts.css зовёт отсутствующий woff2", "assets/fonts.css",
     ("sub", "manrope-cyrillic-400.woff2", "manrope-cyrillic-777.woff2"), "fonts.css зовёт отсутствующий"),
    ("font-display снят", "assets/fonts.css", ("sub_all", "font-display:swap;", ""), "без font-display:swap"),
    ("css зовёт картинку в никуда", "css/style.css",
     ("append", '\n.arch-caption::after { background: url("img/nope-nope.jpg"); }\n'), "ведёт в никуда"),
    ("head ссылается на удалённый файл", "index.html",
     ("sub_all", 'href="assets/logo.svg"', 'href="assets/logo-gone.svg"'), "head: нет файла assets/logo-gone.svg"),

    # --- манифест, service worker -----------------------------------------
    ("name в манифесте разошёлся", "manifest.webmanifest",
     ("sub", '"name": "Фруктовый дворец"', '"name": "Фруктовый двор"'), "не равен вывеске"),
    ("иконки манифеста не на месте", "manifest.webmanifest",
     ("sub", '"src": "assets/icon-192.png"', '"src": "assets/icon-192x.png"'), "манифест: нет иконки"),
    ("sizes иконки кривые", "manifest.webmanifest", ("sub", '"sizes": "192x192"', '"sizes": "any"'), "sizes иконки"),
    ("maskable-иконки нет", "manifest.webmanifest", ("sub", '"purpose": "maskable"', '"purpose": "any"'),
     "нет maskable-иконки"),
    ("theme_color не hex", "manifest.webmanifest", ("sub", '"theme_color": "#1B4D3E"', '"theme_color": "green"'),
     "должен быть #RRGGBB"),
    ("theme-color в head разошёлся с манифестом", "index.html",
     ("sub", '<meta name="theme-color" content="#1B4D3E">', '<meta name="theme-color" content="#000000">'),
     "и в манифесте"),
    ("start_url уехал из подпадки", "manifest.webmanifest", ("sub", '"start_url": "./"', '"start_url": "/fruktovy/app/"'),
     "start_url/scope обязаны быть './'"),
    ("CORE пуст", "sw.js", ("cut", r'var CORE = \[[^\]]*\];', "var CORE = [];"), "пустой CORE"),
    ("CORE кэширует несуществующее", "sw.js", ("sub", '"./assets/logo.svg"', '"./assets/logo-x.svg"'),
     "кэширует несуществующий"),
    ("оболочка офлайна неполная", "sw.js", ("sub", '"./js/app-head.js", ', ""), "оболочка офлайна неполная"),
    ("фото ушли в прекеши", "sw.js",
     ("sub", '"./assets/icon-512.png"]', '"./assets/icon-512.png", "./assets/img/1002778-640x480.jpg"]'),
     "тащит фото в прекеши"),
    ("след js/main.js вернулся", "sw.js", ("sub", '"./js/app.js"', '"./js/main.js"'), "след удалённого файла js/main.js"),
    ("service worker никто не регистрирует", "js/app.js",
     ("sub", "navigator.serviceWorker.register('sw.js')", "void 0"), "никто не регистрирует"),

    # --- палитры и css -----------------------------------------------------
    ("палитры перестали разбираться", "css/style.css",
     ("multi", [("css/style.css", "sub_all", 'html[data-theme="', 'html[data-khim="'),
                ("css/style.css", "sub", ":root,", ".notroot,")]), "ни одной палитры не разобрано"),
    ("дефолтная палитра обесцвечена", "css/style.css",
     ("cut", r':root,\nhtml\[data-theme="market"\] \{[\s\S]*?\n\}', ':root,\nhtml[data-theme="market"] {\n}'),
     "нет ни одного токена"),
    ("палитра в css без объявления в данных", "js/data.js",
     ("cut", r"[ ]*night:'Ночной базар'\n"), "темы разошлись"),
    ("переключатель зовёт несуществующую палитру", "index.html",
     ("sub_all", 'data-set-theme="night"', 'data-set-theme="nightt"'), "переключатель предлагает"),
    ("дефолтная палитра не объявлена", "index.html",
     ("sub", '<html lang="ru" data-theme="market"', '<html lang="ru" data-theme="harvest"'), "не объявлена в THEME_LABELS"),
    ("подпись палитры нигде не показана", "js/data.js",
     ("sub", "night:'Ночной базар'", "night:'Ночной ряд'"), "нигде не показана"),
    ("css зовёт незадекларированную переменную", "css/style.css",
     ("sub", "outline: 2.5px solid var(--focus-ring);", "outline: 2.5px solid var(--focus-ringzz);"),
     "зовёт незадекларированные переменные"),
    ("скобки в css не сходятся", "css/style.css", ("append", "\n}\n"), "скобки не сходятся"),
    ("Safari остался без -webkit-backdrop", "css/style.css",
     ("cut", r'[ ]*-webkit-backdrop-filter: blur\(12px\);\n'), "без -webkit-"),
    ("кольцо фокуса снято", "css/style.css",
     ("sub", "outline: 2.5px solid var(--focus-ring);", "box-shadow: 0 0 0 2.5px var(--focus-ring);"),
     "нет правила :focus-visible с outline"),
    ("кольцо фокуса обнулено", "css/style.css",
     ("sub", "outline: 2.5px solid var(--focus-ring);", "outline: none;"),
     "нет правила :focus-visible с outline"),
    ("outline снят без кольца", "css/style.css",
     ("multi", [("css/style.css", "cut", r'[ ]*outline: 2\.5px solid var\(--focus-ring\);\n', ""),
                ("css/style.css", "append", "\na { outline: none; }\n")]),
     "снимает outline, не заменив его кольцом"),
    ("reduced-motion выключен", "css/style.css",
     ("cut", r"@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}"), "нет @media (prefers-reduced-motion"),
    ("reduced-motion ничего не гасит", "css/style.css",
     ("sub", ".ticker-track { animation: none;", ".ticker-track {"), "ничего не гасит"),
    ("JS не смотрит на reduced-motion", "index.html",
     ("multi", [("js/app-head.js", "sub", "matchMedia('(prefers-reduced-motion: reduce)')", "matchMedia('(prefers-motion: reduce)')"),
                ("js/app.js", "sub_all", "matchMedia('(prefers-reduced-motion: reduce)')", "matchMedia('(prefers-motion: reduce)')")]),
     "JS не смотрит на prefers-reduced-motion"),
    ("тап-цели на телефоне не защищены", "css/style.css",
     ("cut", r"@media \(pointer: coarse\) \{[\s\S]*?\n\}"), "нет @media (pointer: coarse)"),
    ("min-height тап-цели меньше 24px", "css/style.css",
     ("sub", ".cat-tab, .size-pill, .theme-pill, .wish-chip { min-height: 40px; }",
      ".cat-tab, .size-pill, .theme-pill, .wish-chip { min-height: 20px; }"), "меньше WCAG 2.5.8"),
    ("планки 44px для пальцев нет", "css/style.css",
     ("multi", [("css/style.css", "sub_all", "width: max(100%, 44px);", "width: max(100%, 40px);"),
                ("css/style.css", "sub_all", "height: max(100%, 44px);", "height: max(100%, 40px);"),
                ("css/style.css", "sub", ".chat-send-btn { min-width: 44px; min-height: 44px; }",
                 ".chat-send-btn { min-width: 40px; min-height: 40px; }"),
                ("css/style.css", "sub", ".modal-close { width: 44px; height: 44px; }",
                 ".modal-close { width: 40px; height: 40px; }")]),
     "нет планки 44px"),
    ("печать отключена", "css/style.css", ("sub", "@media print {", "@media screen {"), "нет @media print"),
    ("reduce оставил плавные перелёты по якорям", "css/style.css",
     ("sub", "  html { scroll-behavior: auto; }\n", ""), "прокрутка по якорям остаётся плавной"),
    ("в печати прячут то чего нет", "css/style.css",
     ("sub", ".btn, .msg-pill, .chat-send-btn { display: none !important; }",
             ".btn, .msg-pill, .chat-send-btn, .no-such-block { display: none !important; }"),
     "прячут несуществующее"),
    ("порог меню и порога бургера разошёлся", "css/style.css",
     ("sub", "@media (min-width: 1200px) { .main-nav { display: flex; } }",
             "@media (min-width: 1024px) { .main-nav { display: flex; } }"),
     "пороги шапки разошлись"),
    ("бургер не прячется вовсе", "css/style.css",
     ("sub", "@media (min-width: 1200px) { .burger-btn { display: none; } } /* тот же порог, что у .main-nav */", ""),
     "нигде не прячется"),
    ("меню разделов не включается вовсе", "css/style.css",
     ("sub", "@media (min-width: 1200px) { .main-nav { display: flex; } }", ""),
     "не включается ни одним @media"),
    ("класс без единого правила в css", "index.html",
     ("sub_all", 'class="brand-crest"', 'class="brand-crest-v2"'), "без единого правила в css"),

    # --- robots и sitemap --------------------------------------------------
    ("sitemap ведёт на чужой адрес", "sitemap.xml",
     ("sub", "<loc>https://ssrjkk.github.io/fruktovy/</loc>", "<loc>https://example.com/fruktovy/</loc>"),
     "не равен canonical"),
    ("sitemap канонизит index.html", "sitemap.xml",
     ("sub", "<loc>https://ssrjkk.github.io/fruktovy/</loc>", "<loc>https://ssrjkk.github.io/fruktovy/index.html</loc>"),
     "index.html должен быть каноничен"),
    ("robots указывает чужую карту", "robots.txt",
     ("sub", "https://ssrjkk.github.io/fruktovy/sitemap.xml", "https://example.com/sitemap.xml"), "чужой адрес"),
    ("robots без Sitemap", "robots.txt", ("cut", r"Sitemap: [^\n]*\n"), "нет строки Sitemap"),
    # --- заголовок, CSP, LCP-прелоад, сборка ------------------------------
    ("вывеска пропала из <title>", "index.html",
     ("sub", "<title>Фруктовый дворец —", "<title>Свежие фрукты —"),
     "head: в <title> нет названия магазина"),
    ("CSP отпускает чужие скрипты", "index.html",
     ("sub", "script-src 'self';", "script-src 'self' 'unsafe-inline';"),
     "CSP: script-src должен быть ровно"),
    ("вторую картинку помечают как LCP", "index.html",
     ("sub", "</body>",
      '<img src="./assets/img/31665655-120x120.jpg" alt="дубль" width="60" height="60" '
      'loading="lazy" fetchpriority="high"></body>'),
     "а должна быть одна"),
    ("FAQ остался без разметки", "index.html",
     ("sub", '"@type": "FAQPage"', '"@type": "FaqPage"'),
     "а в JSON-LD его нет"),
    ("robots потерял canonical", "robots.txt",
     ("sub", "https://ssrjkk.github.io/fruktovy/sitemap.xml", "https://example.com/sitemap.xml"),
     "нет canonical"),
    ("сборка не тащит размер карточки", "tools/build.py",
     ("sub", "PRODUCT_SIZES = [(640, 480), (900, 675), (240, 180),",
      "PRODUCT_SIZES = [(640, 480), (900, 675),"),
     "карточка останется без фото"),
    ("сборка не тащит галерейный размер", "tools/build.py",
     ("sub", "GALLERY_SIZES = [(640, 480), (1200, 900)]", "GALLERY_SIZES = [(640, 480)]"),
     "не скачивает галерейный"),
    ("палитра night не красит токен", "css/style.css",
     ("cut", r'(html\[data-theme="night"\]\s*\{[\s\S]*?)\n?\s*--ink-muted:\s*#[0-9A-Fa-f]+;', r"\1"),
     "не переопределяет токены:"),
    ("кнопка посветлела до нечитаемого", "css/style.css",
     ("sub", "--accent: #C84B28;", "--accent: #F0A08A;"), "«основная кнопка»"),
    ("карточка стала тёмной под тёмным текстом", "css/style.css",
     ("sub", "--surface: #FFFDF9;", "--surface: #2A231D;"), "текст на карточке"),
    ("кольцо фокуса обесцвечено в бумагу", "css/style.css",
     ("multi", [("css/style.css", "sub", "--focus-ring: #221B15;", "--focus-ring: #E8DFCE;"),
                ("css/style.css", "sub", "--focus-halo: #FFFDF9;", "--focus-halo: #F7F1E6;")]),
     "кольцо фокуса на"),
    ("палитра осталась без ореола", "css/style.css",
     ("cut", r"[ ]*--focus-halo: #FFFDF9;\n"), "нет пары --focus-ring/--focus-halo"),
    ("цвет шапки стал ссылкой вместо цвета", "css/style.css",
     ("sub", "--header-ink: #141619;", "--header-ink: var(--нет-такой);"), "не разобрались цвета"),
    ("резервный фон стал ссылкой вместо цвета", "css/style.css",
     ("sub", "--bg-alt: #E9ECEF;", "--bg-alt: var(--нет-такой);"), "не разобрался фон"),

    # --- вес ассетов -------------------------------------------------------
    ("og.png раздулся", "assets/og.png", ("nul", 300_000), "фото не прожаты"),
]

# Сообщения, собранные целиком из переменных: статистики для сверки нет,
# поэтому руками указываем, какой кейс их всё-таки кусает.
EXEMPT = {
    '"index.html: " + "; ".join(doc.err[:6])': "агрегатор ошибок разметки: кусает кейс «не закрыт h1», "
                                              "из статики в сообщении только имя файла",
    'img#{i}': "шаблон без статики; кусают кейсы «картинка без alt» и «loading=fast»",
    '{src_name}: {why}': "это обёртка оборотов FORBIDDEN: их покрытие сверяется отдельно, списком whys",
}

ONLY = None
if "--only" in sys.argv:
    ONLY = sys.argv[sys.argv.index("--only") + 1]

# ============================================================ покрытие ====
CHECK_SRC = (ROOT / "tools" / "check.py").read_text(encoding="utf-8")


def err_messages(src):
    """Каждый ERR.append(...) → список его статических кусков (плейсхолдеры f-строк вырезаны)."""
    out = []
    for m in re.finditer(r"ERR\.append\(", src):
        i, depth = m.end(), 1
        while i < len(src) and depth:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        arg = src[m.end():i - 1]
        chunks = []
        for trip, trip2, dbl, sgl in re.findall(
                r'"""([\s\S]*?)"""|\'\'\'([\s\S]*?)\'\'\'|"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'', arg):
            lit = next((x for x in (trip, trip2, dbl, sgl) if x), "")
            for part in re.split(r"\{[^{}]*\}", lit):
                part = part.strip()
                if len(part) >= 6:
                    chunks.append(part)
        out.append((arg, chunks))
    return out


def forbidden_whys(src):
    block = re.search(r"FORBIDDEN = \[([\s\S]*?)\n\]", src)
    return [w for _, w in re.findall(r'\(r?"([^"]+)",\s*"([^"]+)"\)', block.group(1))] if block else []


def covered(chunks, wants):
    for c in chunks:
        for w in wants:
            if c in w or w in c:
                return True
    return False


recover()
state = snapshot()
fails = []
fired = []          # строки FAIL, которые гейт реально выдал при прогоне: f-сообщение
                    # покрыто, если его статический кусок всплыл в живом выводе, — иначе
                    # имя пары, зашитое в переменную, нечем проверить и гейт молчал бы.
try:
    for case in CASES:
        name, target, kind, want = case
        if ONLY and ONLY not in name and ONLY not in want:
            continue
        apply_case(target, kind)
        rc, out = run_gate()
        ok = rc == 1 and want in out
        print(("BITES  " if ok else "WEAK   ") + name + f"  (rc={rc}, want={want!r})", flush=True)
        if ok:
            fired += [ln for ln in out.splitlines() if ln.startswith(" - ")]
        else:
            fails.append((name, out.strip().splitlines()[:6]))
        restore(state)
finally:
    restore(state)
    # Снимок живёт только пока идёт прогон: оставить его — значит при следующем старте
    # recover() вернул бы байты прошлого прогона поверх того, что починили между запусками.
    shutil.rmtree(JDIR, ignore_errors=True)

rc, out = run_gate()
print("restored tree gate rc=%d %s" % (rc, out.strip().splitlines()[-1:]))

wants = [w for _, _, _, w in CASES]
msgs = err_messages(CHECK_SRC)
by_exile = lambda arg: any(k in arg for k in EXEMPT)
silent = [arg.replace("\n", " ")[:90] for arg, chunks in msgs
          if chunks and not covered(chunks, wants) and not by_exile(arg)
          and not any(any(c in ln for c in chunks) for ln in fired)]
naked = [arg.replace("\n", " ")[:90] for arg, chunks in msgs if not chunks and not by_exile(arg)]
fb_wants = [w for w in forbidden_whys(CHECK_SRC) if not covered([w], wants)]
for note, lst in (("гейт без мутации", silent), ("гейт целиком из переменных", naked),
                  ("оборот FORBIDDEN без мутации", fb_wants),
                  ("устаревшая поблажка EXEMPT", [k for k in EXEMPT if covered([k], wants)])):
    for item in lst:
        print(f"{note}: {item}")
print(f"гейтов: {len(msgs)}, forbidden-оборотов: {len(forbidden_whys(CHECK_SRC))}, мутаций: {len(CASES)}")
sys.exit(1 if fails or rc != 0 or silent or naked or fb_wants else 0)
