"""Join feedback.md ratings to the archived article records and summarise them,
so the rubric / keywords can be tuned from real signal.

Usage:
    python scripts/feedback_report.py            # all rated dates
    python scripts/feedback_report.py 2026-09-07 # one date

Reads:  feedback.md, data/raw/*.json, digests/*.md
Prints: ratings grouped by +/-/~, each with journal + abstract + note + the
        model's digest score, plus a keyword-lean tally and score-vs-rating
        disagreements. Writes nothing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from triage import adj_re, core_re, exc_re  # noqa: E402

FEEDBACK = Path(__import__("os").environ.get("FEEDBACK_FILE", ROOT / "feedback.md"))
RAW_DIR = ROOT / "data" / "raw"
DIGEST_DIR = ROOT / "digests"

MARKS = {"+": "interesting", "-": "not for me", "~": "meh"}
LINE_RE = re.compile(r"^(10\.\S+)\s+([+\-~?])\s*(.*)$")
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
SCORE_RE = re.compile(
    r"Score\s+([\d.]+).*?relevance\s+([\d.]+)/5.*?novelty\s+([\d.]+)/5.*?topicality\s+([\d.]+)/5",
    re.I,
)
NOTE_SEP_RE = re.compile(r"\s+(?:--|—|–)\s+")


def parse_feedback() -> dict[str, dict]:
    if not FEEDBACK.exists():
        sys.exit("no feedback.md")
    out: dict[str, dict] = {}
    date = None
    for line in FEEDBACK.read_text(encoding="utf-8").splitlines():
        m = DATE_RE.match(line)
        if m:
            date = m.group(1)
            out[date] = {"ratings": [], "notes": ""}
            continue
        if date is None:
            continue
        if line.startswith("notes:"):
            out[date]["notes"] = line[len("notes:"):].strip()
            continue
        lm = LINE_RE.match(line.strip())
        if lm:
            doi, mark, rest = lm.group(1).lower().rstrip("."), lm.group(2), lm.group(3)
            note = ""
            parts = NOTE_SEP_RE.split(rest, maxsplit=1)
            if len(parts) == 2:
                rest, note = parts
            out[date]["ratings"].append({"doi": doi, "mark": mark, "label": rest.strip(), "note": note.strip()})
    return out


def load_raw_index() -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for f in sorted(RAW_DIR.glob("*.json")):
        if f.name.endswith(".shortlist.json"):
            continue
        for it in json.loads(f.read_text(encoding="utf-8")):
            if it.get("doi"):
                idx.setdefault(it["doi"].lower(), it)
    return idx


def digest_scores(date: str) -> dict[str, tuple]:
    path = DIGEST_DIR / f"{date}.md"
    if not path.exists():
        return {}
    scores: dict[str, tuple] = {}
    cur_doi = None
    for line in path.read_text(encoding="utf-8").splitlines():
        dm = re.search(r"10\.\d{4,9}/[^\s)\]]+", line)
        if dm and "doi.org" in line:
            cur_doi = dm.group(0).lower().rstrip(".")
        sm = SCORE_RE.search(line)
        if sm and cur_doi:
            scores[cur_doi] = tuple(float(x) for x in sm.groups())
    return scores


def kw_tally(text: str) -> tuple[int, int, int]:
    return (
        sum(1 for p in core_re if p.search(text)),
        sum(1 for p in adj_re if p.search(text)),
        sum(1 for p in exc_re if p.search(text)),
    )


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else None
    fb = parse_feedback()
    raw = load_raw_index()

    agg = {"+": [], "-": [], "~": []}
    for date, blob in fb.items():
        if want and date != want:
            continue
        scores = digest_scores(date)
        rated = [r for r in blob["ratings"] if r["mark"] in MARKS]
        if not rated and not blob["notes"]:
            continue
        print(f"\n{'=' * 78}\n{date}   ({len(rated)} rated of {len(blob['ratings'])})")
        if blob["notes"]:
            print(f"digest note: {blob['notes']}")
        for r in rated:
            it = raw.get(r["doi"], {})
            sc = scores.get(r["doi"])
            agg[r["mark"]].append({**r, "item": it, "score": sc})
            title = it.get("title") or r["label"]
            jr = it.get("journal_short", "?")
            abstract = (it.get("abstract") or "").strip()
            print(f"\n  [{r['mark']}] {title}  ({jr})")
            print(f"      {r['doi']}" + (f"   model: final {sc[0]} (r{sc[1]}/n{sc[2]}/t{sc[3]})" if sc else ""))
            if r["note"]:
                print(f"      note: {r['note']}")
            if abstract:
                print(f"      abs: {abstract[:400]}{' ...' if len(abstract) > 400 else ''}")
            else:
                print("      abs: (none on record)")

    print(f"\n{'=' * 78}\nSUMMARY")
    for mk, label in MARKS.items():
        rows = agg[mk]
        if not rows:
            continue
        c = a = e = 0
        for row in rows:
            t = f"{row['item'].get('title', '')} {row['item'].get('abstract', '')}"
            dc, da, de = kw_tally(t)
            c += dc
            a += da
            e += de
        n = len(rows)
        print(f"  {mk} {label:<12} n={n:>3}   core-hits/paper {c / n:.1f}   adjacent/paper {a / n:.1f}   exclude/paper {e / n:.1f}")

    dis = [r for r in agg["-"] if r["score"] and r["score"][0] >= 3.7]
    if dis:
        print("\n  DISAGREEMENT -- rated '-' but model scored >= 3.7:")
        for r in dis:
            print(f"    {r['score'][0]}  {r['item'].get('title', r['label'])[:70]}")
    dis2 = [r for r in agg["+"] if r["score"] and r["score"][0] < 3.4]
    if dis2:
        print("\n  DISAGREEMENT -- rated '+' but model scored < 3.4:")
        for r in dis2:
            print(f"    {r['score'][0]}  {r['item'].get('title', r['label'])[:70]}")

    total = sum(len(v) for v in agg.values())
    print(f"\n  total rated: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
