# Фруктовый — сайт-каталог с корзиной и заказом в WhatsApp

Одностраничный сайт магазина «Фруктовый» (СПб, Сытнинская ул., 12):
каталог с поиском и фильтрами, корзина с повтором заказа, конструктор наборов,
сезонный календарь, галерея с лайтбоксом, заказ через WhatsApp.
Чистые HTML/CSS/JS без сборки фреймворков; все ассеты self-hosted, ноль трекеров.

## Структура

```
index.html            страница (разметка + inline SVG-спрайт иконок)
css/style.css         стили (вынесены из страницы, минифицируются сборкой)
js/data.js            данные: магазин, категории, товары, галерея
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
python tools/build.py        # фото (Pexels), шрифты (OFL), vendor (MIT/GSAP), QR на сайт
python tools/test_cart.py
python tools/check.py
python -m http.server 8080   # и открыть http://localhost:8080
```

`build.py` идемпотентен; `--no-minify` оставляет читаемые css/js.
Сгенерированные ассеты (vendor/, assets/img, шрифты, og, иконки) в git не хранятся —
их собирает CI на каждом деплое.

## Деплой

1. Репозиторий на GitHub → загрузить файлы (включая `.github/workflows/deploy.yml`).
2. Settings → Pages → Source: **GitHub Actions**.
3. Push в `main` → job `quality` (secret scan, сборка, тесты, гейт) → деплой на Pages.

Canonical-адрес: `https://ssrjkk.github.io/fruktovy/`. При подключении своего
домена заменить адрес в `index.html` (canonical, og:url), `robots.txt`, `sitemap.xml`.

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

Фото — Pexels License; шрифты Manrope и Cormorant Garamond — SIL OFL 1.1;
Swiper и Lenis — MIT; GSAP/ScrollTrigger — GreenSock standard license.
Полный список — `assets/CREDITS.txt` после сборки.

---

## English (brief)

Single-page catalog site for a fruit & vegetable shop in Saint Petersburg:
searchable catalog, WhatsApp ordering, basket builder, seasonal calendar, gallery.
Vanilla HTML/CSS/JS, all assets self-hosted, zero trackers. CI (`quality` job) runs a
secret scan, builds assets (Pexels photos, OFL fonts, MIT vendors), executes cart unit
tests in a real JS engine and a quality gate, then deploys to GitHub Pages.
Run locally: `pip install pillow rcssmin rjsmin esprima quickjs qrcode`, then
`python tools/build.py && python tools/test_cart.py && python tools/check.py`.