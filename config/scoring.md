# Scoring rubric — "is this paper interesting?"

The scoring step (run by Claude) reads `data/raw/<date>.json`, evaluates every
item against this rubric, and writes a ranked digest as `digests/<date>.json`
(schema in CLAUDE.md), which `scripts/render_site.py` turns into the combined HTML page.
Summaries (`summary_ja`, `caveat_ja`, `note_ja`, `intro_ja`, `dropped_ja`) are
written in Japanese; titles and author lists stay as published.

## Score = weighted sum of three axes (0–5 each)

| Axis | Weight | What it measures | Evidence to use |
|---|---|---|---|
| **Relevance** | 45% | Overlap with `config/keywords.yaml` | title + abstract vs. core / adjacent / exclude lists |
| **Novelty** | 40% | Is the central claim surprising or a real departure from prior work? | abstract: what is claimed as new; hedge words; "first", "unprecedented" (discount hype) |
| **Topicality** | 15% | Is the wider community paying attention to this thread? | citation count & recent velocity (from enrich step), hot subfield, well-known group |

**Final score** = `0.45*Relevance + 0.40*Novelty + 0.15*Topicality` → round to 1 decimal, expressed on a 0–5 scale.

### Axis anchors

**Relevance**
- 5 — squarely in a `core` topic
- 3 — an `adjacent` topic, or core-adjacent framing
- 1 — tangential; materials/chemistry but not the areas of interest
- 0 — matches an `exclude` clause

**Novelty**
- 5 — new mechanism, concept, or a result that overturns an expectation
- 3 — solid incremental advance; new system for a known strategy
- 1 — routine characterization / minor variation on established work
- 0 — nothing identifiable as new from the abstract
- **Cap at 3** when the contribution is a new synthetic route to a known or niche
  polymer target, a scope extension of an established method (new monomer /
  initiator / substrate), or a new combination of known reactions — *unless* it
  enables something previously impossible (metal-free / ambient / O2-tolerant
  control, a closed trade-off) or reveals genuinely unexpected behaviour.
  [2026-09-07 feedback: four such papers were rated "not for me" at novelty 4.]

**Topicality**
- 5 — fast-moving subfield, or already accumulating citations unusually quickly
- 3 — steady active area
- 1 — niche / quiet corner
- (new papers with no citation data yet: judge by subfield heat, default 2–3)

## Selection

- **Digest picks**: the **top 20 by final score**, provided they clear **≥ 3.0**.
  Always aim to fill 20; if fewer than 20 clear 3.0, list what qualifies and say so.
- **Watchlist**: next 6–10 below the cut (down to ~2.6) — one-line mentions.
- Below that — dropped (kept in raw JSON, not shown).
- Number the 20 picks by score, but the digest need not be a strict ranking —
  keep a couple of high-relevance outliers over near-duplicate clusters for range.

## Notes

- No abstract available → score Relevance/Topicality from title + journal, set Novelty ≤ 3, flag `abstract: missing`.
- Be skeptical of promotional abstract language; score the substance.
- One review article max per digest unless a review is genuinely field-defining.

## Feedback loop — how this rubric gets tuned

The owner rates each pick `+` (interesting), `-` (not for me), or `~` (meh),
optionally with a note — via the combined Artifact's buttons on the paper picks
(preferred) or by editing `feedback.md`. That signal tunes this file and
`config/keywords.yaml`.

On request (or at the start of a run once ≥ ~15 new ratings have accumulated):

0. Pull Artifact-db ratings into `feedback.md`: `Artifact` tool `read_db` on
   collection `ratings`, then `python scripts/merge_ratings.py <date>`.
1. `python scripts/feedback_report.py` — joins `feedback.md` to the archived raw
   records and prints, per rating, the papers + abstracts + notes, plus where the
   model's score disagreed with the owner (high score → `-`, low score → `+`).
2. Read that report and look for patterns:
   - Terms/subfields that consistently earn `+` but aren't in `core` → promote / add.
   - `core` terms whose papers consistently earn `-` → demote to `adjacent` or drop.
   - Systematic score bias (e.g. novelty over-rated for a journal, topicality
     mis-called for a subfield) → adjust the anchors or weights here.
   - If `+`/`-` splits cleanly on an axis the rubric doesn't have (methodology vs.
     application, experiment vs. simulation), add that axis.
3. Propose the concrete edits, apply them after the owner okays, and append a
   dated entry to `config/tuning-log.md` (what changed, which ratings drove it).

Keep changes small and reversible — one or two adjustments per tuning pass, so the
effect on the next digest is legible.
