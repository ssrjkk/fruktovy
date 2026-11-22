#!/usr/bin/env node
/* Статический гейт витрины «Фруктовый дворец».
   Запуск: node scripts/gate.mjs          (локально, из корня репозитория)
   В CI:  jobs.quality → шаг «Quality gate».
   Гейт fail-closed: любая просадка порога или отсутствующий файл = exit 1. */

import { readFileSync, existsSync, readdirSync } from 'node:fs';

const ROOT = process.cwd();
const PAGE = readFileSync(`${ROOT}/index.html`, 'utf8');
const PAGE404 = readFileSync(`${ROOT}/404.html`, 'utf8');
const ROBOTS = readFileSync(`${ROOT}/robots.txt`, 'utf8');
const SITEMAP = readFileSync(`${ROOT}/sitemap.xml`, 'utf8');
const MANIFEST = JSON.parse(readFileSync(`${ROOT}/manifest.webmanifest`, 'utf8'));
const FONTSCSS = readFileSync(`${ROOT}/assets/fonts.css`, 'utf8');

const fails = [];
const notes = [];
const MIN_TEXT = 4.5; // WCAG 2.1 AA для обычного текста; по замерам худшая пара — 5.32:1
let checks = 0;

const ok = (cond, label, detail = '') => {
  checks++;
  if (cond) notes.push(`  ok   ${label}${detail ? ' — ' + detail : ''}`);
  else fails.push(`${label}${detail ? ' — ' + detail : ''}`);
  return cond;
};

/* ---------- 1. форма документа ---------- */
ok(PAGE.startsWith('<!DOCTYPE html>'), 'doctype первой строкой');
ok(/<\/html>\s*$/.test(PAGE), '</html> последней строкой');
ok(!PAGE.includes('\r\n'), 'файл на LF, без CRLF');
ok(!PAGE.includes('\uFFFD'), 'нет битых символов кодировки');

