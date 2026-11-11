"""Раскладка видов «Карты тем»: treemap, оттенки кластеров, граф связей.

Чистая геометрия без чтения файлов; используется karta/build.py. Вынесено из
proto_build.py (S14) без изменения алгоритмов — раскладка прототипа принята владельцем.
"""
import math
import random
import re
from collections import defaultdict
from itertools import combinations, permutations

LANGS = ("ru", "ua", "en")

# Опорный размер раскладки — ширина контейнера темы на десктопе: 77.5rem = 1240px
# при корневом кегле 16px. Тема масштабирует корневой кегль от ширины окна
# (html{font-size:1.11vw…}), а блок задаёт все размеры в rem, поэтому пропорции
# «текст ↔ плитка» одинаковы на любом десктопе. Все px здесь — rem × 16.
REF_W = 1240
TREEMAP_H = 560
# Портретная раскладка карты для телефона: ширина области вида при 375px = 344px
# (корневой кегль там 15.4px, но пропорции те же). Высота — чтобы маленьким темам
# хватило места под число.
MOBILE_W = 344
MOBILE_H = 1100
CLUSTER_HEAD = 0           # названия кластеров не рисуются на карте (правка владельца 29.10)
TILE_PAD = 8               # внутренний отступ плитки, px
GRAPH_H = 560


# ---------- treemap (бинарное деление) ----------
# Сравнивали со squarified (Bruls et al.) на этих данных: бинарное деление даёт
# меньше узких полосок, и подписи влезают у большего числа тем.

def split_rects(values, x, y, w, h):
    """values — площади по убыванию. Делим список пополам по сумме, рекурсивно."""
    if len(values) == 1:
        return [(x, y, w, h)]
    total, acc, best = sum(values), 0, None
    for i in range(1, len(values)):
        acc += values[i - 1]
        if best is None or abs(acc - total / 2) < abs(best[1] - total / 2):
            best = (i, acc)
    i, acc = best
    f = acc / total
    if w >= h:
        return (split_rects(values[:i], x, y, w * f, h)
                + split_rects(values[i:], x + w * f, y, w * (1 - f), h))
    return (split_rects(values[:i], x, y, w, h * f)
            + split_rects(values[i:], x, y + h * f, w, h * (1 - f)))


def wrap(text, max_chars):
    """Жадный перенос по словам и после дефиса (как в браузере);
    None, если кусок слова длиннее строки."""
    lines, cur = [], ""
    for word in text.split():
        for i, part in enumerate(re.findall(r"[^-]+-|[^-]+$|-", word)):
            if len(part) > max_chars:
                return None
            glue = " " if i == 0 and cur else ""
            if len(cur + glue + part) <= max_chars:
                cur += glue + part
            else:
                lines.append(cur)
                cur = part
    if cur:
        lines.append(cur)
    return lines


# Моноширинный IBM Plex Mono: ширина знака 0.6 em. Берём с запасом (без учёта
# отрицательного letter-spacing темы), чтобы подпись точно влезла.
LABEL_SIZES = (("l", 14, 18), ("m", 12, 15), ("s", 11, 13))   # класс, кегль, интерлиньяж


def fit_label(name, w, h, count_h):
    """Самый крупный кегль, при котором название целиком влезает в плитку."""
    for cls, size, lh in LABEL_SIZES:
        max_chars = int((w - 2 * TILE_PAD) / (size * 0.6))
        if max_chars < 4:
            continue
        lines = wrap(name, max_chars)
        if lines and len(lines) * lh + 4 + count_h <= h - 2 * TILE_PAD:
            return cls
    return "x"     # не влезает: видно только число, название — по наведению


def treemap_layout(taxonomy, topic_count, ref_w=REF_W, ref_h=TREEMAP_H):
    clusters = []
    for c in taxonomy["cluster"]:
        total = sum(topic_count[t["id"]] for t in c["topic"])
        clusters.append((c, total))
    clusters.sort(key=lambda ct: -ct[1])
    grand = sum(t for _, t in clusters)
    area = ref_w * ref_h
    crects = split_rects([t / grand * area for _, t in clusters], 0, 0, ref_w, ref_h)

    out = {}
    for (c, total), (cx, cy, cw, ch) in zip(clusters, crects):
        inner_h = ch - CLUSTER_HEAD
        topics = sorted(c["topic"], key=lambda t: -topic_count[t["id"]])
        vals = [topic_count[t["id"]] / total * cw * inner_h for t in topics]
        trects = split_rects(vals, 0, 0, cw, inner_h)
        tiles = []
        for t, (tx, ty, tw, th) in zip(topics, trects):
            big = tw >= 130 and th >= 110
            count_h = 34 if big else 20
            tiles.append({
                "id": t["id"],
                # в процентах от области плиток кластера
                "box": [round(tx / cw * 100, 3), round(ty / inner_h * 100, 3),
                        round(tw / cw * 100, 3), round(th / inner_h * 100, 3)],
                "num": "l" if big else "s",
                "fit": {l: fit_label(t["name"][l], tw, th, count_h) for l in LANGS},
            })
        out[c["id"]] = {
            "box": [round(cx / ref_w * 100, 3), round(cy / ref_h * 100, 3),
                    round(cw / ref_w * 100, 3), round(ch / ref_h * 100, 3)],
            "tiles": tiles,
        }
    order = [c["id"] for c, _ in clusters]
    return order, out


