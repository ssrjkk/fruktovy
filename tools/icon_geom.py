#!/usr/bin/env python3
"""Геометрия SVG-спрайта без браузера: пути разворачиваются в полилинии, штрих
растеризуется в маску, по маске считаются связные куски, вес и похожесть силуэтов.
Нужно, чтобы check.py кусался за «обрывки», «два раздельных штриха» и двойняшек.
"""
import math
import re

TOKEN = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)")
NUM = re.compile(r"-?\d*\.?\d+(?:e[-+]?\d+)?", re.I)


def _nums(s):
    return [float(x) for x in NUM.findall(s)]


def _cubic(p0, c1, c2, p1, n):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * p1[0]
        y = mt**3 * p0[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * p1[1]
        out.append((x, y))
    return out


def _quad(p0, c, p1, n):
    out = []
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * p1[0]
        y = mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * p1[1]
        out.append((x, y))
    return out


def _arc(p0, rx, ry, rot, large, sweep, p1, steps=None):
    """Дуга SVG (F.6.5 -> F.6.6) -> список точек, НЕ включая p0.

    Углы снимаются в штрихованной системе координат (относительно центра cx', cy'),
    а не относительно абсолютного центра: иначе дуга улетает за пределы фигуры.
    """
    rx, ry = abs(rx), abs(ry)
    if p0 == p1 or rx < 1e-9 or ry < 1e-9:
        return [] if p0 == p1 else [p1]
    phi = math.radians(rot % 360)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1 = cp * dx + sp * dy
    y1 = -sp * dx + cp * dy
    lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if lam > 1:
        r = math.sqrt(lam)
        rx, ry = rx * r, ry * r
    num = max(rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1, 0.0)
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    co = math.sqrt(num / den) if den else 0.0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1 / ry, -co * ry * x1 / rx

    def ang(ux, uy):
        return math.atan2(uy, ux)

    th1 = ang((x1 - cxp) / rx, (y1 - cyp) / ry)
    th2 = ang((-x1 - cxp) / rx, (-y1 - cyp) / ry)
    delta = th2 - th1
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    cx, cy = cp * cxp - sp * cyp + (p0[0] + p1[0]) / 2, sp * cxp + cp * cyp + (p0[1] + p1[1]) / 2
    n = steps or max(2, int(abs(delta) * max(rx, ry) * 1.6) + 2)
    out = []
    for i in range(1, n + 1):
        t = th1 + delta * i / n
        px, py = rx * math.cos(t), ry * math.sin(t)
        out.append((cp * px - sp * py + cx, sp * px + cp * py + cy))
    return out


NEED = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7}


