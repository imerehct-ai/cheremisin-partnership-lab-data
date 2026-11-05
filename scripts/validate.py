#!/usr/bin/env python3
"""Проверка собранных данных раздела «Посты и статьи» — зеркало inc/karta-fetch.php в теме.

python3 validate.py <папка с home.json и section-*.json> [--rules rules.json]   — код выхода 1 при ошибке.

Правила — один файл на всех: wp-content/themes/cheremisin-theme/karta/rules.json (в репозитории
данных — его копия scripts/rules.json, обновляет repo_sync.py). Проверяется то же, что проверяет
сайт перед записью: размер, приватные маркеры и телефоны, структура и типы ключей, ссылки только
https на белый список площадок, целостность (темы постов/рёбер/плиток существуют, id материалов
в section = id постов в home, одинаковый generated у всех четырёх). Относительные проверки
«не меньше 70 % от текущих» есть только на сайте — у сборки нет «текущих» данных.
"""
import argparse, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent


def load_rules(path=None):
    cands = [Path(path)] if path else [HERE / "rules.json", HERE.parent / "wp-content/themes/cheremisin-theme/karta/rules.json"]
    for c in cands:
        if c.exists():
            return json.loads(c.read_text(encoding="utf-8"))
    sys.exit(f"нет rules.json (искал: {', '.join(map(str, cands))})")


def host_ok(url, hosts):
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    if p.scheme != "https" or not p.netloc:
        return False
    h = p.netloc.lower()
    return any(h == a or h.endswith("." + a) for a in hosts)


def urls_of(value):
    if isinstance(value, str):
        return [value]
    out = []
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        for v in value:
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list) and len(v) > 1 and isinstance(v[1], str):
                out.append(v[1])
            elif isinstance(v, (list, dict)):
                out += urls_of(v)
    return out


def check_file(name, raw, r):
    """Возвращает (data, errors)."""
    errs = []
    if len(raw) < r["min_bytes"]:
        errs.append(f"{name}.json: слишком короткий ({len(raw)} байт)")
    for m in r["markers"]:
        if m and m in raw:
            errs.append(f"{name}.json: приватный маркер «{m}»")
    if r.get("phone_regex") and re.search(r["phone_regex"], raw):
        errs.append(f"{name}.json: похоже на номер телефона")
    try:
        data = json.loads(raw)
    except Exception as e:
        return None, errs + [f"{name}.json: не JSON ({e})"]
    if not isinstance(data, dict):
        return None, errs + [f"{name}.json: не объект"]
    hosts = r["hosts"]
    langs = r["langs"]
    if name == "home":
        for k in r["home_keys"]:
            if not data.get(k):
                errs.append(f"home.json: нет {k}")
        if errs:
            return data, errs
        if data.get("partial"):
            errs.append("home.json: partial")
        t = data["totals"]
        if not isinstance(t, dict) or "materials" not in t or not isinstance(data["topics"], dict) or not isinstance(data["posts"], list) \
                or not isinstance(data["hub"], dict) or not isinstance(data["clusters"], list) or not isinstance(data["edges"], list) \
                or not isinstance(data["graph"], dict) or not isinstance(data["order"], list):
            return data, errs + ["home.json: неправильные типы ключей"]
        g = data["graph"]
        if not (isinstance(g.get("w"), (int, float)) and g["w"] > 0 and isinstance(g.get("h"), (int, float)) and g["h"] > 0):
            errs.append("home.json: graph.w/h")
        if not (isinstance(t.get("years"), list) and len(t["years"]) == 2):
            errs.append("home.json: totals.years")
        for lang in langs:
            if not isinstance(data["hub"].get(lang), str) or not data["hub"][lang]:
                errs.append(f"home.json: hub.{lang}")
        n = t["materials"]
        if n != len(data["posts"]):
            errs.append(f"home.json: totals.materials {n} ≠ posts {len(data['posts'])}")
        if n < r["min_materials"]:
            errs.append(f"home.json: материалов подозрительно мало ({n})")
        if len(data["topics"]) < r["min_topics"]:
            errs.append(f"home.json: тем меньше {r['min_topics']}")
        for tid, topic in data["topics"].items():
            if not isinstance(topic, dict) or not isinstance(topic.get("slug"), dict) or not isinstance(topic.get("name"), dict) \
                    or "cluster" not in topic or not all(k in (topic.get("node") or {}) for k in ("x", "y", "r")):
                errs.append(f"home.json: тема {tid} без slug/name/cluster/node")
                continue
            for lang in langs:
                if not topic["slug"].get(lang) or not topic["name"].get(lang):
                    errs.append(f"home.json: тема {tid} без slug/name для {lang}")
        seen = set()
        for i, post in enumerate(data["posts"]):
            if not isinstance(post, dict) or not post.get("i") or not post.get("d") or "u" not in post or not isinstance(post.get("t"), list):
                errs.append(f"home.json: пост №{i} без i/d/u/t")
                continue
            if post["i"] in seen:
                errs.append(f"home.json: дубль id {post['i']}")
            seen.add(post["i"])
            for tt in post["t"]:
                if tt not in data["topics"]:
                    errs.append(f"home.json: пост {post['i']} с неизвестной темой {tt}")
            for u in urls_of(post["u"]):
                if not host_ok(u, hosts):
                    errs.append(f"home.json: ссылка не из белого списка: {u}")
        for e in data["edges"]:
            if not isinstance(e, dict) or e.get("a") not in data["topics"] or e.get("b") not in data["topics"] or not isinstance(e.get("w"), (int, float)):
                errs.append("home.json: ребро графа на неизвестную тему или без веса")
        cluster_ids = []
        for c in data["clusters"]:
            if not isinstance(c, dict) or not c.get("id") or not isinstance(c.get("tiles"), list):
                errs.append("home.json: кластер без id/tiles")
                continue
            cluster_ids.append(c["id"])
            for tile in c["tiles"]:
                if not isinstance(tile, dict) or tile.get("id") not in data["topics"]:
                    errs.append(f"home.json: плитка кластера {c['id']} на неизвестную тему")
        for cid in data["order"]:
            if cid not in cluster_ids:
                errs.append(f"home.json: order содержит неизвестный кластер {cid}")
    else:
        lang = name[8:]
        for k in r["section_keys"]:
            if not data.get(k):
                errs.append(f"{name}.json: нет {k}")
        if errs:
            return data, errs
        if data["lang"] != lang:
            errs.append(f"{name}.json: lang ≠ {lang}")
        if not isinstance(data["topics"], dict) or not isinstance(data["materials"], dict) or not isinstance(data["hub"], dict):
            return data, errs + [f"{name}.json: неправильные типы ключей"]
        for mid, m in data["materials"].items():
            if not isinstance(m, dict) or not str(m.get("title", "")).strip() or not str(m.get("text", "")).strip() or not m.get("d"):
                errs.append(f"{name}.json: материал {mid} без title/text/d")
                continue
            for u in urls_of(m.get("links", [])):
                if not host_ok(u, hosts):
                    errs.append(f"{name}.json: ссылка не из белого списка: {u}")
        for tid, tp in data["topics"].items():
            if not isinstance(tp, dict) or not tp.get("name") or not tp.get("text"):
                errs.append(f"{name}.json: тема {tid} без name/text")
    return data, errs


