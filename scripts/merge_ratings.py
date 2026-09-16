"""Merge rating docs pulled from the digest Artifact's db into feedback.md.

The digest is published as an Artifact whose +/-/~ buttons write to its db
collection `ratings` (doc id `<date>__<doi-slug>`, fields date/doi/mark/note/...).
Before a tuning pass, dump that collection with the Artifact tool, e.g.

    Artifact  action=read_db  url=<digest artifact url>  db_op=query
              collection=ratings  query={"where":[["date","==","2026-09-07"]]}
              out_dir=data/ratings

then:

    python scripts/merge_ratings.py 2026-09-07            # dir defaults to data/ratings
    python scripts/merge_ratings.py 2026-09-07 --dir some/dir --dry-run

It rewrites the `## <date>` block in feedback.md, replacing each line's `?`
with the mark from the db and appending ` -- <note>` when a note is set.
Lines whose DOI has no db rating are left untouched.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = ROOT / "feedback.md"
VALID = {"+", "-", "~"}
LINE_RE = re.compile(r"^(10\.\S+)\s+([+\-~?])\s*(.*)$")


def load_ratings(dir_: Path, date: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in dir_.rglob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = d if isinstance(d, list) else [d]
        for r in rows:
            if not isinstance(r, dict) or not r.get("doi"):
                continue
            if date and r.get("date") and r["date"] != date:
                continue
            out[r["doi"].lower().rstrip(".")] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date", help="digest date, e.g. 2026-09-07")
    ap.add_argument("--dir", default=str(ROOT / "data" / "ratings"), help="dir of rating JSON files")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ratings = load_ratings(Path(args.dir), args.date)
    if not ratings:
        print(f"no rating docs for {args.date} under {args.dir}")
        return 0

    lines = FEEDBACK.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == f"## {args.date}")
    except StopIteration:
        sys.exit(f"feedback.md has no '## {args.date}' block — write the digest's rating block first")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))

    changed = 0
    for i in range(start, end):
        m = LINE_RE.match(lines[i].strip())
        if not m:
            continue
        doi = m.group(1).lower().rstrip(".")
        r = ratings.get(doi)
        if not r:
            continue
        mark = r.get("mark") or "?"
        if mark not in VALID:
            mark = "?"
        label = m.group(3)
        label = re.split(r"\s+--\s+", label, maxsplit=1)[0].rstrip()
        note = (r.get("note") or "").strip()
        newline = f"{m.group(1)}  {mark}  {label}" + (f"  -- {note}" if note else "")
        if newline != lines[i]:
            lines[i] = newline
            changed += 1

    marked = sum(1 for r in ratings.values() if (r.get("mark") or "") in VALID)
    print(f"{len(ratings)} rating docs ({marked} with a +/-/~) -> {changed} line(s) updated in feedback.md")
    if args.dry_run:
        for i in range(start, end):
            if LINE_RE.match(lines[i].strip()):
                print("  " + lines[i])
        return 0
    FEEDBACK.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote feedback.md — now run: python scripts/feedback_report.py " + args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