def path_subpaths(d, step=0.18):
    """d-атрибут -> список субпутей (полилиний в юнитах viewBox).

    Повторяющиеся группы параметров остаются тем же командам (кроме M, за которым
    идут неявные L), S/T отражают предыдущий контрольный точку только после C/S/Q/T.
    """
    subs, cur = [], []
    x = y = sx = sy = 0.0
    ctrl = None
    kind = None

    def chord(a, b):
        return math.hypot(b[0] - a[0], b[1] - a[1])

    for cmd, rest in TOKEN.findall(d or ""):
        vals = _nums(rest)
        rel = cmd.islower()
        C = cmd.upper()
        if C == "Z":
            if cur:
                cur.append((sx, sy))
                subs.append(cur)
            x, y, cur = sx, sy, []
            ctrl = kind = None
            continue
        i = 0
        first = True
        while i < len(vals):
            cc = "L" if (C == "M" and not first) else C
            need = NEED[cc]
            if i + need > len(vals):
                break
            v = vals[i:i + need]
            i += need
            first = False
            p0 = (x, y)
            if cc == "M":
                nx, ny = (x + v[0], y + v[1]) if rel else (v[0], v[1])
                if cur:
                    subs.append(cur)
                cur = [(nx, ny)]
                sx, sy, x, y = nx, ny, nx, ny
            elif cc == "L":
                x, y = (x + v[0], y + v[1]) if rel else (v[0], v[1])
                cur.append((x, y))
            elif cc == "H":
                x = x + v[0] if rel else v[0]
                cur.append((x, y))
            elif cc == "V":
                y = y + v[0] if rel else v[0]
                cur.append((x, y))
            elif cc == "C":
                c1 = (p0[0] + v[0], p0[1] + v[1]) if rel else (v[0], v[1])
                c2 = (p0[0] + v[2], p0[1] + v[3]) if rel else (v[2], v[3])
                p1 = (p0[0] + v[4], p0[1] + v[5]) if rel else (v[4], v[5])
                cur += _cubic(p0, c1, c2, p1, max(2, int(chord(p0, p1) / step) + 1))
                ctrl, x, y = c2, p1[0], p1[1]
            elif cc == "S":
                c1 = ((p0[0] - ctrl[0], p0[1] - ctrl[1]) if ctrl and kind in ("C", "S") else p0)
                c2 = (p0[0] + v[0], p0[1] + v[1]) if rel else (v[0], v[1])
                p1 = (p0[0] + v[2], p0[1] + v[3]) if rel else (v[2], v[3])
                cur += _cubic(p0, c1, c2, p1, max(2, int(chord(p0, p1) / step) + 1))
                ctrl, x, y = c2, p1[0], p1[1]
            elif cc == "Q":
                c1 = (p0[0] + v[0], p0[1] + v[1]) if rel else (v[0], v[1])
                p1 = (p0[0] + v[2], p0[1] + v[3]) if rel else (v[2], v[3])
                cur += _quad(p0, c1, p1, max(2, int(chord(p0, p1) / step) + 1))
                ctrl, x, y = c1, p1[0], p1[1]
            elif cc == "T":
                c1 = ((p0[0] - ctrl[0], p0[1] - ctrl[1]) if ctrl and kind in ("Q", "T") else p0)
                p1 = (p0[0] + v[0], p0[1] + v[1]) if rel else (v[0], v[1])
                cur += _quad(p0, c1, p1, max(2, int(chord(p0, p1) / step) + 1))
                ctrl, x, y = c1, p1[0], p1[1]
            elif cc == "A":
                p1 = (p0[0] + v[5], p0[1] + v[6]) if rel else (v[5], v[6])
                cur += _arc(p0, v[0], v[1], v[2], int(v[3]), int(v[4]), p1)
                x, y = p1[0], p1[1]
            kind = cc
    if cur and len(cur) > 1:
        subs.append(cur)
    return [s for s in subs if len(s) > 1]


def resample(poly, step):
    """Равномерная выборка по длине дуги — нужна для плотной штамповки штриха.

    carry — путь, пройденный от последней выставленной точки до конца текущего
    звена; следующая точка ставится через step-carry вдоль следующего звена.
    """
    if len(poly) < 2:
        return poly[:]
    out = [tuple(poly[0])]
    prev = out[0]
    carry = 0.0
    for nxt in poly[1:]:
        nxt = tuple(nxt)
        seg = math.hypot(nxt[0] - prev[0], nxt[1] - prev[1])
        if seg <= 1e-9:
            continue
        need = step - carry
        while need <= seg:
            t = need / seg
            prev = (prev[0] + (nxt[0] - prev[0]) * t, prev[1] + (nxt[1] - prev[1]) * t)
            out.append(prev)
            seg = math.hypot(nxt[0] - prev[0], nxt[1] - prev[1])
            need = step
        carry = seg
    if out[-1] != poly[-1]:
        out.append(poly[-1])
    return out


