---
name: material-intel
description: >
  Run the "材料インテリジェンス" deliverable for this repo — one combined page
  (Artifact) with two tracks: the WEEKLY polymer / materials-chemistry paper
  digest (fetch → tune scoring from reader feedback → score → publish) and the
  DAILY policy / market news curation for new-business scouting. Both tracks end
  by rebuilding and republishing the combined page. Use when the user asks to
  "run the digest", "make a new digest", "check for new papers", "pull feedback",
  "tune the scoring", "run the news", "policy news", "update the site", or
  "rebuild the combined page".
---

# material-intel

One deliverable, two tracks, one Artifact.

- **Track A — paper digest** (weekly): the polymer / materials-chemistry journal
  digest. Design + rubric: `AGENTS.md` and `config/scoring.md`.
- **Track B — policy / market news** (daily): `AGENTS.md` > "News track" +
  `news/principles.md`, `news/curation_notes.md`, `news/sources.md`.
- Both finish with **Track C — render + publish** the combined page, then log the
  issue to a Notion database (`push_notion.py`) as an accumulating record.

This file is the runbook; read the design docs it points to.

## Setup (once per session)

- Python: bare `python` is the broken Windows Store stub. Use miniconda:
  - PowerShell: `& "$env:USERPROFILE\miniconda3\python.exe" scripts\<x>.py`
  - bash: `"$USERPROFILE/miniconda3/python.exe" scripts/<x>.py`
  - deps already there: `feedparser requests pyyaml`
- `<date>` = today, `YYYY-MM-DD`. `<prev-date>` = newest existing `digests/*.json`.
- Combined Artifact (reuse this URL, never make a new one):
  `https://Codex.ai/code/artifact/93c92274-daa7-4e29-a86a-e1bf024efbbc`
  (title "材料インテリジェンス", favicon 🧪, `capabilities: {db:{}}`).
- "削除して" = move the file into `削除/`, never `rm`.

---

## Track A — paper digest (weekly)

Run **A0 then A1**, same turn. A0 is not optional — always attempt it first so
the digest is scored with the rubric the latest feedback implies. Skip A0 only if
there is no `<prev-date>` digest yet, or the user says to skip tuning.

### A0 — pull feedback and tune the scoring

1. Pull ratings from the Artifact db: `Artifact` tool → `action=read_db`,
   `url=<Artifact URL>`, `db_op=query`, `collection=ratings`,
   `query={"where":[["date","==","<prev-date>"]]}`, `out_dir=data/ratings`
2. `python scripts/merge_ratings.py <prev-date>` — folds marks/notes into
   `feedback.md`. "no rating docs" → nothing new: say so in one line, go to A1.
3. `python scripts/feedback_report.py` — per-rating abstracts, notes, and
   score-vs-rating disagreements.
4. Read the report, find patterns (`config/scoring.md` > "Feedback loop").
   Propose **1–2 small edits** to `config/keywords.yaml` / `config/scoring.md`.
   State them and wait for a yes (a one-liner is enough); if the user
   pre-authorised auto-tuning, apply directly.
5. Apply the edits, append a dated entry to `config/tuning-log.md` (what changed,
   which ratings drove it). Continue to A1 with the updated config.

No ratings at all → A0 is a no-op; note it and move on.

### A1 — build the digest

1. **Fetch** — `python scripts/fetch_feeds.py`
   (`--days N` widens the Crossref window; `--check` tests sources only.)
2. **Enrich** — `python scripts/enrich.py data/raw/<date>.json`
3. **Triage** — `python scripts/triage.py data/raw/<date>.json --top 160`
   → `data/raw/<date>.shortlist.txt` (readable) + `.shortlist.json`.
4. **Score** (you, not a script): read `config/keywords.yaml` +
   `config/scoring.md` (as just tuned), read the shortlist txt, skim raw titles
   outside it for misses, fold in `inbox.md` (`## Pending — papers`). Score
   Relevance / Novelty / Topicality, take the top 20 (≥ ~3.0). For Nature-family
   picks set `image` to the article's `og:image`; ACS / Wiley / RSC / Elsevier
   block automated access — leave unset (a file dropped in
   `digests/assets/<date>/<doi-slug>.png` is picked up).
