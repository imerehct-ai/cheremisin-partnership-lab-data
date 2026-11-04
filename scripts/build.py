#!/usr/bin/env python3
"""Сборка данных раздела «Посты и статьи» для темы сайта (этап S17, без LLM).

Вход (всё в karta/, git проекта):   catalog.json (материалы: даты, ссылки, темы,
заголовки и аннотации ×3), taxonomy.toml (кластеры, темы, слаги), descriptions.json
(описания кластеров и тем ×3). Вики не читается вовсе.

Выход — wp-content/themes/cheremisin-theme/karta/data/:
  home.json        — раскладка видов (карта, граф, грид), счётчики, список материалов
                     без текстов: id, дата, площадка, ссылка на оригинал, темы, вид
                     (post / article / paper). Читается на главной и в разделе.
  section-<l>.json — тексты одного языка: описания кластеров и тем, заголовки и
                     аннотации материалов, все ссылки. Читается только в разделе
                     (и для подсказок к квадратам на главной).

Сборка падает, если: у материала нет публичной ссылки на известную площадку, нет
заголовка или аннотации на одном из языков, тема без материалов, нет перевода или
описания, в текстах e-mail / телефон / @ / # / служебные слова, не сходятся
счётчики, в выходных файлах есть приватные маркеры. Результат детерминирован.

Запуск: python3 karta/build.py [--edge-min 3]
"""
import argparse
import datetime
import json
import re
import sys
import tomllib
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout as L

ROOT = Path(__file__).resolve().parent.parent
K = ROOT / "karta"
OUT_DIR = ROOT / "wp-content/themes/cheremisin-theme/karta/data"
LANGS = L.LANGS

# Площадка → вид материала и порядок выбора «главной» ссылки (оригинала).
# У поста-подводки к статье главная ссылка — сама статья; у поста — LinkedIn, иначе Telegram.
KIND_BY_PLATFORM = (
    ("zenodo", "paper"), ("scientia", "paper"), ("spilnota", "paper"),
    ("blog", "article"), ("linkedin_article", "article"), ("protocol", "article"),
    ("linkedin", "post"), ("telegram", "post"), ("youtube", "post"),
)
ALLOWED_HOSTS = {
    "linkedin": r"(www\.)?linkedin\.com", "linkedin_article": r"(www\.)?linkedin\.com",
    "telegram": r"t\.me", "blog": r"cheremisin\.partners", "zenodo": r"(doi\.org|zenodo\.org)",
    "scientia": r"([a-z]+\.)?scientia\.report", "spilnota": r"(www\.)?spilnota\.net\.ua",
    "protocol": r"(www\.)?protocol\.ua", "youtube": r"((www\.)?youtube\.com|youtu\.be)",
}
PRIVATE_MARKERS = ("01-indexes", "02-notes", "03-competitors", "04-clients-work", "04-projects", "raw/", ".md", "wiki/")
BAD_WORDS = re.compile(r"@|#|impressions|охват|лайк|тизер|конспект|teaser|[\U0001F300-\U0001FAFF☀-➿]", re.I)
CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.\w+|\+?\d[\d ()-]{8,}\d")


def die(msg):
    sys.exit(f"СТОП: {msg}")


def check_text(where, s):
    if not isinstance(s, str) or not s.strip():
        die(f"{where}: пусто")
    m = BAD_WORDS.search(s)
    if m:
        die(f"{where}: запрещённое «{m.group(0)}» в «{s[:60]}…»")
    if CONTACT.search(s):
        die(f"{where}: похоже на e-mail или телефон: «{s[:60]}…»")


def material_links(m):
    """[(площадка, url), …] в порядке важности; telegram_more раскрыт в отдельные telegram."""
    out = []
    for p, _ in KIND_BY_PLATFORM:
        if p in m["links"]:
            out.append((p, m["links"][p]))
            if p == "telegram":
                out += [("telegram", u) for u in m["links"].get("telegram_more", [])]
    unknown = set(m["links"]) - {p for p, _ in KIND_BY_PLATFORM} - {"telegram_more"}
    if unknown:
        die(f"{m['id']}: неизвестная площадка {sorted(unknown)}")
    for p, u in out:
        # blog — словарь {язык: url} (статья на нескольких языках), остальное — строка
        for url in (u.values() if isinstance(u, dict) else [u]):
            host = re.sub(r"^https://([^/]+).*", r"\1", url)
            if not url.startswith("https://") or not re.fullmatch(ALLOWED_HOSTS[p], host):
                die(f"{m['id']}: ссылка не на публичную площадку «{p}»: {url}")
        if isinstance(u, dict) and not any(l in u for l in LANGS):
            die(f"{m['id']}: у статьи блога нет версии ни на одном из языков раздела")
    if not out:
        die(f"{m['id']}: нет ни одной ссылки")
    return out