# ---------- оттенки кластеров ----------
# Ступени серого (CSS: .karta-shade-1 светлый … -N тёмный, N = число кластеров).
# Серые плохо различимы между соседними ступенями, поэтому раздаём их так, чтобы
# кластеры, соприкасающиеся на карте, и соседние полосы waffle (порядок таксономии)
# отличались как можно сильнее: перебор всех перестановок (7! = 5040).

def assign_shades(taxonomy, tree):
    ids = [c["id"] for c in taxonomy["cluster"]]

    def touch(a, b):
        ax, ay, aw, ah = tree[a]["box"]
        bx, by, bw, bh = tree[b]["box"]
        xo = min(ax + aw, bx + bw) - max(ax, bx)
        yo = min(ay + ah, by + bh) - max(ay, by)
        return (abs(xo) < 0.01 and yo > 0.01) or (abs(yo) < 0.01 and xo > 0.01)

    pairs = {(a, b) for a, b in combinations(ids, 2) if touch(a, b)}
    pairs |= set(zip(ids, ids[1:]))
    best, best_key = None, None
    for perm in permutations(range(1, len(ids) + 1)):
        shade = dict(zip(ids, perm))
        key = sorted(abs(shade[a] - shade[b]) for a, b in pairs)
        if best_key is None or key > best_key:
            best, best_key = shade, key
    return best, best_key[0]


# ---------- граф совместной встречаемости ----------

GRAPH_LABEL = (12, 15, 20)  # кегль, интерлиньяж, знаков в строке


def label_box(names):
    size, lh, max_chars = GRAPH_LABEL
    w = h = 0
    for name in names:
        lines = wrap(name, max_chars) or [name]
        w = max(w, max(len(s) for s in lines) * size * 0.6 + 10)
        h = max(h, len(lines) * lh + 4)
    return w, h


