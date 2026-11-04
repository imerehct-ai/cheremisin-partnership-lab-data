#!/usr/bin/env python3
"""Проверка собранных данных раздела (та же логика, что у фетчера в теме, inc/karta-fetch.php).

python3 validate.py <папка с home.json и section-*.json>   — код выхода 1 при любой ошибке.
Запускается GitHub Action на каждом PR/push в репозитории данных и repo_sync.py перед публикацией.
"""
import json, sys
from pathlib import Path

FILES = ["home", "section-ru", "section-ua", "section-en"]
MARKERS = ("01-indexes", "02-notes", "03-competitors", "04-clients-work", "04-projects", "raw/", "impressions", "owner_id", "@gmail", "+34", "+38")

def main(d):
    d = Path(d); errs = []
    for name in FILES:
        p = d / f"{name}.json"
        if not p.exists(): errs.append(f"{name}.json: нет файла"); continue
        raw = p.read_text(encoding="utf-8")
        if len(raw) < 1000: errs.append(f"{name}.json: слишком короткий ({len(raw)} байт)")
        for m in MARKERS:
            if m in raw: errs.append(f"{name}.json: приватный маркер «{m}»")
        try: data = json.loads(raw)
        except Exception as e: errs.append(f"{name}.json: не JSON ({e})"); continue
        if name == "home":
            for k in ("totals", "topics", "posts", "hub", "clusters"):
                if not data.get(k): errs.append(f"home.json: нет {k}")
            if data.get("partial"): errs.append("home.json: partial")
            n = data.get("totals", {}).get("materials", 0)
            if n != len(data.get("posts", [])): errs.append(f"home.json: totals.materials {n} ≠ posts {len(data.get('posts', []))}")
            if n < 300: errs.append(f"home.json: материалов подозрительно мало ({n})")
            if len(data.get("topics", {})) < 20: errs.append("home.json: тем меньше 20")
            for post in data.get("posts", []):
                for u in (post.get("u") if isinstance(post.get("u"), dict) else {"x": post.get("u")}).values():
                    if u and not str(u).startswith("https://"): errs.append(f"home.json: ссылка не https: {u}"); break
        else:
            lang = name[8:]
            if data.get("lang") != lang: errs.append(f"{name}.json: lang ≠ {lang}")
            for k in ("topics", "materials", "hub"):
                if not data.get(k): errs.append(f"{name}.json: нет {k}")
            home = d / "home.json"
            if home.exists():
                try:
                    hn = json.loads(home.read_text(encoding="utf-8")).get("totals", {}).get("materials")
                    if hn and len(data.get("materials", {})) != hn: errs.append(f"{name}.json: материалов {len(data['materials'])} ≠ home {hn}")
                except Exception: pass
    if errs:
        print("ОШИБКИ:"); [print(" -", e) for e in errs]; sys.exit(1)
    print(f"ok: {len(FILES)} файлов в {d}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
