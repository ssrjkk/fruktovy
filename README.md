# Фруктовый — сайт-каталог с корзиной и заказом в WhatsApp

Одностраничный сайт магазина «Фруктовый» (СПб, Сытнинская ул., 12):
каталог с поиском и фильтрами, корзина с повтором заказа, конструктор наборов,
сезонный календарь, галерея с лайтбоксом, две темы оформления, заказ через WhatsApp.
Чистые HTML/CSS/JS без сборки фреймворков; все ассеты self-hosted, ноль трекеров.

## Структура

```
index.html            страница (разметка + inline SVG-спрайт иконок)
css/style.css         стили (вынесены из страницы, минифицируются сборкой)
css/themes.css        токены второй темы «Рынок», разметка общая
js/data.js            данные: магазин, категории, товары, галерея
js/theme.js           тема до первой отрисовки: localStorage → data-theme
js/main.js            приложение: корзина, конструктор, сезоны, лайтбокс
sw.js                 офлайн-кэш (версию проставляет сборка)
tools/build.py        сборка: vendor, шрифты, фото, og, SEO-каталог, минификация
tools/test_cart.py    юнит-тесты корзины в quickjs (код вырезается из js/main.js)
tools/check.py        гейт качества: разметка, JSON-LD, ссылки, иконки, CSP, sitemap
.github/workflows/deploy.yml  CI: secret scan → сборка → тесты → гейт → Pages
```

## Локальный запуск

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install pillow rcssmin rjsmin esprima quickjs qrcode
python tools/build.py --no-minify   # фото (Pexels), шрифты (OFL), vendor (MIT/GSAP), QR на сайт
python tools/test_cart.py
python tools/check.py
python -m http.server 8080   # и открыть http://localhost:8080
```

`build.py` идемпотентен, но минификацию делает НАД ИСХОДНИКАМИ: `python tools/build.py`
перетирает `css/style.css` и все `js/*.js` их jsmin-версией, а заодно обновляет версию кэша
service worker и lastmod в sitemap. Локально поэтому запускают `--no-minify` — читаемые css/js
нужны не только для глаз: `tools/gate_bite.py` ищет правила мутаций по исходному тексту,
и на переминифицированном дереве он падает на собственном якоре. В CI это безопасно —
там своя копия репозитория, и боевой (минифицированный) вид CI собирает сам.
Сгенерированные ассеты (vendor/, assets/img, шрифты, og, иконки) в git не хранятся —
их собирает CI на каждом деплое. Если Pexels не отдал фото, сборка падает с `PHOTO FAIL`
и пишет плейсхолдеры только в рабочую копию: красная сборка перезапускается, а витрина
с градиентными плитками вместо фруктов висела бы до первого взгляда.

## Деплой

1. Репозиторий на GitHub → загрузить файлы (включая `.github/workflows/deploy.yml`).
2. Settings → Pages → Source: **GitHub Actions**.
3. Push в `main` → job `quality` (secret scan, сборка, тесты, гейт) → деплой на Pages.

Canonical-адрес: `https://ssrjkk.github.io/fruktovy/`. При подключении своего
домена заменить адрес в `index.html` (canonical, og:url), `robots.txt`, `sitemap.xml`.

## Темы оформления

Два варианта дизайна одного и того же сайта: переключатель «Тема оформления» в первом
экране — «Пергамент» и «Рынок на паллетах». Разметка и данные общие, отличаются только
стили. Выбор хранится в localStorage (`fd.theme.v1`) и восстанавливается до первой
отрисовки, поэтому вспышки чужой темы при загрузке нет.

- `css/style.css` — базовая тема «Пергамент»; без `themes.css` сайт остаётся рабочим.
- `css/themes.css` — тема «Рынок на паллетах»: под `[data-theme=market]` переопределены
  токены (палитра, фактуры дерева) и правила заголовков, шапки, кнопок и карточек;
  узкий гротеск Oswald держится здесь же. Всё, что вне этого префикса, — базовая тема.
- `js/theme.js` — читает сохранённый выбор и ставит `data-theme` на `<html>` до CSS;
  отдельный файл, потому что CSP сайта запрещает инлайновые скрипты.
- `js/main.js` — `setTheme()` синхронизирует кнопки и `aria-pressed`.

Какую тему согласует заказчик, та и остаётся. Чтобы убрать вторую, достаточно удалить
`css/themes.css`, `js/theme.js`, блок `.theme-switch` в первом экране, ссылки на оба файла
в `index.html`, `setTheme` в `js/main.js` и две строки в кэше `sw.js` — базовая тема при этом
не требует правок.

## Данные и цены

Цены намеренно `null` («цена по запросу») — продавец подтверждает цену дня в WhatsApp.
Чтобы включить цены, проставить `price` в `js/data.js`; корзина и SEO подхватят сами.

Позиция в `PRODUCTS` — это и есть витрина: `name`, `unit`, `price`, `photo` (id снимка
Pexels или свой файл в `assets/img`), `season` (месяцы), `use` (что из этого на кухне)
и `store` (как хранить его дома). Правка `js/data.js` не требует сборки: push в `main`,
CI соберёт и выложит на Pages. `tools/check.py` не даст оставить позицию без описания,
без заметки о хранении и без решения, когда грузить её фото.

## Что нужно от магазина, чтобы сайт работал сам

- Цены — хотя бы ориентир по позициям: тогда корзина и конструктор наборов начнут считать итог.
- Свои снимки прилавка вместо стоковых: сейчас пять групп товаров делят одни и те же фото.
- Часы работы и оба телефона: они живут в `SHOP`, а `openingHours`, `telephone` и
  `alternateTelephone` в JSON-LD гейт сверяет с `data.js` — разъезд ломает сборку.
- Домен: при подключении достаточно заменить адрес в `index.html` (canonical, og:url),
  `robots.txt` и `sitemap.xml`.

## Лицензии ассетов

Фото — Pexels License; шрифты Manrope, Cormorant Garamond и Oswald — SIL OFL 1.1;
Swiper и Lenis — MIT; GSAP/ScrollTrigger — GreenSock standard license.
Полный список — `assets/CREDITS.txt` после сборки.

---

## English (brief)

Single-page catalog site for a fruit & vegetable shop in Saint Petersburg:
searchable catalog, WhatsApp ordering, basket builder, seasonal calendar, gallery.
Two swappable themes (default "Parchment" and "Market") share one markup: everything that
belongs to the second one sits under the `[data-theme=market]` prefix in `css/themes.css`,
the choice lives in `localStorage` and is applied before first paint by `js/theme.js` —
details in «Темы оформления» above.
Vanilla HTML/CSS/JS, all assets self-hosted, zero trackers. CI (`quality` job) runs a
secret scan, builds assets (Pexels photos, OFL fonts, MIT vendors), executes cart unit
tests in a real JS engine and a quality gate, then deploys to GitHub Pages.
Run locally: `pip install pillow rcssmin rjsmin esprima quickjs qrcode`, then
`python tools/build.py --no-minify && python tools/test_cart.py && python tools/check.py`
(the plain build minifies the tracked css/js in place — that step belongs to CI, see «Локальный запуск»).