def graph_layout(taxonomy, topic_count, edges):
    rnd = random.Random(14)
    topics = [(c["id"], t) for c in taxonomy["cluster"] for t in c["topic"]]
    cmax = max(topic_count.values())
    nodes = {}
    cluster_ids = [c["id"] for c in taxonomy["cluster"]]
    for i, (cid, t) in enumerate(topics):
        k = cluster_ids.index(cid)
        ang = 2 * math.pi * k / len(cluster_ids)
        r = 4 + 9 * math.sqrt(topic_count[t["id"]] / cmax)
        lw, lh = label_box([t["name"][l] for l in LANGS])
        nodes[t["id"]] = {
            "cluster": cid, "r": r,
            "w": max(lw, 2 * r), "h": 2 * r + 2 + lh,
            "x": REF_W / 2 + 300 * math.cos(ang) + rnd.uniform(-60, 60),
            "y": GRAPH_H / 2 + 200 * math.sin(ang) + rnd.uniform(-50, 50),
        }
    ids = list(nodes)
    wmax = max(edges.values())

    def bbox(n):   # точка — центр кружка, подпись под ним
        return (n["x"] - n["w"] / 2, n["y"] - n["r"], n["x"] + n["w"] / 2, n["y"] - n["r"] + n["h"])

    for step in range(3000):
        cool = 1 - step / 3000
        fx = {i: 0.0 for i in ids}
        fy = {i: 0.0 for i in ids}
        for a, b in combinations(ids, 2):
            dx = nodes[a]["x"] - nodes[b]["x"]
            dy = nodes[a]["y"] - nodes[b]["y"]
            d2 = dx * dx + dy * dy + 0.01
            f = 9000 / d2
            d = math.sqrt(d2)
            fx[a] += f * dx / d; fy[a] += f * dy / d
            fx[b] -= f * dx / d; fy[b] -= f * dy / d
        for (a, b), w in edges.items():
            dx = nodes[b]["x"] - nodes[a]["x"]
            dy = nodes[b]["y"] - nodes[a]["y"]
            d = math.hypot(dx, dy) + 0.01
            f = 0.004 * (w / wmax + 0.15) * (d - 120)
            fx[a] += f * dx; fy[a] += f * dy
            fx[b] -= f * dx; fy[b] -= f * dy
        # мягкое притяжение к своему кластеру и к центру
        cent = defaultdict(lambda: [0.0, 0.0, 0])
        for i in ids:
            c = cent[nodes[i]["cluster"]]
            c[0] += nodes[i]["x"]; c[1] += nodes[i]["y"]; c[2] += 1
        for i in ids:
            c = cent[nodes[i]["cluster"]]
            fx[i] += 0.02 * (c[0] / c[2] - nodes[i]["x"]) + 0.01 * (REF_W / 2 - nodes[i]["x"])
            fy[i] += 0.02 * (c[1] / c[2] - nodes[i]["y"]) + 0.015 * (GRAPH_H / 2 - nodes[i]["y"])
        for i in ids:
            step_len = math.hypot(fx[i], fy[i])
            lim = 12 * cool + 0.5
            if step_len > lim:
                fx[i] *= lim / step_len; fy[i] *= lim / step_len
            nodes[i]["x"] += fx[i]; nodes[i]["y"] += fy[i]
        # расталкиваем пересекающиеся подписи (с зазором 8px)
        for _ in range(3):
            for a, b in combinations(ids, 2):
                ax0, ay0, ax1, ay1 = bbox(nodes[a])
                bx0, by0, bx1, by1 = bbox(nodes[b])
                ox = min(ax1, bx1) - max(ax0, bx0) + 8
                oy = min(ay1, by1) - max(ay0, by0) + 8
                if ox > 0 and oy > 0:
                    if ox < oy:
                        s = 1 if nodes[a]["x"] < nodes[b]["x"] else -1
                        nodes[a]["x"] -= s * ox / 2; nodes[b]["x"] += s * ox / 2
                    else:
                        s = 1 if nodes[a]["y"] < nodes[b]["y"] else -1
                        nodes[a]["y"] -= s * oy / 2; nodes[b]["y"] += s * oy / 2
        for i in ids:   # не выходим за поле
            n = nodes[i]
            n["x"] = min(max(n["x"], n["w"] / 2 + 2), REF_W - n["w"] / 2 - 2)
            n["y"] = min(max(n["y"], n["r"] + 2), GRAPH_H - (n["h"] - n["r"]) - 2)

    # Дожимаем наложения подписей, оставшиеся после охлаждения сил (11.11.2026: новые связи тем дали 3 наложения).
    # Двигаются только пересекающиеся пары, раскладка в остальном не меняется.
    # Пара, которая не расходится по короткой оси (упирается в край поля), со второй попытки идёт по другой оси.
    stuck = set()
    for _ in range(400):
        moved, now = False, set()
        for a, b in combinations(ids, 2):
            ax0, ay0, ax1, ay1 = bbox(nodes[a])
            bx0, by0, bx1, by1 = bbox(nodes[b])
            ox = min(ax1, bx1) - max(ax0, bx0) + 8
            oy = min(ay1, by1) - max(ay0, by0) + 8
            if ox > 0 and oy > 0:
                moved = True; now.add((a, b))
                if (ox < oy) != ((a, b) in stuck):
                    s = 1 if nodes[a]["x"] < nodes[b]["x"] else -1
                    nodes[a]["x"] -= s * ox / 2; nodes[b]["x"] += s * ox / 2
                else:
                    s = 1 if nodes[a]["y"] < nodes[b]["y"] else -1
                    nodes[a]["y"] -= s * oy / 2; nodes[b]["y"] += s * oy / 2
        for i in ids:
            n = nodes[i]
            n["x"] = min(max(n["x"], n["w"] / 2 + 2), REF_W - n["w"] / 2 - 2)
            n["y"] = min(max(n["y"], n["r"] + 2), GRAPH_H - (n["h"] - n["r"]) - 2)
        stuck = now
        if not moved:
            break

    # Растягиваем раскладку на всё поле: силы собирают граф в комок посередине.
    # Коэффициент ≥ 1, поэтому зазоры между подписями только растут.
    for axis, size, lo, hi in (("x", REF_W, lambda n: n["w"] / 2, lambda n: n["w"] / 2),
                               ("y", GRAPH_H, lambda n: n["r"], lambda n: n["h"] - n["r"])):
        first = min(ids, key=lambda i: nodes[i][axis] - lo(nodes[i]))
        last = max(ids, key=lambda i: nodes[i][axis] + hi(nodes[i]))
        a0 = nodes[first][axis]
        span = nodes[last][axis] - a0
        k = max(1.0, (size - 4 - lo(nodes[first]) - hi(nodes[last]) - 4) / span)
        for i in ids:
            nodes[i][axis] = 2 + lo(nodes[first]) + (nodes[i][axis] - a0) * k

    overlaps = 0
    for a, b in combinations(ids, 2):
        ax0, ay0, ax1, ay1 = bbox(nodes[a])
        bx0, by0, bx1, by1 = bbox(nodes[b])
        if min(ax1, bx1) > max(ax0, bx0) and min(ay1, by1) > max(ay0, by0):
            overlaps += 1
    return {i: {"x": round(n["x"], 1), "y": round(n["y"], 1), "r": round(n["r"], 1)}
            for i, n in nodes.items()}, overlaps