def check_set(files):
    """Согласованность четырёх файлов между собой."""
    errs = []
    home = files.get("home")
    if not home:
        return errs
    gen = str(home.get("generated"))
    ids = sorted(p["i"] for p in home["posts"] if isinstance(p, dict) and "i" in p)
    topics = sorted(home["topics"])
    for name, s in files.items():
        if name == "home" or not s:
            continue
        if str(s.get("generated")) != gen:
            errs.append(f"{name}.json: сборка {s.get('generated')}, а home — {gen}")
        if len(s["materials"]) != len(home["posts"]):
            errs.append(f"{name}.json: материалов {len(s['materials'])} ≠ home {len(home['posts'])}")
        if sorted(s["materials"]) != ids:
            errs.append(f"{name}.json: id материалов не совпадают с home.json")
        if sorted(s["topics"]) != topics:
            errs.append(f"{name}.json: набор тем не совпадает с home.json")
    return errs


def validate_dir(d, rules):
    d = Path(d)
    errs, files = [], {}
    for name in rules["files"]:
        p = d / f"{name}.json"
        if not p.exists():
            errs.append(f"{name}.json: нет файла")
            continue
        data, e = check_file(name, p.read_text(encoding="utf-8"), rules)
        errs += e
        files[name] = data if not e else None
    if not errs:
        errs += check_set(files)
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=".")
    ap.add_argument("--rules")
    a = ap.parse_args()
    rules = load_rules(a.rules)
    errs = validate_dir(a.dir, rules)
    if errs:
        print("ОШИБКИ:")
        for e in errs[:50]:
            print(" -", e)
        if len(errs) > 50:
            print(f" … и ещё {len(errs) - 50}")
        sys.exit(1)
    print(f"ok: {len(rules['files'])} файлов в {a.dir}")


if __name__ == "__main__":
    main()
