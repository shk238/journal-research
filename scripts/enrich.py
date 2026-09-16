"""Add citation data to a raw file via the OpenAlex API.

Usage:
    python scripts/enrich.py data/raw/2026-09-07.json

For every item with a DOI, fills:
    citations            total citation count (OpenAlex)
    citations_per_month  count / months since publication (rough velocity)
    openalex_id
    abstract             only if the item had none and OpenAlex has one

OpenAlex is free and needs no key; we send a mailto for the polite pool.
Fresh articles will mostly come back with 0 citations — that is expected;
this pass matters when the fetch window is widened or for inbox.md entries.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

MAILTO = os.environ.get("JOURNAL_RESEARCH_EMAIL", "you@example.com")
BATCH = 50


def deinvert(inv: dict | None) -> str:
    if not inv:
        return ""
    positions = [(pos, word) for word, poss in inv.items() for pos in poss]
    positions.sort()
    return " ".join(w for _, w in positions)


def months_since(date_str: str) -> float:
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            d = dt.datetime.strptime(date_str, fmt).date()
            break
        except (ValueError, TypeError):
            continue
    else:
        return 0.0
    days = (dt.date.today() - d).days
    return max(days / 30.44, 0.5)


def main(path_str: str) -> int:
    path = Path(path_str)
    items = json.loads(path.read_text(encoding="utf-8"))
    by_doi = {it["doi"].lower(): it for it in items if it.get("doi")}
    dois = list(by_doi)
    print(f"{len(items)} items · {len(dois)} with DOI")

    session = requests.Session()
    session.headers["User-Agent"] = f"journal-research/0.1 (mailto:{MAILTO})"
    enriched = 0

    for i in range(0, len(dois), BATCH):
        chunk = dois[i : i + BATCH]
        filt = "doi:" + "|".join(chunk)
        resp = session.get(
            "https://api.openalex.org/works",
            params={"filter": filt, "per-page": BATCH, "mailto": MAILTO,
                    "select": "id,doi,cited_by_count,publication_date,abstract_inverted_index"},
            timeout=45,
        )
        resp.raise_for_status()
        for w in resp.json().get("results", []):
            doi = (w.get("doi") or "").replace("https://doi.org/", "").lower()
            it = by_doi.get(doi)
            if not it:
                continue
            cites = w.get("cited_by_count", 0)
            pub = w.get("publication_date") or it.get("published", "")
            it["openalex_id"] = w.get("id", "")
            it["citations"] = cites
            it["citations_per_month"] = round(cites / months_since(pub), 2)
            if not it.get("abstract"):
                it["abstract"] = deinvert(w.get("abstract_inverted_index"))
            enriched += 1
        print(f"  {i + len(chunk):>4}/{len(dois)}  matched so far: {enriched}")
        time.sleep(1)

    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"enriched {enriched} items -> {path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