/* ---------- 2. только свой источник ---------- */
const ORIGIN = 'https://ssrjkk.github.io/fruktovy';
const ALLOWED_HOSTS = ['ssrjkk.github.io', 't.me', 'yandex.ru', 'maps.yandex.ru', 'schema.org', 'www.w3.org'];
const hosts = [...new Set([...PAGE.matchAll(/https?:\/\/([a-z0-9.-]+)/gi)].map((m) => m[1].toLowerCase()))];
const foreign = hosts.filter((h) => !ALLOWED_HOSTS.includes(h));
ok(foreign.length === 0, 'посторонних хостов нет', foreign.join(',') || `разрешённые: ${hosts.length}`);
ok(!/images\.pexels|fonts\.googleapis|fonts\.gstatic|unpkg|jsdelivr|cdn\./.test(PAGE), 'ни CDN-фото, ни CDN-шрифтов');
ok(/fruktovy-dvorets\.ru/.test(PAGE) === false, 'домен-заглушка вычищен');
ok(PAGE.includes(`href="${ORIGIN}/"`), 'canonical на Pages-адрес');
ok(PAGE.includes(`content="${ORIGIN}/"`), 'og:url на Pages-адрес');
ok(ROBOTS.includes(`Sitemap: ${ORIGIN}/sitemap.xml`), 'robots указывает на sitemap');
ok(SITEMAP.includes(`<loc>${ORIGIN}/</loc>`), 'sitemap на Pages-адрес');
ok(/Content-Security-Policy/.test(PAGE), 'CSP объявлен');
const csp = (PAGE.match(/Content-Security-Policy" content="([^"]+)"/) || [])[1] || '';
ok(/img-src 'self' data:/.test(csp), 'CSP img-src только self', csp.slice(0, 40));
ok(/object-src 'none'/.test(csp) && /base-uri 'self'/.test(csp), 'CSP object-src/base-uri закрыты');

/* ---------- 3. локальные пути существуют ---------- */
const staticRefs = [...PAGE.matchAll(/(?:src|href)="((?!https?:|data:|#|mailto:|tel:)[^"]+)"/g)]
  .map((m) => m[1].replace(/^\.\//, ''))
  .filter((r) => !r.includes('${') && !r.includes('['));
const missingRefs = [...new Set(staticRefs)].filter((r) => !existsSync(`${ROOT}/${r.split('?')[0]}`));
ok(missingRefs.length === 0, 'все статические ссылки ведут на файлы репозитория', missingRefs.join(', ') || `${new Set(staticRefs).size} ссылок`);
const fontFiles = [...new Set([...FONTSCSS.matchAll(/url\("(fonts\/[^"]+)"\)/g)].map((m) => m[1]))];
const missingFonts = fontFiles.filter((f) => !existsSync(`${ROOT}/assets/${f}`));
ok(fontFiles.length >= 8 && missingFonts.length === 0, 'подмножества шрифтов на диске', `${fontFiles.length} файлов`);
const families = [...new Set([...FONTSCSS.matchAll(/font-family:\s*"([^"]+)"/g)].map((m) => m[1]))];
const cyrSubsets = fontFiles.filter((f) => /cyrillic/.test(f));
ok(families.every((f) => cyrSubsets.some((p) => p.includes(f.toLowerCase().replace(/\s+/g, '-')))), 'у каждой семьи есть cyrillic-подмножество', families.join(', '));
const usedFamilies = [...new Set([...PAGE.matchAll(/font-family:\s*([^;{}]+)/g)].flatMap((m) => m[1].split(',').map((x) => (x.match(/"([^"]+)"/) || [])[1]).filter(Boolean)))];
const unknownFamilies = usedFamilies.filter((f) => !families.includes(f) && !['serif', 'sans-serif', 'system-ui'].some((g) => f.toLowerCase().includes(g)));
ok(unknownFamilies.length === 0, 'все используемые семьи подключены', unknownFamilies.join(',') || usedFamilies.join(', '));

/* ---------- 4. каталог: 25 позиций и целостность данных ---------- */
const productBlock = PAGE.slice(PAGE.indexOf('const PRODUCTS = ['), PAGE.indexOf('];', PAGE.indexOf('const PRODUCTS = [')));
const ids = [...productBlock.matchAll(/\{ id: '([^']+)'/g)].map((m) => m[1]);
ok(ids.length === 25, 'позиций в каталоге 25', `факт ${ids.length}`);
ok(new Set(ids).size === 25, 'id позиций уникальны');
const descs = [...productBlock.matchAll(/desc: '([^']*)'/g)].map((m) => m[1]);
ok(descs.length === 25, 'у каждой позиции есть описание вкуса', `найдено ${descs.length}`);
const shortDesc = descs.filter((d) => d.trim().length < 25);
ok(shortDesc.length === 0, 'описания не короче 25 знаков', `коротких ${shortDesc.length}`);
ok(descs.every((d) => !/[\r\n]/.test(d)), 'описания в одну строку');
const photos = [...productBlock.matchAll(/photo: (\d+)/g)].map((m) => m[1]);
ok(new Set(photos).size === 25, 'фото не повторяются между позициями', `уникальных ${new Set(photos).size}`);
const prices = [...productBlock.matchAll(/price: (\d+)/g)].map((m) => +m[1]);
ok(prices.length === 25 && prices.every((p) => p > 0), 'все цены положительные', `мин ${Math.min(...prices)} ₽`);
const seasonSets = [...productBlock.matchAll(/season: \[([\d,\s]+)\]/g)].map((m) => m[1].split(',').map((x) => +x.trim()));
const badSeason = seasonSets.filter((s) => s.some((v, i) => v < 1 || v > 12 || (i > 0 && v <= s[i - 1])));
ok(badSeason.length === 0, 'месяцы сезона идут по возрастанию 1..12', `нарушений ${badSeason.length}`);

/* ---------- 5. каждый генерируемый путь к фото лежит в репозитории ---------- */
const template = (PAGE.match(/const photoSrc = \(id, w = (\d+), h = (\d+)\) => `([^`]+)`;/) || []).slice(1);
ok(template.length === 3, 'шаблон пути к фото найден', template.join(' '));
const sizes = new Set([template[0] + 'x' + template[1]]);
for (const m of PAGE.matchAll(/photoSrc\([^,]+,\s*(\d+),\s*(\d+)\)/g)) sizes.add(m[1] + 'x' + m[2]);
const galleryIds = [...new Set([...PAGE.matchAll(/GALLERY_ITEMS = \[[\s\S]{0,4000}?\];/g)].flatMap((m) => [...m[0].matchAll(/photo: (\d+)/g)].map((x) => x[1])))];
const neededIds = [...new Set([...photos, ...galleryIds])];
const missingImg = [];
for (const id of neededIds) for (const size of sizes) {
  const [w, h] = size.split('x');
  if (!existsSync(`${ROOT}/assets/img/${id}-${w}x${h}.jpg`)) missingImg.push(`${id}-${w}x${h}`);
}
ok(missingImg.length === 0, 'все варианты кадров собраны локально', `${neededIds.length} id x ${sizes.size} размеров${missingImg.length ? ': ' + missingImg.slice(0, 6).join(', ') : ''}`);
ok(template[2].startsWith('assets/img/'), 'шаблон ведёт в assets/img, а не на чужой CDN', template[2]);

/* ---------- 6. Baymard: числовое поле в карточке ---------- */
ok(/<input type="number" class="qty-direct-input/.test(PAGE), 'в карточке есть прямой числовой ввод');
const stepperCss = (PAGE.match(/\.qty-stepper \{([\s\S]*?)\}/) || [])[1] || '';
const inputCss = (PAGE.match(/\.qty-direct-input \{([\s\S]*?)\}/) || [])[1] || '';
const h = (css, prop) => +((css.match(new RegExp(`${prop}:\\s*(\\d+)px`)) || [])[1] || 0);
ok(h(stepperCss, 'height') === 44, 'строка степпера 44px (Zero-CLS)', `${h(stepperCss, 'height')}px`);
ok(h(inputCss, 'height') >= 44 && h(inputCss, 'width') >= 44, 'числовое поле не меньше 44x44 (цель касания)', `${h(inputCss, 'width')}x${h(inputCss, 'height')}px`);
ok(/min="1"/.test(PAGE) && /max="30"/.test(PAGE), 'у поля заданы границы 1..30');

/* ---------- 7. промокод свёрнут, поля помечены ---------- */
ok(/class="promo-toggle-link"[^>]*aria-expanded="false"/.test(PAGE), 'промокод свёрнут по умолчанию');
ok(/РЫНОК10/.test(PAGE) && /ПРИВЕТ/.test(PAGE), 'оба промокода объявлены');
const reqMarks = (PAGE.match(/\(обязательно\)/g) || []).length;
const optMarks = (PAGE.match(/\(необязательно\)/g) || []).length;
ok(reqMarks >= 2 && optMarks >= 1, 'поля чекаута помечены по обязательности', `${reqMarks} обязательно / ${optMarks} необязательно`);

/* ---------- 8. FAQ совпадает с JSON-LD znak v znak ---------- */
const ld = JSON.parse((PAGE.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/) || [])[1]);
const graph = ld['@graph'] || [];
const store = graph.find((g) => g['@type'] === 'GroceryStore');
const faqLd = graph.find((g) => g['@type'] === 'FAQPage');
ok(!!store && !!faqLd, 'JSON-LD содержит GroceryStore и FAQPage');
ok(!JSON.stringify(ld).includes('aggregateRating'), 'в JSON-LD нет self-serving aggregateRating', 'рейтинг остаётся видимым и ведёт на sameAs');
ok((store?.sameAs || '').includes('yandex.ru/maps/org/'), 'карточка организации указана в sameAs', store?.sameAs || '');
const norm = (t) => t.replace(/\s+/g, ' ').trim();
const faqHtml = [...PAGE.matchAll(/<details class="faq-item"[^>]*>\s*<summary>([^<]+)<span>\+<\/span><\/summary>\s*<p>([^<]+)<\/p>/g)]
  .map((m) => [norm(m[1]), norm(m[2])]);
ok(faqHtml.length === faqLd?.mainEntity?.length, 'вопросов в HTML и JSON-LD одинаково', `${faqHtml.length} против ${faqLd?.mainEntity?.length}`);
const drift = [];
(faqLd?.mainEntity || []).forEach((q, i) => {
  const [hq, ha] = faqHtml[i] || ['', ''];
  if (norm(q.name) !== hq) drift.push(`вопрос #${i + 1}`);
  if (norm(q.acceptedAnswer.text) !== ha) drift.push(`ответ #${i + 1}`);
});
ok(drift.length === 0, 'формулировки FAQ синхронизированы', drift.join(', ') || `${faqHtml.length} пары 1:1`);

/* ---------- 9. контраст по токенам всех пяти палитр ---------- */
function parseColor(str) {
  const hex = str.match(/^#([0-9a-f]{3,8})$/i);
  if (hex) {
    let f = hex[1];
    if (f.length === 3) f = f.split('').map((c) => c + c).join('');
    return { r: parseInt(f.slice(0, 2), 16), g: parseInt(f.slice(2, 4), 16), b: parseInt(f.slice(4, 6), 16), a: parseInt(f.slice(6, 8) || 'ff', 16) / 255 };
  }
  const rgb = str.match(/rgba?\(([\d.\s,]+)\)/);
  if (rgb) {
    const [r, g, b, a = 1] = rgb[1].split(',').map((x) => parseFloat(x));
    return { r, g, b, a };
  }
  return null;
}
const over = (fg, bg) => ({
  r: fg.r * fg.a + bg.r * (1 - fg.a),
  g: fg.g * fg.a + bg.g * (1 - fg.a),
  b: fg.b * fg.a + bg.b * (1 - fg.a),
  a: 1,
});
const lum = (c) => {
  const f = (v) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
};
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const themeBlocks = [...PAGE.matchAll(/:root,\s*html\[data-theme="market"\]\s*\{([\s\S]*?)\}|html\[data-theme="([a-z]+)"\]\s*\{([\s\S]*?)\n    \}/g)];
const palettes = [];
const rootBlock = (PAGE.match(/:root,\s*html\[data-theme="market"\]\s*\{([\s\S]*?)\n    \}/) || [])[1] || '';
const parseDecls = (body) => {
  const map = {};
  for (const m of body.matchAll(/(--[a-z0-9-]+):\s*([^;]+);/g)) map[m[1]] = m[2].trim();
  return map;
};
if (rootBlock) palettes.push(['market', parseDecls(rootBlock)]);
for (const m of PAGE.matchAll(/html\[data-theme="(light|fig|emerald|night)"\]\s*\{([\s\S]*?)\n    \}/g)) palettes.push([m[1], parseDecls(m[2])]);
ok(palettes.length === 5, 'палитр в css пять', palettes.map((p) => p[0]).join(', '));

const pairs = [
  ['--ink', '--bg', 'текст на фоне страницы'],
  ['--ink-muted', '--bg', 'вторичный текст на фоне'],
  ['--ink', '--surface', 'текст на карточке'],
  ['--ink-muted', '--surface', 'вторичный текст на карточке'],
  ['--accent-ink', '--accent', 'текст на акцентной кнопке'],
  ['--brand-ink', '--brand', 'текст на брендовой кнопке'],
  ['--chalk-ink', '--chalk-bg', 'мел на доске'],
  ['--chalk-muted', '--chalk-bg', 'приглушённый мел'],
  ['--gold-ink', '--gold', 'текст на золотой плашке'],
  ['--hero-muted', '--hero-bg', 'подпись в первом экране'],
  ['--header-muted', '--header-bg', 'пунктир шапки'],
  ['--fresh-ink', '--fresh', 'бейдж «в сезоне» и счётчик месяцев'],
  ['--hero-ink', '--hero-bg', 'заголовок первого экрана'],
  ['--ink', '--bg-alt', 'текст на приглушённом фоне секций'],
];
const worst = { v: 99, label: '' };
const perTheme = [];
for (const [name, tok] of palettes) {
  for (const [fgK, bgK, label] of pairs) {
    const fgRaw = tok[fgK], bgRaw = tok[bgK];
    if (!fgRaw || !bgRaw) { fails.push(`токен ${fgK} или ${bgK} не найден в палитре ${name}`); checks++; continue; }
    const fg = parseColor(fgRaw), bg = parseColor(bgRaw);
    if (!fg || !bg) { fails.push(`не разобран цвет ${fgK}=${fgRaw} в ${name}`); checks++; continue; }
    const r = ratio(over(fg, bg), bg);
    if (r < worst.v) { worst.v = r; worst.label = `${name}: ${label}`; }
    if (r < MIN_TEXT) fails.push(`контраст ${name} / ${label} = ${r.toFixed(2)}:1 < ${MIN_TEXT}`);
    checks++;
    if (r < 5) perTheme.push(`${name} ${label} ${r.toFixed(2)}`);
  }
}
notes.push(`  min контраст по всем 5 палитрам и ${pairs.length} парам: ${worst.v.toFixed(2)}:1 (${worst.label})`);
ok(true, 'пары контраста посчитаны', `${palettes.length} x ${pairs.length} = ${palettes.length * pairs.length}`);

const pills = [['.msg-tg', '#141A21', '#2AABEE'], ['.msg-wa', '#112418', '#25D366'], ['.msg-vk', '#FFFFFF', '#0066DB'], ['.msg-max', '#FFFFFF', '#4E44E6'], ['.msg-max', '#FFFFFF', '#7E22CE']];
for (const [cls, fg, bg] of pills) {
  const r = ratio(parseColor(fg), parseColor(bg));
  ok(r >= MIN_TEXT, `кнопка ${cls} (${bg})`, `${r.toFixed(2)}:1`);
}
ok(/\.msg-tg \{ background: #2AABEE; color: #141A21;/.test(PAGE), 'на голубом Telegram тёмный текст');
ok(/\.msg-wa \{ background: #25D366; color: #112418;/.test(PAGE), 'на зелёном WhatsApp тёмный текст');

/* ---------- 9b. инварианты тем и предзагрузок ---------- */
const freshRules = [...PAGE.matchAll(/\.[a-z-]+[^{]*\{[^}]*background:[^;]*var\(--fresh\)[^}]*\}/g)]
  .map((m) => m[0]);
ok(freshRules.length > 0, 'правила на плашке «в сезоне» найдены', `${freshRules.length} правила`);
ok(!freshRules.some((r) => /color:\s*#FF/i.test(r)),
   'цвет текста на плашке «в сезоне» берётся из токена, а не вшит в код',
   freshRules.filter((r) => /color:\s*#FF/i.test(r)).length ? 'найдены жёсткие #FFFFFF' : 'var(--fresh-ink) во всех');
for (const [, body] of palettes) {
  ok(!!body['--fresh-ink'], 'токен --fresh-ink определён', body['--fresh-ink'] || 'нет');
}

const fontPreloads = [...PAGE.matchAll(/<link rel="preload" as="font"[^>]*href="([^"]+)"/g)].map((m) => m[1]);
ok(fontPreloads.length >= 6, 'критичные шрифты предзагружаются', `${fontPreloads.length} файлов`);
const missingPreload = fontPreloads.filter((h) => !existsSync(`${ROOT}/${h}`));
ok(missingPreload.length === 0, 'все предзагруженные файлы лежат в репозитории', missingPreload.join(', ') || fontPreloads.length + ' путей');
const imgPreload = (PAGE.match(/<link rel="preload" as="image"[^>]*href="([^"]+)"/) || [])[1] || '';
ok(imgPreload && existsSync(`${ROOT}/${imgPreload}`), 'предзагружен кадр, который реально в первом экране', imgPreload);
ok(/@media \(pointer: coarse\)[\s\S]{0,900}min-height:\s*44px/.test(PAGE),
   'на пальце контролы растягиваются до 44px');
ok(/fetchpriority="high"/.test(PAGE), 'главному кадру первого экрана поднят приоритет');

/* ---------- 10. ни одного пиктограммного значка в интерфейсе ---------- */
const ALLOWED_MARKS = new Set(['↗', '→', '←', '↓', '↑', '·', '★', '✓', '—', '–', '№', '₽', '«', '»', '−', '✕', '●', '▲', '▼', '•', '⇒']);
const pics = [...new Set([...PAGE.matchAll(/[\u{1F000}-\u{1FAFF}\u{2190}-\u{2BFF}\u{FE0F}\u{1F1E6}-\u{1F1FF}]/gu)].map((m) => m[0]))].filter((c) => !ALLOWED_MARKS.has(c));
ok(pics.length === 0, 'в интерфейсе нет эмодзи и стикеров', pics.join(' ') || `разрешённые знаки: ${[...new Set([...PAGE.matchAll(/[\u{1F000}-\u{1FAFF}\u{2190}-\u{2BFF}]/gu)].map((m) => m[0]))].length}`);

/* ---------- 11. семантика, alt, focus ---------- */
ok((PAGE.match(/<h1[ >]/g) || []).length === 1, 'один h1');
ok((PAGE.match(/<header[ >]/g) || []).length === 1, 'один header');
ok((PAGE.match(/<nav[ >]/g) || []).length === 1, 'один nav');
ok((PAGE.match(/<main[ >]/g) || []).length === 1, 'один main');
const imgs = [...PAGE.matchAll(/<img\b[^>]*>/g)].map((m) => m[0]);
const noAlt = imgs.filter((t) => !/alt=/.test(t));
ok(noAlt.length === 0, 'у всех img есть alt', `${imgs.length} меток, без alt ${noAlt.length}`);
const noWh = imgs.filter((t) => !/width="\d+" height="\d+"/.test(t));
ok(noWh.length === 0, 'у всех img заданы width/height (без сдвигов макета)', `без размеров ${noWh.length}`);
ok(/:focus-visible/.test(PAGE) && !/outline:\s*none\s*[;}]/.test(PAGE), 'кольцо фокуса задано и не глушится');
ok(/prefers-reduced-motion/.test(PAGE), 'режим reduced-motion учтён');
ok(/@media print/.test(PAGE), 'печатная версия описана');
ok(/scrollbar-gutter:\s*stable/.test(PAGE), 'scrollbar-gutter: stable против CLS');

/* ---------- 12. состав релиза ---------- */
const releaseList = (PAGE.match(/const RELEASE_FILES = \[([^\]]+)\]/) || [])[1] || '';
const releaseFiles = [...releaseList.matchAll(/'([^']+)'/g)].map((m) => m[1]);
ok(releaseFiles.includes('index.html'), 'архив включает index.html', `${releaseFiles.length} файлов`);
const missingRelease = releaseFiles.filter((f) => !existsSync(`${ROOT}/${f}`));
ok(missingRelease.length === 0, 'все файлы из архива лежат в репозитории', missingRelease.join(', ') || releaseFiles.join(', '));
const readme = readFileSync(`${ROOT}/README.md`, 'utf8');
const shotRefs = [...new Set([...readme.matchAll(/docs\/screens\/([0-9a-z-]+\.jpg)/g)].map((m) => m[1]))];
const missingShots = shotRefs.filter((f) => !existsSync(`${ROOT}/docs/screens/${f}`));
const staleShots = existsSync(`${ROOT}/docs/screens`)
  ? readdirSync(`${ROOT}/docs/screens`).filter((f) => f.endsWith('.jpg') && !shotRefs.includes(f))
  : [];
ok(shotRefs.length >= 20 && missingShots.length === 0 && staleShots.length === 0,
   'README показывает только те снимки, что лежат в репозитории',
   `${shotRefs.length} ссылок; нет на месте: ${missingShots.slice(0, 4).join(', ') || 'ни одного'}; не упомянуты: ${staleShots.slice(0, 4).join(', ') || 'ни одного'}`);
for (const doc of ['README.md', 'AGENT_DEPLOY.md', 'NEXT_AGENT_PROMPT.md']) {
  const size = readFileSync(`${ROOT}/${doc}`, 'utf8').length;
  ok(size > 2500, `${doc} не заготовка`, `${size} знаков`);
}
ok(!/tools\/build\.py|pillow|quickjs|rcssmin|segno|GSAP|Lenis|Swiper/.test(PAGE), 'в витрине нет следов сборщика и тяжёлых библиотек');
ok(!existsSync(`${ROOT}/tools/build.py`) && !existsSync(`${ROOT}/sw.js`), 'сборщик и service worker удалены из корня');
ok(MANIFEST.icons?.length >= 3 && existsSync(`${ROOT}/${MANIFEST.icons[1].src}`), 'манифест с иконками, файлы на месте', `${MANIFEST.icons?.length || 0} иконок`);
ok(!/js\/app\.js|css\/style\.css/.test(PAGE), 'страница не ссылается на удалённые модули');
ok((PAGE404.match(/assets\//g) || []).length >= 3 && !/css\/style\.css/.test(PAGE404), '404 самодостаточен');

/* ---------- 13. ссылки на мессенджеры ---------- */
const tgLinks = [...new Set([...PAGE.matchAll(/href="(https:\/\/t\.me\/[^"]+)"/g)].map((m) => m[1]))];
ok(tgLinks.length === 1 && tgLinks[0] === 'https://t.me/ssrjkk', 'все мессенджеры ведут в @ssrjkk', tgLinks.join(', '));
ok(/tel:\+79992035645|7 \(999\) 203-56-45/.test(PAGE), 'телефон лавки указан');

/* ---------- итог ---------- */
console.log(`\nГЕЙТ ВИТРИНЫ: проверок ${checks}, провалов ${fails.length}`);
notes.forEach((t) => console.log(t));
if (perTheme.length) { console.log('\nПлотные пары (4.5..5.0):'); perTheme.forEach((p) => console.log('  ' + p)); }
if (fails.length) {
  console.log('\nПРОВАЛЕНО:');
  fails.forEach((f) => console.log('  ✗ ' + f));
  process.exit(1);
}
console.log('\nGREEN');
