#!/usr/bin/env python3
"""Юнит-тесты пакета в реальном JS-движке (quickjs).

Тело IIFE из js/app.js вырезается как есть и исполняется с заглушками DOM:
тестируется ровно тот код, который уезжает на сайт, а не его пересказ на Python.
Ганяется та логика, которую браузер сам не проверяет: количества, вес, «пакет по
ссылке» из чужого URL, текст заявки и то, что денег в нём нет.

Запуск: python tools/test_cart.py"""
import json, re
import sys
from pathlib import Path

import quickjs

ROOT = Path(__file__).resolve().parent.parent
data = (ROOT / "js" / "data.js").read_text(encoding="utf-8")
app = (ROOT / "js" / "app.js").read_text(encoding="utf-8")

# тело IIFE: шапка-комментарий и переносы строки не важны, важна форма «(() => { … })();»
m = re.search(r"\(\s*\(\s*\)\s*=>\s*\{(.*)\}\s*\)\s*\(\s*\)\s*;?\s*\Z", app, re.S)
if not m:
    print("FAIL: js/app.js is not a single IIFE — update the extractor"); sys.exit(1)
body = m.group(1).strip()

STUBS = r"""
var mem = {};
var localStorage = {
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(mem, k) ? mem[k] : null; },
  setItem: function (k, v) { mem[k] = String(v); },
  removeItem: function (k) { delete mem[k]; }
};
var nodes = {}, created = 0, opened = [], openArgs = [], commands = [], copiedFrom = null;
function el(id) {
  if (!nodes[id]) {
    nodes[id] = {
      id: id, value: '', textContent: '', innerHTML: '', open: false, href: '', className: '', attrs: {},
      style: { setProperty: function () {}, removeProperty: function () {} },
      dataset: {}, children: [],
      classList: { toggle: function () {}, add: function () {}, remove: function () {}, contains: function () { return false; } },
      appendChild: function (c) { this.children.push(c); return c; },
      querySelector: function () { return el(id + ':q'); },
      querySelectorAll: function () { return []; },
      addEventListener: function () {}, removeEventListener: function () {},
      setAttribute: function (k, v) { this.attrs[k] = v; }, getAttribute: function (k) { return this.attrs[k] || null; },
      getBoundingClientRect: function () { return { top: 0, left: 0, width: 10, height: 10, right: 10, bottom: 10 }; },
      scrollIntoView: function () {}, focus: function () {}, remove: function () {},
      select: function () { copiedFrom = this.value; },
      closest: function () { return null; }, matches: function () { return false; }, click: function () {}
    };
  }
  return nodes[id];
}
var document = {
  readyState: 'loading',
  documentElement: { dataset: { theme: 'market', cards: '3d' }, style: { setProperty: function () {} },
                     setAttribute: function () {}, getAttribute: function () { return null; },
                     classList: { add: function () {}, remove: function () {}, toggle: function () {} } },
  body: { appendChild: function (c) { return c; }, classList: { add: function () {}, remove: function () {} } },
  getElementById: function (id) { return el(id); },
  querySelector: function (s) { return el('sel:' + s); },
  querySelectorAll: function () { return []; },
  createElement: function (t) { return el('new:' + t + ':' + (created++)); },
  execCommand: function (c) { commands.push(c); return c === 'copy'; },
  addEventListener: function () {}, removeEventListener: function () {}
};
var window = {
  open: function (u, tgt, feats) { opened.push(u); openArgs.push([tgt, feats]); return null; },
  matchMedia: function () { return { matches: false, addEventListener: function () {}, addListener: function () {} }; },
  addEventListener: function () {}, removeEventListener: function () {},
  requestAnimationFrame: function () { return 0; }, scrollTo: function () {}
};
var location = { hash: '', origin: 'https://site.test', pathname: '/fruktovy/' };
var navigator = { clipboard: { writeText: function () { return { then: function () {}, catch: function () {} }; } } };
function setTimeout() { return 0; }
function clearTimeout() {}
function setInterval() { return 0; }
function clearInterval() {}
"""