def element_polylines(tag, attrs):
    """Один geometric-элемент -> субпути + замкнутость."""
    closed = tag in ("polygon", "rect", "circle", "ellipse")
    if tag == "path":
        subs = path_subpaths(attrs.get("d", ""))
        return subs, any(zd_closed(s) for s in subs)
    if tag == "line":
        return [[(float(attrs["x1"]), float(attrs["y1"])), (float(attrs["x2"]), float(attrs["y2"]))]], False
    if tag == "polyline":
        return [_pairs(attrs.get("points", ""))], False
    if tag == "polygon":
        pts = _pairs(attrs.get("points", ""))
        if pts:
            pts = pts + [pts[0]]
        return [pts], True
    if tag in ("circle", "ellipse"):
        cx, cy = float(attrs.get("cx", 0)), float(attrs.get("cy", 0))
        rx = float(attrs.get("r", attrs.get("rx", 0)))
        ry = float(attrs.get("ry", rx))
        n = max(16, int(2 * math.pi * max(rx, ry) * 3))
        return [[(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]], True
    if tag == "rect":
        x, y = float(attrs.get("x", 0)), float(attrs.get("y", 0))
        w, h = float(attrs.get("width", 0)), float(attrs.get("height", 0))
        rx = float(attrs.get("rx", 0)) or 0
        ry = float(attrs.get("ry", rx)) or rx
        if rx <= 0 or ry <= 0:
            return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]], True
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        pts = []
        arcs = [((x + w - rx, y + ry), rx, ry, -90, 90), ((x + w - rx, y + h - ry), rx, ry, 0, 90),
                ((x + rx, y + h - ry), rx, ry, 90, 90), ((x + rx, y + ry), rx, ry, 180, 90)]
        for centre, arx, ary, a0, sw in arcs:
            for k in range(sw + 1):
                t = math.radians(a0 + k)
                pts.append((centre[0] + arx * math.cos(t), centre[1] + ary * math.sin(t)))
        pts.append(pts[0])
        return [pts], True
    return [], False


def _pairs(s):
    v = NUM.findall(s or "")
    return [(float(v[i]), float(v[i + 1])) for i in range(0, len(v) - 1, 2)]


def zd_closed(sub):
    return len(sub) > 2 and math.hypot(sub[0][0] - sub[-1][0], sub[0][1] - sub[-1][1]) < 0.02


def subpath_len(sub):
    return sum(math.hypot(sub[i + 1][0] - sub[i][0], sub[i + 1][1] - sub[i][1]) for i in range(len(sub) - 1))


SYMS = re.compile(r'<symbol id="([^"]+)"([^>]*)>(.*?)</symbol>', re.S)
ELS = re.compile(r'<(path|line|polyline|polygon|circle|rect|ellipse)\b([^>]*?)/?>', re.S)
ATTR = re.compile(r'([A-Za-z-]+)\s*=\s*"([^"]*)"')


def load_symbols(html):
    out = {}
    for sid, sattrs, body in SYMS.findall(html):
        box = (24.0, 24.0)
        vb = re.search(r'viewBox="([^"]+)"', sattrs + body)
        if vb:
            n = [float(x) for x in NUM.findall(vb.group(1))]
            if len(n) >= 4:
                box = (n[2], n[3])
        els = []
        for tag, raw in ELS.findall(body):
            a = dict(ATTR.findall(raw))
            els.append((tag, a))
        out[sid] = {"box": box, "els": els}
    return out


def raster(els, size=32, span=24.0, sw_user=1.9, ink=0.5):
    """Маска штрихов (и заливок замкнутых форм с fill!=none) в сетке size x size."""
    grid = [[0.0] * size for _ in range(size)]
    k = size / span
    for tag, a in els:
        subs, _ = element_polylines(tag, a)
        fill = a.get("fill", "none")
        stroked = a.get("stroke", "") != "none"
        sw = float(a.get("stroke-width", sw_user) or sw_user)
        rad = max(0.3, sw * k / 2.0)
        for sub in subs:
            if stroked:
                for (x, y) in resample(sub, 0.4 / k):
                    disc(grid, x * k, y * k, rad, size)
            if fill not in ("none", "", None) and zd_closed(sub):
                fill_poly(grid, sub, size, k)
    return [[1 if v >= ink else 0 for v in row] for row in grid]


