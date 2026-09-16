# AGENTS.md

Pick out interesting papers from a set of polymer / materials-chemistry
journals, on a weekly cadence, and write a ranked Markdown digest.

Owner's field: polymer science & materials chemistry. "Interesting" is defined
by `config/scoring.md` + `config/keywords.yaml` — read both before scoring.

## Layout

```
config/
  feeds.yaml      ~24 journal sources (RSS: Nature/Wiley · Crossref: ACS/RSC/Elsevier)
  keywords.yaml   interest keywords: core / adjacent / exclude
  scoring.md      the rubric + digest selection + the feedback-tuning procedure
  tuning-log.md   dated record of every rubric/keyword change and why
scripts/
  fetch_feeds.py       pull sources -> data/raw/<date>.json, dedupe via data/state/seen.json
  enrich.py            add citation counts (OpenAlex) to a raw file  [optional pass]
  triage.py            keyword pre-filter -> data/raw/<date>.shortlist.json (+ .txt)
  feedback_report.py   join feedback.md ratings to the archived records
  render_site.py       the ONLY renderer: latest digest + latest news -> one page
                       site/<date>.html (+ --embed self-contained, --artifact w/ rating buttons)
  merge_ratings.py     fold Artifact-db ratings (data/ratings/) back into feedback.md
  push_notion.py       append the issue to a Notion DB (env NOTION_TOKEN/NOTION_DB_ID)
data/
  raw/<date>.json     collected articles (full set, pre-scoring)
  state/seen.json     ids already collected — never hand-edit
  ratings/            rating docs dumped from the Artifact db (transient)
digests/<date>.json         the digest deliverable + durable readable record, authored by Codex
digests/assets/<date>/      graphical-abstract images (auto for Nature; drop others in by hand)
feedback.md           the durable rating record (git-tracked); synced from the Artifact
inbox.md              drop DOIs/URLs here by hand; the relevant step folds them in
                      (## Pending — papers  vs  ## Pending — news)

news/                        SECOND TRACK — policy / market news, daily, Codex-run, no scripts
  principles.md              target market + bottleneck framing + "when in doubt, include"
  curation_notes.md          exclusion rules + dated feedback log — read before each run
  sources.md                 sources (core / opportunity pool) + theme defs + access limits
  _report_template.md        Markdown skeleton for the daily report
  _schema.json               JSON skeleton (consumed by scripts/render_site.py)
  <date>_policy_news.md/.json the daily deliverable — never overwrite a prior day
site/<date>.html             combined page: paper digest + policy/market news, from render_site.py
  <date>.embed.html          self-contained (images inlined) — one-file copy to send
  <date>.artifact.html       wrapperless + rating buttons — this is what gets published

## The combined Artifact

One reusable Artifact hosts the **combined page** (paper digest + policy/market
news), rebuilt by `render_site.py --artifact` and republished to the same URL:
**https://Codex.ai/code/artifact/93c92274-daa7-4e29-a86a-e1bf024efbbc**
(`capabilities: {db: {}}`; title "材料インテリジェンス", favicon 🧪). Its −/~/+
buttons on the paper picks write to db collection `ratings` (doc id
`<digest-date>__<doi-slug>`; fields `date, doi, title, journal_short, score,
mark, note, updated`) — unchanged from when this URL hosted the digest-only page,
so `merge_ratings.py` and the Phase 0 tuning loop keep working. Republish to this
same URL (pass it as `url` from a fresh session). `feedback.md` stays the source
of truth — the buttons are just the input surface, merged back by
`merge_ratings.py`.
```

## Environment

Bare `python` on this machine is the broken Windows Store stub. Use the
miniconda interpreter: `& "$env:USERPROFILE\miniconda3\python.exe" scripts\...`
(PowerShell). Deps in that base env: `feedparser`, `requests`, `pyyaml`.

## Weekly workflow

Operational runbook: `.Codex/skills/material-intel/SKILL.md` (Track A: A0 tune →
A1 build; Track B: news; Track C: combined-page render + publish). This section is
the design reference; keep the two in step when either changes.

1. **Tune from feedback — always first, before any fetching.** See
   `config/scoring.md` > "Feedback loop".
   a. Pull ratings from the digest Artifact db: `Artifact` tool
      `action=read_db url=<digest artifact url> db_op=query collection=ratings`
      `query={"where":[["date","==","<prev-date>"]]} out_dir=data/ratings`
   b. `python scripts/merge_ratings.py <prev-date>` — folds them into `feedback.md`.
   c. `python scripts/feedback_report.py`, propose 1–2 small edits to
      `keywords.yaml` / `scoring.md`, apply after the owner okays, log to
      `config/tuning-log.md`.
   No-op if there are no new ratings (say so in one line, continue).

