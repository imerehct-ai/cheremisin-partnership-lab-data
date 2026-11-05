# cheremisin-partnership-lab-data

Public data behind the "Posts and articles" section of [cheremisin.partners](https://cheremisin.partners/en/topics/):
Nikolay Cheremisin's LinkedIn and Telegram posts, blog articles and papers on business partnership,
grouped into 31 topics, each with a one-paragraph summary in three languages and a link to the original.
No full texts of posts and no metrics are stored here.

- `data/` — the four files the site reads (`home.json`, `section-{ru,ua,en}.json`). The site fetches
  the latest commit of `main` once a day (or on demand from the admin panel), pins the download to that
  commit's SHA so the four files always come from one build, validates them with the same rules as
  `scripts/validate.py` (`scripts/rules.json`), keeps the previous set for rollback and swaps the files
  only if everything passes.
- `catalog.json` — the catalogue: id, date, format, language, links per platform, topics, question-titles
  and annotations ×3. `annotations.json`, `descriptions.json`, `manual_topics.json`, `taxonomy.toml` — its sources.
- `scripts/build.py` + `layout.py` — build `data/` from the catalogue (`python3 scripts/build.py` works
  from the repository root; `--src`/`--out` override the paths). `validate.py` + `rules.json` — the checks
  that run on every push and pull request; the Action also rebuilds `data/` and fails if the result
  differs from what is committed (apart from the build date).

**How data gets published.** The update pipeline pushes a branch `update/<date>` and opens a pull
request; merging it into `main` is the publication, after which the site picks the data up by itself.
Until branch protection is enabled on `main` (owner's GitHub settings: require a pull request and the
"validate data" check), a direct push to `main` is technically possible — the site's own validation is
then the only gate.
