"""Fetch journal sources (RSS + Crossref) and collect new articles.

Usage:
    python scripts/fetch_feeds.py            # fetch, dedupe, write data/raw/<today>.json
    python scripts/fetch_feeds.py --check    # test every source, write nothing
    python scripts/fetch_feeds.py --all      # ignore seen-state (re-collect everything)
    python scripts/fetch_feeds.py --date 2026-09-07     # force the output date
    python scripts/fetch_feeds.py --days 14  # widen the Crossref look-back window

Reads:  config/feeds.yaml
Writes: data/raw/<date>.json    (new articles)
        data/state/seen.json    (id -> first-seen date, for dedupe)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
FEEDS_YAML = ROOT / "config" / "feeds.yaml"
RAW_DIR = ROOT / "data" / "raw"
STATE_FILE = ROOT / "data" / "state" / "seen.json"

CONTACT = os.environ.get("JOURNAL_RESEARCH_EMAIL", "you@example.com")
UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
UA_API = f"journal-research/0.1 (mailto:{CONTACT})"
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.I)
TAG_RE = re.compile(r"<[^>]+>")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = TAG_RE.sub(" ", str(text))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def make_id(doi: str | None, fallback: str) -> str:
    return f"doi:{doi.lower()}" if doi else (fallback or "").strip()


# --------------------------------------------------------------------------- RSS
def fetch_rss(feed: dict) -> list[dict]:
    resp = requests.get(
        feed["url"],
        headers={"User-Agent": UA_BROWSER, "Accept": "application/rss+xml, application/xml, */*"},
        timeout=30,
    )
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"parse error: {parsed.bozo_exception}")

    items = []
    for e in parsed.entries:
        doi = _doi_from_fields(e.get("prism_doi"), e.get("dc_identifier"), e.get("doi"),
                               e.get("id"), e.get("link"), e.get("summary"))
        authors = [clean(a.get("name")) for a in e.get("authors", []) if a.get("name")]
        if not authors and e.get("author"):
            authors = [clean(e["author"])]
        published = ""
        for key in ("published_parsed", "updated_parsed"):
            if e.get(key):
                published = time.strftime("%Y-%m-%d", e[key])
                break
        items.append({
            "doi": doi,
            "title": clean(e.get("title")),
            "authors": authors,
            "url": e.get("link", ""),
            "abstract": clean(e.get("summary")),
            "published": published,
            "_fallback_id": e.get("id") or e.get("link") or e.get("title", ""),
        })
    return items


# ---------------------------------------------------------------------- Crossref
def fetch_crossref(feed: dict, since: str) -> list[dict]:
    params = {
        "filter": f"from-created-date:{since},type:journal-article",
        "sort": "created",
        "order": "desc",
        "rows": 200,
        "select": "DOI,title,author,abstract,created,published,URL,subtitle",
    }
    resp = requests.get(
        f"https://api.crossref.org/journals/{feed['issn']}/works",
        params=params,
        headers={"User-Agent": UA_API},
        timeout=45,
    )
    resp.raise_for_status()
    message = resp.json()["message"]

    items = []
    for w in message["items"]:
        doi = (w.get("DOI") or "").lower() or None
        title = clean(" ".join(w.get("title", [])) or "")
        created = w.get("created", {}).get("date-parts", [[None]])[0]
        published_parts = w.get("published", {}).get("date-parts", [[None]])[0]
        parts = published_parts if published_parts and published_parts[0] else created
        published = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p is not None)
        authors = []
        for a in w.get("author", []):
            name = " ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "")
            if name:
                authors.append(clean(name))
        items.append({
            "doi": doi,
            "title": title,
            "authors": authors,
            "url": w.get("URL", f"https://doi.org/{doi}" if doi else ""),
            "abstract": clean(w.get("abstract")),
            "published": published,
            "_fallback_id": doi or title,
        })
    return items


def _doi_from_fields(*fields) -> str | None:
    for f in fields:
        if not f:
            continue
        m = DOI_RE.search(str(f))
        if m:
            return m.group(0).rstrip(".")
    return None


# --------------------------------------------------------------------------- run
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="test sources only, write nothing")
    ap.add_argument("--all", action="store_true", help="ignore seen-state, collect every entry")
    ap.add_argument("--date", help="output date (YYYY-MM-DD), default today")
    ap.add_argument("--days", type=int, help="Crossref look-back window in days")
    args = ap.parse_args()

    today = args.date or dt.date.today().isoformat()
    cfg = yaml.safe_load(FEEDS_YAML.read_text(encoding="utf-8"))
    window = args.days or cfg.get("defaults", {}).get("crossref_window_days", 7)
    since = (dt.date.today() - dt.timedelta(days=window)).isoformat()
    feeds = [f for f in cfg.get("feeds", []) if f.get("enabled", True)]
    state = {} if args.check else _load_state()

    collected: list[dict] = []
    print(f"since (crossref): {since}   window: {window}d\n")
    print(f"{'source':<22} {'ok':>5} {'entries':>8} {'new':>5}  note")
    print("-" * 72)

    for f in feeds:
        short = f.get("short", f["name"])
        src = f.get("source", "rss")
        try:
            raw = fetch_rss(f) if src == "rss" else fetch_crossref(f, since)
        except Exception as exc:  # noqa: BLE001
            print(f"{short[:22]:<22} {'ERR':>5} {'-':>8} {'-':>5}  {type(exc).__name__}: {str(exc)[:60]}")
            continue

        new_here = 0
        for it in raw:
            eid = make_id(it["doi"], it.pop("_fallback_id"))
            if not eid or (not args.all and eid in state):
                it.pop("_fallback_id", None)
                continue
            item = {
                "id": eid,
                "doi": it["doi"],
                "title": it["title"],
                "authors": it["authors"],
                "journal": f["name"],
                "journal_short": short,
                "source": src,
                "url": it["url"],
                "abstract": it["abstract"],
                "published": it["published"],
                "collected": today,
            }
            collected.append(item)
            state[eid] = today
            new_here += 1

        print(f"{short[:22]:<22} {'ok':>5} {len(raw):>8} {new_here:>5}")
        time.sleep(1)  # be polite

    print("-" * 72)
    print(f"total new: {len(collected)}")

    if args.check:
        print("\n--check: nothing written.")
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{today}.json"
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    seen_ids = {x["id"] for x in existing}
    merged = existing + [x for x in collected if x["id"] not in seen_ids]
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {out.relative_to(ROOT)}  ({len(merged)} items in file)")
    print(f"state: {len(state)} ids tracked")
    return 0


def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


if __name__ == "__main__":
    sys.exit(main())