def disc(grid, px, py, rad, size):
    r2 = rad * rad
    i0, i1 = max(0, int(math.floor(px - rad))), min(size - 1, int(math.ceil(px + rad)))
    j0, j1 = max(0, int(math.floor(py - rad))), min(size - 1, int(math.ceil(py + rad)))
    for j in range(j0, j1 + 1):
        row = grid[j]
        dy = j + 0.5 - py
        for i in range(i0, i1 + 1):
            dx = i + 0.5 - px
            d2 = dx * dx + dy * dy
            if d2 <= r2:
                d = math.sqrt(d2)
                cov = 1.0 if d <= rad - 0.6 else max(0.25, (rad + 0.45 - d))
                if cov > row[i]:
                    row[i] = min(1.0, cov)


def fill_poly(grid, poly, size, k):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    y0, y1 = max(0, int(min(ys) * k)), min(size - 1, int(max(ys) * k))
    for j in range(y0, y1 + 1):
        yy = (j + 0.5) / k
        xsec = []
        for i in range(len(poly)):
            ax, ay = poly[i]
            bx, by = poly[(i + 1) % len(poly)]
            if (ay <= yy < by) or (by <= yy < ay):
                xsec.append(ax + (yy - ay) * (bx - ax) / (by - ay))
        xsec.sort()
        for a, b in zip(xsec[0::2], xsec[1::2]):
            for i in range(max(0, int(a * k)), min(size - 1, int(b * k)) + 1):
                grid[j][i] = 1.0


