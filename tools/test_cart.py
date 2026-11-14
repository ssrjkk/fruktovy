#!/usr/bin/env python3
"""Юнит-тесты корзины в реальном JS-движке (quickjs).
Код корзины вырезается из js/main.js как есть — тестируется тот код, который уезжает на сайт.
Запуск: python tools/test_cart.py"""
import re, sys
from pathlib import Path
import quickjs

ROOT = Path(__file__).resolve().parent.parent
main = (ROOT / "js" / "main.js").read_text(encoding="utf-8")
m = re.search(r"var CART_KEY=[\s\S]*?\}\)\(\);", main)
if not m:
    print("FAIL: cart IIFE not found in js/main.js"); sys.exit(1)
cart_src = m.group(0)

ctx = quickjs.Context()
ctx.eval((ROOT / "js" / "data.js").read_text(encoding="utf-8"))
ctx.eval("""
var mem = {};
function readLS(k, f){ try { var v = mem[k]; return v ? JSON.parse(v) : f; } catch (e) { return f; } }
function writeLS(k, v){ mem[k] = JSON.stringify(v); }
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }
function product(id){ for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === id) return PRODUCTS[i]; return null; }
function money(n){ return n + ' ₽'; }
var dom = { '#pickupWhen': { value: 'сегодня до 18:00' }, '#giftFlag': { checked: true }, '#cartComment': { value: 'поспелее' } };
function $(s){ return dom[s] || null; }
""")
ctx.eval(cart_src)
n = ctx.eval("""
var n = 0;
function ok(name, cond){ n++; if (!cond) throw new Error("FAIL: " + name); }
ok("empty", cart.count() === 0);
cart.add("apple", 2); cart.add("banana"); cart.add("apple");
ok("accumulate", cart.qty("apple") === 3 && cart.count() === 4);
cart.add("apple", 500); ok("cap 99", cart.qty("apple") === 99);
cart.add("apple", -500); ok("floor removes", cart.qty("apple") === 0);
cart.add("apple", 3);
ok("ghost ignored", cart.add("ghost", 1) === 0 && cart.qty("ghost") === 0);
var q = cart.remove("apple"); ok("remove returns qty", q === 3);
cart.restore("apple", q); ok("undo", cart.qty("apple") === 3);
cart.replace({ apple: 2, ghost: 9, banana: 0 }); ok("replace filters", cart.qty("apple") === 2 && cart.qty("ghost") === 0 && cart.qty("banana") === 0);
var t = cart.totals(); ok("null prices", t.unknown === 1 && t.sum === 0);
for (var i = 0; i < PRODUCTS.length; i++) if (PRODUCTS[i].id === "apple") PRODUCTS[i].price = 150;
var t2 = cart.totals(); ok("known sum", t2.sum === 300 && t2.unknown === 0);
var msg = cart.message();
ok("text items", msg.indexOf("Яблоки — 2 кг (300 ₽)") !== -1);
ok("text when", msg.indexOf("Планирую забрать: сегодня до 18:00.") !== -1);
ok("text gift", msg.indexOf("Это подарок") !== -1);
ok("text comment", msg.indexOf("Комментарий: поспелее") !== -1);
ok("text honest", msg.indexOf("Подтвердите, пожалуйста, наличие и цену дня.") !== -1);
ok("text pickup", msg.indexOf("Самовывоз: СПб, Сытнинская, 12.") !== -1);
cart.saveLast(); cart.clear(); ok("clear", cart.count() === 0);
ok("repeat", cart.repeat() && cart.count() === 2);
ok("lines shape", cart.lines().every(function (l) { return l.p && l.qty > 0; }));
ok("bundle valid", BUNDLE.every(function (id) { return PRODUCTS.some(function (p) { return p.id === id; }); }));
ok("fields", PRODUCTS.every(function (p) { return p.photo && p.unit && p.name && p.season; }));
n;
""")
if ctx.eval(cart_src + ";cart.qty('apple')") != 2:
    print("FAIL: persist — new cart instance lost stored items"); sys.exit(1)
n += 1
if n < 20:
    print(f"FAIL: only {n} assertions ran (blind)"); sys.exit(1)
print(f"CART TESTS: {n}/{n} PASS")