2. **Fetch** — `python scripts/fetch_feeds.py`
   Writes `data/raw/<today>.json`. Idempotent: re-running the same day only adds
   newly-appeared articles. Use `--days N` to widen the Crossref window (default 7),
   `--all` to ignore dedupe state, `--check` to test sources without writing.

3. **Enrich (optional)** — `python scripts/enrich.py data/raw/<today>.json`
   Fills `citations` / `citations_per_month` from OpenAlex. Fresh articles will be
   ~0; still useful when the window is widened or for `inbox.md` entries.

4. **Triage** — `python scripts/triage.py data/raw/<today>.json --top 160`
   Coarse keyword pre-filter. Writes `<date>.shortlist.json` and a readable
   `<date>.shortlist.txt`. ~1000 items -> ~160 for the model to score by hand.
   This is a volume cut, not the scorer.

5. **Score & write the digest** — done by Codex, not a script:
   - Read `config/keywords.yaml` and `config/scoring.md` (post-tuning).
   - Read `<date>.shortlist.txt`; also scan the raw file's top titles outside the
     shortlist for anything the keyword filter missed, and fold in `inbox.md`.
   - **Score pass**: score Relevance / Novelty / Topicality (0–5) against the
     rubric, compute the weighted final, take the top 20 per `scoring.md`.
   - Elsevier items arrive with no abstract. If such a title scores high on
     relevance, fetch the abstract from the article page (WebFetch the DOI URL)
     before finalising its novelty score.
   - For each pick, set `image` to the Nature/Springer og:image URL when the
     journal is Nature-family (fetch `https://doi.org/<doi>`, read
     `<meta property="og:image">`). ACS / Wiley / RSC / Elsevier block all
     automated access — leave `image` unset for those; the owner can drop a file
     into `digests/assets/<date>/<doi-slug>.png` by hand and it will be used.
   - Write `digests/<today>.json` (schema below) with **`summary_ja` in Japanese**
     (2–4 sentences), `caveat_ja` optional. Titles/authors stay as published.
     Do not overwrite a prior day's digest.
   - Append a rating block for the picks to `feedback.md` under a `## <today>`
     heading (DOI + `?` + short title); put the dropped summary in `dropped_ja`.
   - Render + publish the combined page: `python scripts/render_site.py --artifact`
     (picks up the latest digest + latest news), then republish
     `site/<today>.artifact.html` to the Artifact's existing URL (pass it as
     `url`) — the rating buttons ride on the paper picks. Also run
     `render_site.py` for the local `site/<today>.html`. See "Combined site page".

## Digest JSON schema

Authored by Codex as `digests/<date>.json`; `render_site.py` turns it (plus the
latest news file) into the combined HTML the owner reads.

```jsonc
{
  "date": "YYYY-MM-DD",
  "stats": {"journals": N, "new": M, "scored": K, "picks": P},
  "intro_ja": "この号の位置づけを1〜2文で（任意）",
  "picks": [{
    "rank": 1,
    "title": "English title as published",
    "authors": "Family, Family, Family, et al.",
    "journal_short": "Macromolecules",
    "doi": "10.1021/...", "url": "https://doi.org/10.1021/...",
    "published": "YYYY-MM",
    "score": 4.4, "relevance": 5.0, "novelty": 4.0, "topicality": 3.5,
    "summary_ja": "日本語で2〜4文。何をして、なぜ注目か、何が新しいか。",
    "caveat_ja": "任意。誇張・要旨欠落・射程の狭さなど。",
    "image": "https://media.springernature.com/...  (Nature only; omit otherwise)"
  }],
  "watchlist": [{"title": "...", "journal_short": "...", "doi": "...",
                 "url": "...", "note_ja": "一言（なぜ当落線上か）"}],
  "dropped_ja": "内訳の一文。"
}
```

## News track (policy / market — separate, daily)

Independent of the paper digest above. Curate policy / regulation / market-trend
news for a polymer-maker's new-business scouting. Manual trigger, daily, no fetch
script — Codex sweeps the sources live. Reports are in Japanese.