def components(grid):
    size = len(grid)
    seen = [[False] * size for _ in range(size)]
    out = []
    for j in range(size):
        for i in range(size):
            if not grid[j][i] or seen[j][i]:
                continue
            stack, cells = [(i, j)], []
            seen[j][i] = True
            while stack:
                x, y = stack.pop()
                cells.append((x, y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < size and 0 <= ny < size and grid[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            out.append(cells)
    return out


def crop_norm(grid, n=24, pad=0):
    """Обрезаем по маске, сохраняем пропорции, вписываем в n x n."""
    cells = [(i, j) for j, row in enumerate(grid) for i, v in enumerate(row) if v]
    if not cells:
        return [[0] * n for _ in range(n)]
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    s = (n - pad) / max(w, h)
    out = [[0] * n for _ in range(n)]
    ow, oh = max(1, round(w * s)), max(1, round(h * s))
    ox, oy = (n - ow) // 2, (n - oh) // 2
    for j in range(oh):
        for i in range(ow):
            sx = x0 + i / s
            sy = y0 + j / s
            a00 = grid[int(sy)][int(sx)] if int(sy) < len(grid) and int(sx) < len(grid[0]) else 0
            a10 = grid[int(sy)][min(int(sx) + 1, len(grid[0]) - 1)]
            a01 = grid[min(int(sy) + 1, len(grid) - 1)][int(sx)]
            a11 = grid[min(int(sy) + 1, len(grid) - 1)][min(int(sx) + 1, len(grid[0]) - 1)]
            fx, fy = sx - int(sx), sy - int(sy)
            v = a00 * (1 - fx) * (1 - fy) + a10 * fx * (1 - fy) + a01 * (1 - fx) * fy + a11 * fx * fy
            out[oy + j][ox + i] = 1 if v >= 0.5 else 0
    return out


def dihedral(grid):
    n = len(grid)
    out = []
    cur = grid

    def rot(g):
        return [[g[n - 1 - x][y] for x in range(n)] for y in range(n)]

    def mir(g):
        return [row[::-1] for row in g]

    for _ in range(4):
        out.append(cur)
        out.append(mir(cur))
        cur = rot(cur)
    return out


def iou(a, b):
    inter = union = 0
    for j in range(len(a)):
        for i in range(len(a)):
            if a[j][i] or b[j][i]:
                union += 1
                if a[j][i] and b[j][i]:
                    inter += 1
    return inter / union if union else 0.0


def best_iou(a, b):
    rb = dihedral(b)
    return max(iou(x, y) for x in [a] for y in rb)


def endpoint_gaps(subs, limit=1.2):
    """Концы разных штрихов, которые «почти соприкасаются»: именно то, что в
    маленьких иконках читается как обрывок линии."""
    tips = []
    for s in subs:
        if len(s) > 1 and not zd_closed(s):
            tips.append(s[0])
            tips.append(s[-1])
    gaps = []
    for i in range(len(tips)):
        for j in range(i + 1, len(tips)):
            d = math.hypot(tips[i][0] - tips[j][0], tips[i][1] - tips[j][1])
            if 0.02 < d <= limit:
                gaps.append(round(d, 2))
    return sorted(gaps)


def raster_float(els, size, span, sw_user):
    """Сетка плотности чернил 0..1 — та же модель, что в замере живых пикселей
    Chrome (coverage вместо бинарного диска), поэтому пороги переносимы."""
    grid = [[0.0] * size for _ in range(size)]
    k = size / span
    for tag, a in els:
        subs, _ = element_polylines(tag, a)
        r = max(0.25, float(a.get("stroke-width", sw_user) or sw_user) * k / 2.0)
        stroked = a.get("stroke", "") != "none"
        fill = a.get("fill", "none")
        for sub in subs:
            if stroked:
                for (x, y) in resample(sub, 0.3 / k):
                    px, py = x * k, y * k
                    i0, i1 = max(0, int(math.floor(px - r - 1))), min(size - 1, int(math.ceil(px + r + 1)))
                    j0, j1 = max(0, int(math.floor(py - r - 1))), min(size - 1, int(math.ceil(py + r + 1)))
                    for j in range(j0, j1 + 1):
                        row = grid[j]
                        dy = j + 0.5 - py
                        for i in range(i0, i1 + 1):
                            cov = max(0.0, min(1.0, r + 0.5 - math.hypot(i + 0.5 - px, dy)))
                            if cov > row[i]:
                                row[i] = cov
            if fill not in ("none", "", None) and zd_closed(sub):
                fill_poly(grid, sub, size, k)
    return grid, k


def sample_alpha(grid, k, x, y):
    """Билинейная плотность чернил в точке пользовательских координат."""
    size = len(grid)
    X, Y = x * k, y * k
    x0, y0 = min(int(X), size - 1), min(int(Y), size - 1)
    fx, fy = X - int(X), Y - int(Y)

    def a(ix, iy):
        if ix < 0 or iy < 0 or ix >= size or iy >= size:
            return 0.0
        return grid[iy][ix]

    return (a(x0, y0) * (1 - fx) * (1 - fy) + a(x0 + 1, y0) * fx * (1 - fy)
            + a(x0, y0 + 1) * (1 - fx) * fy + a(x0 + 1, y0 + 1) * fx * fy)


def glyph_metrics(els, span, sw_user, sizes=(16, 20), gap_limit=0.9):
    """Один проход по глифу: всё, чем мы меряли спрайт в Chrome, но без браузера."""
    subs = []
    for tag, a in els:
        subs += element_polylines(tag, a)[0]
    out = {
        "nsub": len(subs),
        "minlen": round(min([subpath_len(s) for s in subs] or [0.0]), 2),
        "gaps": [round(g, 2) for g in endpoint_gaps(subs, limit=gap_limit)],
        "filled": any(a.get("fill", "none") not in ("none", "", None) for tag, a in els),
        "stroke_only": all(a.get("stroke") == "none" for tag, a in els),
    }
    for size in sizes:
        grid, k = raster_float(els, size, span, sw_user)
        hard = [[1 if v >= 0.5 else 0 for v in row] for row in grid]
        out["c%d" % size] = sorted(len(c) for c in components(hard))
        out["ink%d" % size] = round(sum(sum(r) for r in hard) / float(size * size), 3)
        worst = 1.0
        for tag, a in els:
            if a.get("stroke") == "none":
                continue
            for sub in element_polylines(tag, a)[0]:
                pts = resample(sub, 0.3 / k)
                if len(pts) < 2:
                    worst = min(worst, 0.0)
                    continue
                worst = min(worst, sum(sample_alpha(grid, k, x, y) for x, y in pts) / len(pts))
        out["alpha%d" % size] = round(worst, 3)
    return out

