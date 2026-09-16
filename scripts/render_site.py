"""Combine the latest paper digest and the latest policy/market news report into
one HTML page.

Usage:
    python scripts/render_site.py                    # latest of each -> site/<date>.html
    python scripts/render_site.py --date 2026-09-07
    python scripts/render_site.py --embed            # inline images -> site/<date>.embed.html
    python scripts/render_site.py --artifact         # -> site/<date>.artifact.html (rating buttons)
    python scripts/render_site.py --digest digests/2026-09-07.json \
                                 --news news/2026-09-07_policy_news.json

Inputs
    digests/<date>.json            (schema: CLAUDE.md > "Digest JSON schema")
    news/<date>_policy_news.json   (schema: news/_schema.json)
Either input may be missing; that section then renders as "本号は該当なし".

Output
    site/<date>.html          local build. Digest graphical abstracts are referenced
                              at ../digests/assets/<date>/<slug>.<ext> (they live in
                              the digest tree, not copied).
    site/<date>.embed.html    with --embed: every image inlined as a data: URI, so
                              the file is self-contained and can be sent with SendUserFile.
    site/<date>.artifact.html with --artifact: like --embed, plus no <!doctype> wrapper
                              and -/~/+ rating buttons on each paper pick, backed by the
                              `ratings` db collection (doc id <digest-date>__<slug>).
                              Publish with capabilities:{db:{}} — this is the file that
                              goes to the shared Artifact (CLAUDE.md > "The combined Artifact").

<date> for the output filename is the later of the two input dates (weekly digest
vs. daily news), else --date, else today.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import mimetypes
import re
import sys
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent.parent
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
IMG_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


# ---------------------------------------------------------------------------------
# Digest card design system — was shared from render_digest.py; inlined here when
# render_site.py became the single renderer. render_digest.py is retired to 削除/.
# ---------------------------------------------------------------------------------

def slug(doi: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", doi.lower()).strip("-")


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def find_local(asset_dir: Path, doi: str) -> Path | None:
    for p in sorted(asset_dir.glob(f"{slug(doi)}.*")):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return p
    return None


def _data_uri(blob: bytes, ctype: str) -> str:
    return f"data:{ctype};base64,{base64.b64encode(blob).decode()}"


def resolve_image(pick: dict, asset_dir: Path, date: str, download: bool, embed: bool = False) -> str | None:
    doi = pick.get("doi") or pick.get("title", "x")
    local = find_local(asset_dir, doi)
    if local:
        if embed:
            return _data_uri(local.read_bytes(), mimetypes.guess_type(local.name)[0] or "image/png")
        return f"assets/{date}/{local.name}"
    url = pick.get("image")
    if not url:
        return None
    if not download and not embed:
        return url
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").split(";")[0].strip() or "image/png"
        if embed:
            return _data_uri(r.content, ctype)
        ext = IMG_EXT.get(ctype, ".img")
        asset_dir.mkdir(parents=True, exist_ok=True)
        out = asset_dir / f"{slug(doi)}{ext}"
        out.write_bytes(r.content)
        return f"assets/{date}/{out.name}"
    except Exception as exc:  # noqa: BLE001
        print(f"  ! image fetch failed for {doi}: {exc}")
        return url  # fall back to hotlink


CSS = """
:root{--bg:#faf9f7;--card:#fff;--ink:#1a1a1a;--mut:#6b6b6b;--line:#e5e2dc;--accent:#7c4dff;--chip:#f0eef9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Kaku Gothic ProN","Yu Gothic UI",Meiryo,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:32px 20px 80px}
header h1{font-size:22px;margin:0 0 4px}
header .meta{color:var(--mut);font-size:13px}
header .note{margin-top:10px;font-size:13px;background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.intro{margin:20px 0 8px;color:#333}
h2{font-size:15px;letter-spacing:.04em;text-transform:uppercase;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:6px;margin:36px 0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:14px 0;display:grid;grid-template-columns:200px 1fr;gap:16px}
.card.noimg{grid-template-columns:1fr}
.gfx{width:200px}
.gfx img{width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
.body .rank{display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;background:var(--accent);color:#fff;border-radius:6px;font-size:12px;font-weight:700;margin-right:8px}
.body h3{display:inline;font-size:16px;margin:0}
.body h3 a{color:var(--ink);text-decoration:none}
.body h3 a:hover{text-decoration:underline}
.byline{color:var(--mut);font-size:12.5px;margin:8px 0}
.scores{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}
.scores span{font-size:11.5px;background:var(--chip);border-radius:999px;padding:2px 9px;color:#444}
.scores .final{background:var(--accent);color:#fff;font-weight:700}
.summary{margin:8px 0 0}
.caveat{margin:8px 0 0;font-size:13px;color:var(--mut);border-left:3px solid var(--line);padding-left:10px}
.wl{margin:8px 0;padding:10px 0;border-bottom:1px solid var(--line)}
.wl a{color:var(--ink)}
.wl .j{color:var(--mut);font-size:12.5px}
.wl .n{display:block;color:#444;font-size:13px;margin-top:3px}
.dropped{color:var(--mut);font-size:13px}
footer{margin-top:50px;color:var(--mut);font-size:12px;text-align:center}
@media (max-width:600px){.card{grid-template-columns:1fr}.gfx{width:100%;max-width:260px}}
@media (prefers-color-scheme:dark){
:root{--bg:#151516;--card:#1e1e20;--ink:#e9e7e3;--mut:#9a968e;--line:#33322f;--accent:#9a7bff;--chip:#26243a}
.gfx img{background:#fff}
}
"""

RATING_CSS = """
#fb-banner{position:sticky;top:0;z-index:5;background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13px;margin-bottom:8px}
#fb-status{color:var(--mut);font-size:12px;margin-left:8px}
.fb-row{display:flex;align-items:center;gap:8px;margin-top:12px;flex-wrap:wrap}
.fb-btn{border:1px solid var(--line);background:var(--card);color:var(--ink);width:34px;height:30px;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;line-height:1}
.fb-btn:hover{border-color:var(--accent)}
.fb-btn[aria-pressed=true][data-mark="+"]{background:#1e9e5a;border-color:#1e9e5a;color:#fff}
.fb-btn[aria-pressed=true][data-mark="~"]{background:#c98a17;border-color:#c98a17;color:#fff}
.fb-btn[aria-pressed=true][data-mark="-"]{background:#c0392b;border-color:#c0392b;color:#fff}
.fb-btn:disabled{opacity:.4;cursor:not-allowed}
.fb-note{flex:1;min-width:160px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:5px 9px;font:inherit;font-size:13px}
"""

RATING_JS = r"""
(function(){
  var DATE = "%DATE%";
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card[data-slug]"));
  var banner = document.getElementById("fb-banner");
  var statusEl = document.getElementById("fb-status");
  var col = null, debouncers = new WeakMap();

  function paint(card){
    var m = card.dataset.mark && card.dataset.mark !== "?" ? card.dataset.mark : "";
    card.querySelectorAll(".fb-btn").forEach(function(b){
      b.setAttribute("aria-pressed", String(b.dataset.mark === m));
    });
  }
  function refreshStatus(){
    var n = cards.filter(function(c){ return c.dataset.mark && c.dataset.mark !== "?"; }).length;
    if (statusEl) statusEl.textContent = "評価済み " + n + " / " + cards.length;
  }
  function bodyFor(card){
    var note = card.querySelector(".fb-note");
    return {
      date: DATE, slug: card.dataset.slug, doi: card.dataset.doi,
      title: card.dataset.title, journal_short: card.dataset.journal,
      score: card.dataset.score ? Number(card.dataset.score) : null,
      mark: (card.dataset.mark && card.dataset.mark !== "?") ? card.dataset.mark : "",
      note: note ? note.value : "",
      updated: new Date().toISOString()
    };
  }
  function save(card){
    if (!col) return;
    col.doc(DATE + "__" + card.dataset.slug).set(bodyFor(card)).catch(function(e){
      banner.textContent = "保存に失敗しました (" + (e && e.code || e) + ") — もう一度お試しください。";
    });
  }
  function wire(){
    cards.forEach(function(card){
      card.querySelectorAll(".fb-btn").forEach(function(btn){
        btn.disabled = false;
        btn.addEventListener("click", function(){
          card.dataset.mark = (card.dataset.mark === btn.dataset.mark) ? "?" : btn.dataset.mark;
          paint(card); refreshStatus(); save(card);
        });
      });
      var note = card.querySelector(".fb-note");
      if (note){
        note.disabled = false;
        note.addEventListener("input", function(){
          clearTimeout(debouncers.get(note));
          debouncers.set(note, setTimeout(function(){ save(card); }, 600));
        });
      }
    });
  }
  function offline(msg){ if (banner) banner.textContent = msg; }

  if (!(window.claude && window.claude.use)){
    offline("⚠ claude.ai の Artifact 版で開くと評価ボタンが有効になります(このファイルはローカル版)。");
    return;
  }
  window.claude.use("db").then(function(db){
    if (!db){
      offline("⚠ この表示では保存できません。claude.ai 上の Artifact で操作してください。");
      return;
    }
    col = db.collection("ratings");
    col.where("date", "==", DATE).onSnapshot(function(snap){
      snap.docs.forEach(function(d){
        var v = d.data(); if (!v || !v.slug) return;
        var card = document.querySelector('.card[data-slug="' + v.slug + '"]');
        if (!card) return;
        card.dataset.mark = v.mark || "?";
        paint(card);
        var note = card.querySelector(".fb-note");
        if (note && document.activeElement !== note) note.value = v.note || "";
      });
      refreshStatus();
    }, function(err){ console.warn("ratings snapshot", err); });
    wire();
    refreshStatus();
  });
})();
"""

EXTRA_CSS = """
.nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 0;margin:0 0 4px;z-index:10;display:flex;gap:16px;font-size:13px}
.nav a{color:var(--mut);text-decoration:none}
.nav a:hover{color:var(--ink)}
.section-head{font-size:19px;margin:44px 0 2px;padding-top:8px;border-top:2px solid var(--line)}
.section-sub{color:var(--mut);font-size:13px;margin:4px 0 8px}
.banner{background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:12.5px;color:#555;margin:10px 0}
.tier{font-size:13px;letter-spacing:.04em;text-transform:uppercase;color:var(--mut);border-bottom:1px solid var(--line);padding-bottom:5px;margin:26px 0 12px}
.nitem{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;background:var(--card)}
.nitem h4{margin:0;font-size:15px;line-height:1.5}
.nitem h4 a{color:var(--ink);text-decoration:none}
.nitem h4 a:hover{text-decoration:underline}
.nitem .meta{color:var(--mut);font-size:12px;margin:6px 0 0}
.nitem p{margin:8px 0 0;font-size:13.5px}
.nitem .angle{border-left:3px solid var(--line);padding-left:10px;color:#444}
.badge{display:inline-block;font-size:10.5px;padding:1px 8px;border-radius:999px;background:var(--chip);color:#555;margin-left:6px;vertical-align:middle;white-space:nowrap}
.badge.t1{background:#e6f0ff;color:#274690}
.badge.t2{background:#e7f6ea;color:#1f6b39}
.cov{width:100%;border-collapse:collapse;font-size:12.5px;margin:10px 0}
.cov td{border-top:1px solid var(--line);padding:6px 8px;vertical-align:top}
.cov td:first-child{white-space:nowrap;color:var(--mut)}
@media (prefers-color-scheme:dark){
.badge.t1{background:#22314c;color:#aac4f0}
.badge.t2{background:#1f3a29;color:#9fd8b2}
}
"""

# --artifact only: RATING_CSS pins #fb-banner sticky at top, but this page already
# has a sticky .nav there — keep the banner inside the papers section instead.
ARTIFACT_CSS_OVERRIDE = "#fb-banner{position:static;margin:12px 0 0}"


# ---------------------------------------------------------------- paper digest --

def _digest_card(p: dict, asset_dir: Path, download: bool, embed: bool,
                 artifact: bool = False) -> str:
    img = resolve_image(p, asset_dir, p.get("_date", ""), download, embed)
    if img and not embed and img.startswith("assets/"):
        img = "../digests/" + img  # site/<date>.html -> ../digests/assets/<date>/..
    gfx = (f"<div class='gfx'><a href='{esc(p.get('url'))}'>"
           f"<img src='{esc(img)}' alt='graphical abstract' loading='lazy'></a></div>"
           if img else "")
    sc = []
    if "score" in p:
        sc.append(f"<span class='final'>総合 {p['score']}</span>")
    for key, lab in (("relevance", "関連"), ("novelty", "新規"), ("topicality", "話題")):
        if key in p:
            sc.append(f"<span>{lab} {p[key]}</span>")
    byline = " · ".join(x for x in [
        f"<b>{esc(p.get('journal_short'))}</b>", esc(p.get("authors")),
        esc(p.get("published")),
        f"<a href='{esc(p.get('url'))}'>{esc(p.get('doi'))}</a>" if p.get("doi") else "",
    ] if x and x != "<b></b>")
    # --artifact: rating hooks per card, writing to the `ratings` db collection
    # (doc id <digest-date>__<slug>) via RATING_JS below.
    data_attrs = fb_row = ""
    if artifact:
        data_attrs = (f" data-slug=\"{esc(slug(p.get('doi') or p.get('title', '')))}\""
                      f" data-doi=\"{esc(p.get('doi'))}\" data-journal=\"{esc(p.get('journal_short'))}\""
                      f" data-score=\"{esc(p.get('score', ''))}\" data-title=\"{esc(p.get('title'))}\""
                      f" data-mark=\"?\"")
        btns = "".join(f"<button class='fb-btn' data-mark='{m}' aria-pressed='false' disabled>{m}</button>"
                       for m in ("-", "~", "+"))
        fb_row = (f"<div class='fb-row'>{btns}"
                  f"<input class='fb-note' type='text' placeholder='メモ(任意)' disabled></div>")
    body = [f"<div class='body'><span class='rank'>{esc(p.get('rank', ''))}</span>"
            f"<h3><a href='{esc(p.get('url'))}'>{esc(p.get('title'))}</a></h3>"
            f"<div class='byline'>{byline}</div>"
            f"<div class='scores'>{''.join(sc)}</div>"
            f"<p class='summary'>{esc(p.get('summary_ja'))}</p>"]
    if p.get("caveat_ja"):
        body.append(f"<p class='caveat'>{esc(p['caveat_ja'])}</p>")
    body.append(fb_row)
    body.append("</div>")
    return f"<div class='{'card' if img else 'card noimg'}'{data_attrs}>{gfx}{''.join(body)}</div>"


def digest_section(data: dict, download: bool, embed: bool, artifact: bool = False) -> str:
    date = data.get("date", "")
    asset_dir = ROOT / "digests" / "assets" / date
    st = data.get("stats", {})
    stat_line = " · ".join(x for x in [
        f"{st['journals']}誌" if "journals" in st else "",
        f"新着{st['new']}件" if "new" in st else "",
        f"採点{st['scored']}件" if "scored" in st else "",
        f"掲載{len(data.get('picks', []))}件",
    ] if x)
    parts = [f"<h2 class='section-head' id='papers'>論文ダイジェスト</h2>",
             f"<p class='section-sub'>{esc(date)} · 週次 · {esc(stat_line)}</p>"]
    if artifact:
        parts.append("<div id='fb-banner'>各採用論文を下の <b>− / ~ / +</b> ボタンで評価してください。"
                     "claude.ai に保存され、次回のチューニングに自動反映されます。"
                     "<span id='fb-status'></span></div>")
    if data.get("intro_ja"):
        parts.append(f"<p class='intro'>{esc(data['intro_ja'])}</p>")
    parts.append("<h3 class='tier'>Picks</h3>")
    for p in data.get("picks", []):
        p = {**p, "_date": date}
        parts.append(_digest_card(p, asset_dir, download, embed, artifact))
    if data.get("watchlist"):
        parts.append("<h3 class='tier'>Watchlist</h3>")
        for w in data["watchlist"]:
            parts.append(
                f"<div class='wl'><a href='{esc(w.get('url'))}'>{esc(w.get('title'))}</a> "
                f"<span class='j'>— {esc(w.get('journal_short'))} · {esc(w.get('doi'))}</span>"
                f"<span class='n'>{esc(w.get('note_ja'))}</span></div>")
    if data.get("dropped_ja"):
        parts.append(f"<h3 class='tier'>Dropped</h3><p class='dropped'>{esc(data['dropped_ja'])}</p>")
    return "".join(parts)


# ------------------------------------------------------------ policy/market news --

CONF_LABEL = {
    "primary": "一次資料本文まで確認",
    "headline": "会議開催情報・見出し／検索レベル（一次PDF未読）",
}


def news_section(data: dict) -> str:
    date = data.get("date", "")
    st = data.get("stats", {})
    stat_line = " · ".join(x for x in [
        f"ソース{st['sources_checked']}" if "sources_checked" in st else "",
        f"新規{st['new']}" if "new" in st else "",
        f"本筋{st['main']}" if "main" in st else "",
        f"裾野{st['fringe']}" if "fringe" in st else "",
    ] if x)
    parts = [f"<h2 class='section-head' id='news'>政策・市場ニュース</h2>",
             f"<p class='section-sub'>{esc(date)} · 日次 · {esc(stat_line)}</p>"]
    cl = data.get("confirmation_level")
    cl_txt = CONF_LABEL.get(cl, cl)
    if cl_txt:
        parts.append(f"<div class='banner'>確認レベル: {esc(cl_txt)}</div>")
    if data.get("intro_ja"):
        parts.append(f"<p class='intro'>{esc(data['intro_ja'])}</p>")

    for key, label in (("main", "本筋"), ("fringe", "裾野・要ご判断")):
        items = [it for it in data.get("items", []) if it.get("tier") == key]
        if not items:
            continue
        parts.append(f"<h3 class='tier'>{esc(label)}</h3>")
        for it in items:
            th = it.get("theme")
            badge = f"<span class='badge t{th}'>テーマ{th}</span>" if th in (1, 2) else ""
            title = esc(it.get("title_ja"))
            if it.get("url"):
                title = f"<a href='{esc(it['url'])}'>{title}</a>"
            meta = " · ".join(x for x in [
                esc(it.get("source_short")), esc(it.get("published")),
                f"<a href='{esc(it.get('url'))}'>出典</a>" if it.get("url") else "",
                f"ローカル保存: {esc(it['local_file'])}" if it.get("local_file") else "",
            ] if x)
            parts.append("<div class='nitem'>")
            parts.append(f"<h4>{esc(it.get('id', ''))}. {title}{badge}</h4>")
            if meta:
                parts.append(f"<div class='meta'>{meta}</div>")
            if it.get("summary_ja"):
                parts.append(f"<p>{esc(it['summary_ja'])}</p>")
            if it.get("polymer_angle_ja"):
                parts.append(f"<p class='angle'>高分子アングル: {esc(it['polymer_angle_ja'])}</p>")
            parts.append("</div>")

    if data.get("source_coverage"):
        parts.append("<h3 class='tier'>ソース別確認結果</h3><table class='cov'>")
        for c in data["source_coverage"]:
            parts.append(f"<tr><td>{esc(c.get('source_short'))}</td>"
                         f"<td>{esc(c.get('result_ja'))}</td></tr>")
        parts.append("</table>")
    if data.get("dropped_ja"):
        parts.append(f"<h3 class='tier'>除外</h3><p class='dropped'>{esc(data['dropped_ja'])}</p>")
    return "".join(parts)


# ---------------------------------------------------------------------- assembly --

def render_page(digest: dict | None, news: dict | None, out_date: str,
                download: bool, embed: bool, artifact: bool = False) -> str:
    if artifact:
        embed = True  # publisher image hosts are not on the Artifact CSP allowlist
    style = CSS + EXTRA_CSS + (RATING_CSS + ARTIFACT_CSS_OVERRIDE if artifact else "")
    if artifact:
        # no <!doctype>/<html>/<head>/<body> — the Artifact tool wraps it. Stable
        # <title> so the Artifact keeps one identity across weeks; date is in the H1.
        parts = [f"<title>材料インテリジェンス</title><style>{style}</style><div class='wrap'>"]
    else:
        parts = ["<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
                 "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                 f"<title>材料インテリジェンス {esc(out_date)}</title>"
                 f"<style>{style}</style></head><body><div class='wrap'>"]
    parts.append(
        f"<header><h1>材料インテリジェンス — {esc(out_date)}</h1>"
        f"<div class='meta'>論文ダイジェスト（週次） ＋ 政策・市場ニュース（日次）</div></header>"
    )
    nav = []
    if digest:
        nav.append("<a href='#papers'>論文</a>")
    if news:
        nav.append("<a href='#news'>政策・市場ニュース</a>")
    if nav:
        parts.append(f"<div class='nav'>{''.join(nav)}</div>")

    if digest:
        parts.append(digest_section(digest, download, embed, artifact))
    else:
        parts.append("<h2 class='section-head' id='papers'>論文ダイジェスト</h2>"
                     "<p class='section-sub'>本号は該当なし</p>")
    if news:
        parts.append(news_section(news))
    else:
        parts.append("<h2 class='section-head' id='news'>政策・市場ニュース</h2>"
                     "<p class='section-sub'>本号は該当なし</p>")

    parts.append(f"<footer>generated {dt.date.today().isoformat()} · journal-research</footer></div>")
    if artifact and digest:
        # rating buttons write to db collection `ratings`, keyed by the DIGEST's
        # date (not out_date) so merge_ratings.py <digest-date> still finds them.
        parts.append(f"<script>{RATING_JS.replace('%DATE%', digest['date'])}</script>")
    elif not artifact:
        parts.append("</body></html>")
    return "".join(parts)


def _latest(paths: list[Path]) -> Path | None:
    dated = sorted(p for p in paths if DATE_RE.search(p.name))
    return dated[-1] if dated else None


def _resolve_digest(args) -> Path | None:
    if args.digest:
        return Path(args.digest).resolve()
    if args.date:
        p = ROOT / "digests" / f"{args.date}.json"
        return p if p.exists() else None
    return _latest(list((ROOT / "digests").glob("*.json")))


def _resolve_news(args) -> Path | None:
    if args.news:
        return Path(args.news).resolve()
    if args.date:
        p = ROOT / "news" / f"{args.date}_policy_news.json"
        return p if p.exists() else None
    return _latest(list((ROOT / "news").glob("*_policy_news.json")))


def _date_of(path: Path | None) -> str | None:
    if not path:
        return None
    m = DATE_RE.search(path.name)
    return m.group(0) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="YYYY-MM-DD; use that date's digest + news file")
    ap.add_argument("--digest", help="explicit path to a digests/<date>.json")
    ap.add_argument("--news", help="explicit path to a news/<date>_policy_news.json")
    ap.add_argument("--embed", action="store_true",
                    help="inline every image as a data: URI -> one self-contained file")
    ap.add_argument("--artifact", action="store_true",
                    help="emit Artifact HTML (no doctype wrapper, images inlined) with the "
                         "digest's +/-/~ rating buttons on each paper pick, backed by the "
                         "same `ratings` db collection. Publish with capabilities:{db:{}}.")
    ap.add_argument("--no-download", action="store_true",
                    help="hotlink remote digest images instead of saving them")
    args = ap.parse_args()

    dpath = _resolve_digest(args)
    npath = _resolve_news(args)
    for flag, p in (("--digest", dpath if args.digest else None),
                    ("--news", npath if args.news else None)):
        if p and not p.exists():
            print(f"{flag} path not found: {p}", file=sys.stderr)
            return 1
    if not (dpath and dpath.exists()) and not (npath and npath.exists()):
        print("nothing to render: no digest and no news file found", file=sys.stderr)
        return 1

    digest = json.loads(dpath.read_text(encoding="utf-8")) if dpath else None
    news = json.loads(npath.read_text(encoding="utf-8")) if npath else None

    dates = [d for d in (_date_of(dpath), _date_of(npath)) if d]
    out_date = args.date or (max(dates) if dates else dt.date.today().isoformat())

    site_dir = ROOT / "site"
    site_dir.mkdir(exist_ok=True)
    tag = ".artifact.html" if args.artifact else (".embed.html" if args.embed else ".html")
    out = site_dir / f"{out_date}{tag}"
    out.write_text(
        render_page(digest, news, out_date, download=not args.no_download,
                    embed=args.embed, artifact=args.artifact),
        encoding="utf-8")

    def _rel(p: Path | None) -> str:
        if not p:
            return "—"
        try:
            return str(p.relative_to(ROOT))
        except ValueError:
            return str(p)

    print(f"wrote {_rel(out)}")
    print(f"  digest: {_rel(dpath)}  |  picks {len(digest['picks']) if digest else 0}")
    print(f"  news:   {_rel(npath)}  |  items {len(news['items']) if news else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