5. **Write** — author `digests/<date>.json` per the schema in `AGENTS.md`.
   `summary_ja` / `caveat_ja` / `note_ja` / `intro_ja` / `dropped_ja` in
   **Japanese**; titles + authors stay as published. Do not overwrite a prior
   day's digest. Append a `## <date>` rating block to `feedback.md` (one line
   per pick: `<doi>  ?  <short title>`).
6. → **Track C**.

---

## Track B — policy / market news (daily)

Read `news/principles.md`, `news/curation_notes.md`, `news/sources.md` first.

1. Sweep the core sources in `news/sources.md` (add opportunity-pool sources when
   the day's topics warrant). Fold in `## Pending — news` lines from `inbox.md`.
2. Triage wide — theme 1 = policy hitting polymer makers directly; theme 2 =
   power / energy incl. nuclear, actively reasoning where polymers fit even when
   the keywords are absent. When in doubt, keep it (`news/principles.md`).
3. Write `news/<date>_policy_news.md` + `.json` (template
   `news/_report_template.md`, schema `news/_schema.json`). State up front
   whether primary PDFs were read or only agenda / headline level. Two tiers:
   本筋 / 裾野・要ご判断. Per-source coverage table + one-line drop summary at the
   end. Never overwrite a prior day. **Do not reconstruct a primary source's
   substance from secondary write-ups** — an item that couldn't be read stays at
   "announced + follow-up"; numbers/claims are provisional until first-party
   confirmed (`news/curation_notes.md`, 2026-09-07).
4. → **Track C**.
5. User feedback on scope → append a dated entry to `news/curation_notes.md`.
   Don't create permanent rules otherwise.

---

## Track C — render + publish the combined page

1. `python scripts/render_site.py --artifact` → `site/<date>.artifact.html`
   = latest digest (with −/~/+ rating buttons) + latest policy/market news.
   Runs even if one side is missing (that section shows "本号は該当なし").
2. Publish it to the Artifact URL above (`Artifact` tool, `url=<that URL>`; omit
   `capabilities` to carry `{db:{}}` forward). Read the artifact first if this
   session hasn't published it before.
3. `python scripts/render_site.py` → local `site/<date>.html` (record of truth)
   and `python scripts/render_site.py --embed` → `site/<date>.embed.html`
   (self-contained, images inlined).
4. **Log the issue to Notion** — `python scripts/push_notion.py <date>`
   Appends (or refreshes) one page per issue in the Notion database: pushes the
   digest entry when `digests/<date>.json` exists and the news entry when
   `news/<date>_policy_news.json` exists (so a weekly run logs the digest, a
   daily news run logs the news). Page = date + 種別 + Artifact link + count +
   `intro_ja` + the picks / items as a bulleted body.
   - Needs env vars `NOTION_TOKEN` and `NOTION_DB_ID` (internal integration token
     + the DB shared with that integration). If unset, the script exits with a
     message — tell the user to set them and skip this step for now.
   - `--dry-run` prints the payload; `--kind digest|news` forces one.

`<date>` on the output = the later of the digest date and the news date.

## Notes

- `scripts/render_site.py` is the only renderer (self-contained; the old
  `render_digest.py` is retired to `削除/`). Its `--artifact` rating buttons write
  to db collection `ratings`, doc id `<digest-date>__<slug>` — unchanged, so
  `merge_ratings.py` and A0 keep working.
- `feedback.md` is the durable git-tracked record; the Artifact buttons are just
  the input surface, merged in by A0 step 2.
- `data/raw/*.json`, `data/state/seen.json`, `data/ratings/` are machine-owned.
- Adding a journal: edit `config/feeds.yaml`, then `fetch_feeds.py --check`.
- Not on a schedule — runs only when invoked.
