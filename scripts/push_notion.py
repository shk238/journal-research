"""Push each paper / news item as its own row into a Notion database.

No Notion connector needed — talks to the Notion REST API with an internal
integration token.

Env vars:
  NOTION_TOKEN          internal integration token  (required)
  NOTION_DB_ID          target database id, 32 hex chars from the DB URL  (required)
  NOTION_VERSION        API version header           (default 2022-06-28)

Usage:
  python scripts/push_notion.py 2026-09-07               # digest picks + watchlist + news items for that date
  python scripts/push_notion.py 2026-09-07 --kind digest
  python scripts/push_notion.py 2026-09-07 --dry-run     # print the rows, write nothing

One row per digest pick, per digest watchlist entry, and per news item.
Idempotent on the `キー` property (paper:<doi> / news:<date>:<id>): a row whose
key already exists is PATCHed instead of duplicated.

Database properties it fills (matched case-insensitively; any it can't find is skipped):
  <title>            found by type — the paper title / the news 見出し
  種別 / Type         select   ("論文" | "ニュース")
  日付 / Date         date     (the issue date)
  掲載号 / Issue       select   ("<date> 週次" | "<date> 日次")
  区分 / Class        select   ("Pick" | "Watchlist" | "本筋" | "裾野")
  スコア / Score       number   (digest picks only)
  出典 / Source       select   (journal_short | source_short)
  テーマ / Theme       select   (news only: "規制・政策" | "電力・エネルギー")
  リンク / Link        url
  評価 / Rating        select   ("+" | "~" | "-" from feedback.md, papers only)
  概要 / Summary       rich_text
  キー / Key           rich_text  (dedup key; hide it in your views)
Manual columns (確認状況 / 重要度 / メモ etc.) are never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.notion.com/v1"

KINDS = {
    "digest": {"rel": lambda d: f"digests/{d}.json", "issue": lambda d: f"{d} 週次"},
    "news": {"rel": lambda d: f"news/{d}_policy_news.json", "issue": lambda d: f"{d} 日次"},
}
THEME = {1: "規制・政策", 2: "電力・エネルギー"}
TIER = {"main": "本筋", "fringe": "裾野"}

# key -> (candidate property names lowercased, required Notion type)
PROP_CANDS = {
    "kind": (["種別", "type", "kind"], "select"),
    "date": (["日付", "date"], "date"),
    "issue": (["掲載号", "issue", "号"], "select"),
    "class": (["区分", "class", "tier"], "select"),
    "score": (["スコア", "score", "点数"], "number"),
    "source": (["出典", "誌名", "情報源", "source", "journal"], "select"),
    "theme": (["テーマ", "theme"], "select"),
    "link": (["リンク", "link", "url", "doi"], "url"),
    "rating": (["評価", "rating", "mark"], "select"),
    "summary": (["概要", "summary", "説明"], "rich_text"),
    "key": (["キー", "key", "dedup"], "rich_text"),
}
FB_LINE = re.compile(r"^(10\.\S+)\s+([+\-~?])")


def _ok(r: requests.Response) -> requests.Response:
    if not r.ok:
        sys.exit(f"Notion API {r.status_code} on {r.request.method} {r.request.url}\n{r.text[:600]}")
    return r


def rt(text: str | None, limit: int = 1900) -> list:
    text = (text or "").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return [{"type": "text", "text": {"content": text}}] if text else []


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:80] or "x"


def headers() -> dict:
    tok = os.environ.get("NOTION_TOKEN")
    if not tok:
        sys.exit("NOTION_TOKEN is not set")
    return {
        "Authorization": f"Bearer {tok}",
        "Notion-Version": os.environ.get("NOTION_VERSION", "2022-06-28"),
        "Content-Type": "application/json",
    }


def resolve_props(db_id: str, h: dict) -> tuple[str | None, dict]:
    props = _ok(requests.get(f"{API}/databases/{db_id}", headers=h, timeout=30)).json()["properties"]
    title_name = next((n for n, p in props.items() if p["type"] == "title"), None)
    lookup = {n.lower(): (n, p["type"]) for n, p in props.items()}
    resolved: dict[str, str] = {}
    for key, (cands, want) in PROP_CANDS.items():
        for c in cands:
            if c in lookup and lookup[c][1] == want:
                resolved[key] = lookup[c][0]
                break
    return title_name, resolved


def feedback_marks(date: str) -> dict[str, str]:
    fb = ROOT / "feedback.md"
    if not fb.exists():
        return {}
    lines = fb.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == f"## {date}")
    except StopIteration:
        return {}
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    out: dict[str, str] = {}
    for ln in lines[start:end]:
        m = FB_LINE.match(ln.strip())
        if m and m.group(2) in "+-~":
            out[m.group(1).lower().rstrip(".")] = m.group(2)
    return out


def digest_rows(date: str, data: dict, marks: dict) -> list[dict]:
    rows = []
    for pk in sorted(data.get("picks", []), key=lambda x: x.get("rank", 999)):
        doi = (pk.get("doi") or "").lower().rstrip(".")
        rows.append({
            "title": pk.get("title", ""), "kind": "論文", "date": date,
            "issue": KINDS["digest"]["issue"](date), "class": "Pick",
            "score": pk.get("score"), "source": pk.get("journal_short"), "theme": None,
            "link": pk.get("url") or (f"https://doi.org/{doi}" if doi else None),
            "rating": marks.get(doi), "summary": pk.get("summary_ja", ""),
            "key": f"paper:{doi}" if doi else f"paper:{date}:{slug(pk.get('title', ''))}",
        })
    for wl in data.get("watchlist", []):
        doi = (wl.get("doi") or "").lower().rstrip(".")
        rows.append({
            "title": wl.get("title", ""), "kind": "論文", "date": date,
            "issue": KINDS["digest"]["issue"](date), "class": "Watchlist",
            "score": None, "source": wl.get("journal_short"), "theme": None,
            "link": wl.get("url") or (f"https://doi.org/{doi}" if doi else None),
            "rating": marks.get(doi), "summary": wl.get("note_ja", ""),
            "key": f"paper:{doi}" if doi else f"paper:{date}:{slug(wl.get('title', ''))}",
        })
    return rows


def news_rows(date: str, data: dict) -> list[dict]:
    rows = []
    for it in data.get("items", []):
        rows.append({
            "title": it.get("title_ja", ""), "kind": "ニュース", "date": date,
            "issue": KINDS["news"]["issue"](date),
            "class": TIER.get(it.get("tier"), it.get("tier")),
            "score": None, "source": it.get("source_short"),
            "theme": THEME.get(it.get("theme")), "link": it.get("url"),
            "rating": None, "summary": it.get("summary_ja", ""),
            "key": f"news:{date}:{it.get('id')}",
        })
    return rows


def props_for(title_name: str | None, R: dict, row: dict) -> dict:
    p: dict = {}
    if title_name:
        p[title_name] = {"title": rt(row["title"])}
    if "date" in R:
        p[R["date"]] = {"date": {"start": row["date"]}}
    for k in ("kind", "issue", "class", "source", "theme", "rating"):
        if k in R and row.get(k):
            p[R[k]] = {"select": {"name": str(row[k])}}
    if "score" in R and row.get("score") is not None:
        p[R["score"]] = {"number": float(row["score"])}
    if "link" in R and row.get("link"):
        p[R["link"]] = {"url": row["link"]}
    if "summary" in R:
        p[R["summary"]] = {"rich_text": rt(row["summary"])}
    if "key" in R:
        p[R["key"]] = {"rich_text": rt(row["key"], 200)}
    return p


def existing_keys(db_id: str, h: dict, key_prop: str | None) -> dict[str, str]:
    if not key_prop:
        return {}
    out: dict[str, str] = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        res = _ok(requests.post(f"{API}/databases/{db_id}/query", headers=h, json=body, timeout=30)).json()
        for pg in res["results"]:
            kp = pg["properties"].get(key_prop)
            if kp and kp.get("type") == "rich_text":
                txt = "".join(x["plain_text"] for x in kp["rich_text"]).strip()
                if txt:
                    out[txt] = pg["id"]
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("date", help="YYYY-MM-DD")
    ap.add_argument("--kind", choices=list(KINDS), help="force one; default = whichever files exist")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows: list[dict] = []
    for k in ([args.kind] if args.kind else list(KINDS)):
        src = ROOT / KINDS[k]["rel"](args.date)
        if not src.exists():
            print(f"  {k}: no {src.name} — skip")
            continue
        data = json.loads(src.read_text(encoding="utf-8"))
        rows += digest_rows(args.date, data, feedback_marks(args.date)) if k == "digest" else news_rows(args.date, data)

    if not rows:
        print("nothing to push")
        return 0

    if args.dry_run:
        for r in rows:
            sc = f"{r['score']}" if r.get("score") is not None else " . "
            print(f"  {r['key']:<48} {r['kind']} {str(r.get('class')):<9} [{sc:>4}] {r['title'][:64]}")
        print(f"\n{len(rows)} rows (dry-run, nothing written)")
        return 0

    h = headers()
    db_id = os.environ.get("NOTION_DB_ID")
    if not db_id:
        sys.exit("NOTION_DB_ID is not set")
    title_name, R = resolve_props(db_id, h)
    seen = existing_keys(db_id, h, R.get("key"))
    print(f"db {db_id[:8]}…  {len(rows)} rows  ({len(seen)} already in DB)")

    created = updated = 0
    for r in rows:
        body = props_for(title_name, R, r)
        page_id = seen.get(r["key"])
        if page_id:
            _ok(requests.patch(f"{API}/pages/{page_id}", headers=h, json={"properties": body}, timeout=30))
            updated += 1
        else:
            _ok(requests.post(f"{API}/pages", headers=h, timeout=30,
                              json={"parent": {"database_id": db_id}, "properties": body}))
            created += 1
        time.sleep(0.34)  # Notion ~3 req/s
    print(f"created {created}, updated {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