TESTS = r"""
var n = 0, fails = [];
function ok(name, cond) { n++; if (!cond) fails.push(name); }

/* --- каталог: на этих полях держатся и вес, и текст заявки --- */
ok('каталог 25 позиций', PRODUCTS.length === 25);
ok('ids уникальны', new Set(PRODUCTS.map(function (p) { return p.id; })).size === PRODUCTS.length);
ok('цен в данных нет', PRODUCTS.every(function (p) { return p.price === null && p.oldPrice === null; }));
ok('вес задан у всех', PRODUCTS.every(function (p) { return typeof p.weightKg === 'number' && p.weightKg > 0; }));
ok('единицы из заявленных', PRODUCTS.every(function (p) { return ['кг', 'шт', '100 г'].indexOf(p.unit) !== -1; }));
ok('сезон в пределах 1..12', PRODUCTS.every(function (p) {
  return p.season.length > 0 && p.season.every(function (mo) { return mo >= 1 && mo <= 12; });
}));
ok('«часто берут вместе» ссылается на каталог', PRODUCTS.every(function (p) {
  return (p.together || []).every(function (id) { return PRODUCTS.some(function (x) { return x.id === id; }); });
}));
ok('хиты дня существуют', DAILY_HITS.every(function (id) { return PRODUCTS.some(function (p) { return p.id === id; }); }));

/* --- пустой пакет --- */
state.cart = {}; state.promoCode = null; state.wishes = new Set(); state.delivery = 'pickup';
var e0 = cartStats();
ok('пусто: 0 позиций', e0.count === 0 && e0.entries.length === 0);
ok('пусто: 0 кг', e0.kg === 0);

/* --- количества и вес --- */
setCartQty('apple', 1);
ok('одна позиция', cartStats().count === 1);
ok('вес = weightKg * qty', Math.abs(cartStats().kg - byId('apple').weightKg) < 1e-9);
setCartQty('apple', 3);
ok('перезапись количества', state.cart.apple === 3 && cartStats().count === 1);
setCartQty('banana', 2);
ok('вторая позиция', cartStats().count === 2);
ok('суммарный вес', Math.abs(cartStats().kg - (byId('apple').weightKg * 3 + byId('banana').weightKg * 2)) < 1e-9);
setCartQty('walnut', 99);
ok('потолок 30', state.cart.walnut === 30);
setCartQty('walnut', -5);
ok('ноль убирает позицию', !('walnut' in state.cart) && cartStats().count === 2);
setCartQty('apple', 0);
ok('нулевая позиция не считается', cartStats().count === 1 && state.cart.apple === undefined);

/* --- мусор из старого localStorage: ни в пакет, ни в заявку --- */
state.cart = { banana: 2, 'duh-iz-proshlogo': 4, papaya: -1 };
var gs = cartStats();
ok('призраки отсеяны', gs.count === 1 && gs.entries.length === 1 && gs.entries[0][0] === 'banana');
ok('вес без призраков', Math.abs(gs.kg - byId('banana').weightKg * 2) < 1e-9);

/* --- пакет по ссылке из чужого URL --- */
state.cart = {}; location.hash = '#cart=apple:2,duh:9,banana:1,tomato:99';
hydrateCartFromHash();
ok('ссылка дочитала свои', state.cart.apple === 2 && state.cart.banana === 1);
ok('ссылка игнорит чужие и недоступные', !('duh' in state.cart) && !('tomato' in state.cart));
ok('пакет сохранён в localStorage', JSON.parse(mem[KEYS.cart]).apple === 2);

/* --- текст заявки: самовывоз --- */
state.cart = { apple: 2, spices: 3 }; state.promoCode = null;
state.wishes = new Set(['Поспелее на сегодня']); state.delivery = 'pickup';
el('cartNote').value = '  ';
var t1 = buildOrderText('З-1234', { name: 'Аня', phone: '+7 999 000-00-00' });
ok('шапка с номером заявки', t1.indexOf('Заявка З-1234 с сайта') === 0);
ok('строки с единицами', t1.indexOf('1. Яблоки — 2 кг') !== -1 && t1.indexOf('2. Специи на развес — 3 100 г') !== -1);
ok('позиции посчитаны', t1.indexOf('Позиций: 2, примерно ') !== -1);
ok('вес по-русски, через запятую', /примерно ~\d+,\d кг/.test(t1));
ok('самовывоз адресован', t1.indexOf('Заберу сам: Сытнинская, 12') !== -1);
ok('просит цену дня', t1.indexOf('цены сегодняшнего завоза') !== -1);
ok('контакт для ответа', t1.indexOf('Отвечать на: +7 999 000-00-00 (Аня)') !== -1);
ok('пожелание передано', t1.indexOf('Пожелания: Поспелее на сегодня') !== -1);
ok('пустой комментарий не печатается', t1.indexOf('Комментарий') === -1);
ok('без промокода строки нет', t1.indexOf('Промокод') === -1);

/* --- текст заявки: курьер + промокод + комментарий --- */
state.delivery = 'courier'; state.promoCode = 'РЫНОК10';
el('cartNote').value = 'Помойте зелень заранее';
var t2 = buildOrderText(null, { name: 'Аня', phone: 'wa:anya', address: 'Большой пр. П.С., 45', slot: 'Сегодня 14:00–17:00' });
ok('курьерский адрес и слот', t2.indexOf('Курьером: Большой пр. П.С., 45 · время: Сегодня 14:00–17:00') !== -1);
ok('промокод передан текстом', t2.indexOf('Промокод: РЫНОК10') !== -1);
ok('комментарий передан', t2.indexOf('Комментарий: Помойте зелень заранее') !== -1);
ok('без номера — приветствие', t2.indexOf('Здравствуйте! Заявка с сайта') === 0);

/* --- деньги: их в заявке нет ни в каком виде --- */
var allText = [t1, t2, buildOrderText()].join('\n');
ok('в тексте заявки нет рублей', allText.indexOf('₽') === -1);
ok('в тексте заявки нет платёжной лексики', !/оплат|карт|СБП|эквайринг|скидка применена/i.test(allText));
ok('промокод — метка, а не математика', typeof PROMOS['РЫНОК10'].label === 'string' && PROMOS['РЫНОК10'].label.length > 0);
ok('промокод не обещает скидку цифрой', !/\d+\s*%|минус\s*\d|\d+\s*₽/.test(PROMOS['РЫНОК10'].label + PROMOS['ПРИВЕТ'].label));

/* --- отправка: открывается чат магазина, своего бэкенда у сайта нет --- */
state.cart = { apple: 2, spices: 1 }; state.promoCode = null; state.delivery = 'pickup'; state.wishes = new Set();
opened.length = 0; openArgs.length = 0; commands.length = 0; copiedFrom = null;
sendChatOrder();
ok('открыт ровно один чат', opened.length === 1 && openArgs.length === 1);
ok('чат = SHOP.tg из data.js', opened[0] === 'https://t.me/' + SHOP.tg);
ok('в новый таб и с noopener', openArgs[0][0] === '_blank' && /noopener/.test(openArgs[0][1] || ''));
ok('список пакета копируется в буфер', commands.indexOf('copy') !== -1 && /Яблоки/.test(copiedFrom || ''));
ok('пустой пакет не отправляется', (function () {
  state.cart = {}; opened.length = 0; commands.length = 0; sendChatOrder();
  return opened.length === 0 && commands.length === 0;
})());

/* --- тема: применяется только заявленная палитра --- */
applyTheme('night');
ok('тема применилась', document.documentElement.dataset.theme === 'night' && mem[KEYS.theme] === 'night');
applyTheme('vasilok');
ok('неизвестная тема отклонена', document.documentElement.dataset.theme === 'night');
ok('палитры объявлены в THEME_LABELS', Object.keys(THEME_LABELS).length >= 2);
"""

ctx = quickjs.Context()
src = STUBS + "\n" + data + "\n" + body + "\n" + TESTS
try:
    ctx.eval(src)
except BaseException as e:
    print(f"FAIL: JS raised: {str(e)[:400]}")
    sys.exit(1)

n = int(ctx.eval("n"))
bad = [str(x) for x in json.loads(ctx.eval("JSON.stringify(fails)"))]
if bad:
    for f in bad:
        print("FAIL:", f)
    print(f"CART TESTS: {n - len(bad)}/{n} PASS")
    sys.exit(1)
if n < 20:
    print(f"FAIL: only {n} assertions ran (blind)"); sys.exit(1)
print(f"CART TESTS: {n}/{n} PASS")
