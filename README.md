# cheremisin-partnership-lab-data

Public data behind the "Posts and articles" section of [cheremisin.partners](https://cheremisin.partners/en/topics/):
Nikolay Cheremisin's LinkedIn and Telegram posts, blog articles and papers on business partnership,
grouped into 31 topics, each with a one-paragraph summary in three languages and a link to the original.
No full texts of posts and no metrics are stored here.

- `data/` — files the site reads (`home.json`, `section-{ru,ua,en}.json`). The site fetches `main` daily
  and swaps the files only if all four pass validation (`scripts/validate.py`, same rules as in the theme).
- `catalog.json` — the catalogue: id, date, format, language, links per platform, topics, question-titles
  and annotations ×3. `annotations.json`, `descriptions.json`, `manual_topics.json`, `taxonomy.toml` — its sources.
- `scripts/build.py` + `layout.py` — build `data/` from the catalogue; `validate.py` — checks run on every pull request.

**Merge into `main` = publication.** Pull requests are opened by the update pipeline; the owner merges.