def link_for(u, lang):
    """Ссылка для языка раздела: своя версия статьи, иначе RU, иначе первая доступная."""
    if not isinstance(u, dict):
        return u
    return u.get(lang) or u.get("ru") or next(iter(u.values()))


def kind_of(m):
    for p, k in KIND_BY_PLATFORM:
        if p in m["links"]:
            return k, p
    die(f"{m['id']}: не определить вид")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge-min", type=int, default=3, help="минимум общих материалов, чтобы рисовать связь")
    args = ap.parse_args()

    taxonomy = tomllib.loads((K / "taxonomy.toml").read_text(encoding="utf-8"))
    catalog = json.loads((K / "catalog.json").read_text(encoding="utf-8"))
    descr = json.loads((K / "descriptions.json").read_text(encoding="utf-8"))

    # --- таксономия и описания: всё ×3, слаги уникальны ---
    topics_tax = {t["id"]: (c, t) for c in taxonomy["cluster"] for t in c["topic"]}
    for c in taxonomy["cluster"]:
        for l in LANGS:
            check_text(f"кластер {c['id']} name.{l}", c["name"].get(l, ""))
            check_text(f"кластер {c['id']} описание.{l}", descr["clusters"].get(c["id"], {}).get(l, ""))
        for t in c["topic"]:
            for l in LANGS:
                check_text(f"тема {t['id']} name.{l}", t["name"].get(l, ""))
                check_text(f"тема {t['id']} описание.{l}", descr["topics"].get(t["id"], {}).get(l, ""))
    extra = set(descr["topics"]) - set(topics_tax)
    if extra:
        die(f"описания тем, которых нет в таксономии: {sorted(extra)}")
    for l in ("ru", "ua"):
        slugs = [t["slug"][l] for _, t in topics_tax.values()]
        if len(slugs) != len(set(slugs)):
            die(f"повтор слага темы ({l})")
    if len(topics_tax) != len(set(topics_tax)):
        die("повтор id темы")
    hub = taxonomy["hub"]["slug"]

    # --- материалы ---
    materials = []
    for m in catalog["materials"]:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["date"]):
            die(f"{m['id']}: дата «{m['date']}»")
        if not m["topics"]:
            die(f"{m['id']}: нет тем")
        for t in m["topics"]:
            if t not in topics_tax:
                die(f"{m['id']}: неизвестная тема {t}")
        for l in LANGS:
            check_text(f"{m['id']} title.{l}", m.get("title", {}).get(l, ""))
            check_text(f"{m['id']} annotation.{l}", m.get("annotation", {}).get(l, ""))
            if not m["title"][l].strip().endswith("?"):
                die(f"{m['id']} title.{l}: заголовок не вопрос")
        links = material_links(m)
        kind, primary = kind_of(m)
        materials.append({**m, "_links": links, "_kind": kind, "_primary": primary})
    materials.sort(key=lambda m: (m["date"], m["id"]), reverse=True)
    ids = [m["id"] for m in materials]
    if len(ids) != len(set(ids)):
        die("повтор id материала")

    # --- счётчики ---
    topic_count = Counter(t for m in materials for t in m["topics"])
    missing = [t for t in topics_tax if not topic_count[t]]
    if missing:
        die(f"темы без материалов: {missing}")
    cluster_of = {t: c["id"] for t, (c, _) in topics_tax.items()}
    cluster_unique = Counter(c for m in materials for c in {cluster_of[t] for t in m["topics"]})
    if sum(topic_count.values()) != sum(len(m["topics"]) for m in materials):
        die("не сходятся счётчики тем")

    pair_count = Counter()
    for m in materials:
        for a, b in combinations(sorted(m["topics"]), 2):
            pair_count[(a, b)] += 1
    edges = {p: w for p, w in pair_count.items() if w >= args.edge_min}
    related = {t: [] for t in topics_tax}
    for (a, b), w in pair_count.items():
        related[a].append([b, w]); related[b].append([a, w])
    for t in related:
        related[t].sort(key=lambda e: (-e[1], e[0]))
        related[t] = related[t][:8]

    # --- раскладка ---
    order, tree = L.treemap_layout(taxonomy, topic_count)
    _, tree_m = L.treemap_layout(taxonomy, topic_count, L.MOBILE_W, L.MOBILE_H)
    for cid, c in tree.items():
        c["box_m"] = tree_m[cid]["box"]
        by_id = {t["id"]: t for t in tree_m[cid]["tiles"]}
        for t in c["tiles"]:
            t["box_m"] = by_id[t["id"]]["box"]
            t["fit_m"] = by_id[t["id"]]["fit"]
    nodes, overlaps = L.graph_layout(taxonomy, topic_count, edges)
    shades, shade_gap = L.assign_shades(taxonomy, tree)

    platforms = Counter(p for m in materials for p, _ in m["_links"])
    years = sorted({m["date"][:4] for m in materials})
    today = datetime.date.today().isoformat()

    home = {
        "generated": today,
        "partial": False,
        "totals": {
            "materials": len(materials),
            "topics": len(topics_tax),
            "clusters": len(taxonomy["cluster"]),
            "platforms": len(platforms),
            "years": [years[0], years[-1]],
            "kinds": dict(Counter(m["_kind"] for m in materials)),
        },
        "hub": hub,
        "order": order,
        "clusters": [{
            "id": c["id"],
            "name": c["name"],
            "count": cluster_unique[c["id"]],
            "shade": shades[c["id"]],
            "box": tree[c["id"]]["box"],
            "box_m": tree[c["id"]]["box_m"],
            "tiles": tree[c["id"]]["tiles"],
        } for c in taxonomy["cluster"]],
        "topics": {t["id"]: {
            "cluster": c["id"],
            "name": t["name"],
            "slug": {**t["slug"], "en": t["id"]},
            "count": topic_count[t["id"]],
            "node": nodes[t["id"]],
            "related": related[t["id"]],
        } for c in taxonomy["cluster"] for t in c["topic"]},
        "edges": [{"a": a, "b": b, "w": w} for (a, b), w in sorted(edges.items(), key=lambda e: (-e[1], e[0]))],
        "graph": {"w": L.REF_W, "h": L.GRAPH_H},
        "treemap": {"w": L.REF_W, "h": L.TREEMAP_H, "head": L.CLUSTER_HEAD},
        # Материалы без текстов: i — id (ключ в section-<l>.json), d — дата, k — вид
        # (post / article / paper), p и u — площадка и ссылка оригинала, t — темы.
        # u — строка или {язык: url} для статей блога на нескольких языках (ES раздел не показывает).
        "posts": [{"i": m["id"], "d": m["date"], "k": m["_kind"], "p": m["_primary"],
                   "u": ({l: u for l, u in dict(m["_links"])[m["_primary"]].items() if l in LANGS}
                         if isinstance(dict(m["_links"])[m["_primary"]], dict) else dict(m["_links"])[m["_primary"]]),
                   "t": m["topics"]} for m in materials],
    }
    sections = {l: {
        "generated": today,
        "lang": l,
        "hub": hub,
        "clusters": {c["id"]: {"name": c["name"][l], "text": descr["clusters"][c["id"]][l]} for c in taxonomy["cluster"]},
        "topics": {t: {"name": topics_tax[t][1]["name"][l], "text": descr["topics"][t][l]} for t in topics_tax},
        # Материалы: заголовок-вопрос и аннотация этого языка, язык оригинала, все ссылки.
        "materials": {m["id"]: {
            "d": m["date"], "k": m["_kind"], "f": m["format"], "l": m["lang"], "t": m["topics"],
            "title": m["title"][l].strip(), "text": m["annotation"][l].strip(),
            "links": [[p, link_for(u, l)] for p, u in m["_links"]],
            # o — оригинальное название научной публикации (для строки «Научные публикации» на главной, S17b)
            **({"o": m["title"]["src"].strip()} if (m["_kind"] == "paper" or m["_primary"] == "protocol") and m["title"].get("src") else {}),
        } for m in materials},
    } for l in LANGS}

    # --- проверки выходных файлов: приватные маркеры ---
    outputs = {"home.json": home, **{f"section-{l}.json": sections[l] for l in LANGS}}
    blobs = {}
    for name, data in outputs.items():
        blob = json.dumps(data, ensure_ascii=False, indent=1)
        for marker in PRIVATE_MARKERS:
            # ссылки блога заканчиваются на слаг, «.md» в них нет; проверяем всё тело файла
            if marker in blob:
                die(f"{name}: найдено «{marker}»")
        blobs[name] = blob + "\n"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, blob in blobs.items():
        (OUT_DIR / name).write_text(blob, encoding="utf-8")

    print(f"материалов: {len(materials)}; виды: {home['totals']['kinds']}; годы {years[0]}–{years[-1]}")
    print(f"площадки (ссылок): {dict(platforms)}")
    print(f"по кластерам: {dict(sorted(cluster_unique.items()))}")
    print(f"оттенки: {shades}, минимальный разрыв у соседей: {shade_gap} ступ.")
    print(f"пары тем: {len(pair_count)}, связей ≥{args.edge_min}: {len(edges)}; веса: {sorted(Counter(pair_count.values()).items())}")
    print(f"граф: пересечений подписей {overlaps}")
    fits = Counter(f for c in tree.values() for t in c["tiles"] for f in t["fit"].values())
    fits_m = Counter(f for c in tree.values() for t in c["tiles"] for f in t["fit_m"].values())
    print(f"подписи плиток десктоп (l/m/s — влезает, x — только число): {dict(fits)}; телефон: {dict(fits_m)}")
    for name, blob in blobs.items():
        print(f"записано: {(OUT_DIR / name).relative_to(ROOT)} ({len(blob.encode()) // 1024} КБ)")


if __name__ == "__main__":
    main()