1. Read `news/principles.md`, `news/curation_notes.md`, `news/sources.md`.
2. Sweep the core sources in `sources.md` (add opportunity-pool sources when the
   day's topics warrant). Fold in `## Pending — news` lines from `inbox.md`.
3. Triage wide — theme 1 = policy hitting polymer makers directly; theme 2 =
   power / energy incl. nuclear, actively reasoning where polymers fit even when
   the keywords are absent. When in doubt, keep it (`principles.md`).
4. Write `news/<today>_policy_news.md` + `.json` (template `news/_report_template.md`,
   schema `news/_schema.json`). State up front whether primary PDFs were read or
   only agenda / headline level. Two tiers: 本筋 / 裾野・要ご判断. End with a
   per-source coverage table and a one-line drop summary. Never overwrite a prior day.
   Do not reconstruct a primary source's substance from secondary write-ups — an
   item that couldn't be read stays at "announced + follow-up"; numbers/claims are
   provisional until first-party confirmed (see `news/curation_notes.md`, 2026-09-07).
5. Render the combined page: `python scripts/render_site.py` — see below.
6. User feedback on scope → append a dated entry to `news/curation_notes.md`.
   Don't create permanent rules otherwise.

## Combined site page

`scripts/render_site.py` merges the **latest** `digests/<date>.json` and the
**latest** `news/<date>_policy_news.json` into one page — the paper digest and the
policy/market news read as one deliverable.

- `python scripts/render_site.py` → `site/<date>.html` (local; digest graphical
  abstracts are referenced at `../digests/assets/<date>/…`, not copied).
- `--embed` → `site/<date>.embed.html`, images inlined, self-contained — a one-file
  copy to hand over with `SendUserFile`.
- `--artifact` → `site/<date>.artifact.html`: like `--embed`, plus no `<!doctype>`
  wrapper and −/~/+ rating buttons on each paper pick. **This is the file published
  to the Artifact** at the URL in "The combined Artifact" — republish to that same
  `url`; buttons write to the `ratings` collection keyed by the digest's date
  (doc id `<digest-date>__<slug>`), so `merge_ratings.py` is unaffected.
- `--date YYYY-MM-DD`, or `--digest PATH` / `--news PATH`, to pin inputs. Either
  section renders as "本号は該当なし" if its file is absent (weekly digest + daily
  news means most days have news only). `<date>` on the output = the later of the
  two input dates.
- `render_site.py` is the single renderer — self-contained (the card design system
  + rating CSS/JS it once imported from `render_digest.py` are now inlined). The
  old `render_digest.py` is retired to `削除/`.
- Hosting: local `site/` is the record of truth; the `--artifact` build is the
  shared Artifact; `--embed` for one-off sends.

## Conventions

- All API calls send a real mailto UA, read from env `JOURNAL_RESEARCH_EMAIL`
  (set it in the shell profile) — it's the polite-pool contact for Crossref/OpenAlex.
- `data/raw/*.json` and `data/state/seen.json` are machine-owned. Edit `config/*`
  and `inbox.md` freely.
- Crossref caps a response at 200 rows/journal per run. At a weekly cadence with
  a 7-day window that is not a real limit; if a run truncates (JACS/ACS AMI show
  exactly 200), rerun sooner or split the window.
- Adding a journal: append to `config/feeds.yaml` (`source: rss` + `url`, or
  `source: crossref` + `issn`), then `python scripts/fetch_feeds.py --check`.

## Scheduling

Intended to run weekly via the `schedule` skill (a cloud cron agent): run the
weekly workflow above (tune from last week's ratings first), build
`site/<date>.artifact.html` with `render_site.py --artifact` and republish it to
the combined Artifact URL, run `render_site.py` for the local page, log the issue
to Notion (`python scripts/push_notion.py <date>` — needs env `NOTION_TOKEN` /
`NOTION_DB_ID`; see the skill's Track C step 4), then commit the new
`data/raw/*`, `digests/<date>.json`, `digests/assets/<date>/*`,
`site/<date>.html`, the merged `feedback.md`, and any `config/` changes from a
tuning pass. (`*.artifact.html` and `site/*.embed.html` are disposable builds —
regenerate rather than rely on the committed copy.) Not yet wired up — see the
owner before enabling.

The news track (daily, manual) is not scheduled. Whenever it runs it also ends by
calling `render_site.py` (and `--artifact` + republish if the Artifact should
reflect the new news), so `site/<date>.html` reflects the newest news plus the
most recent weekly digest.
