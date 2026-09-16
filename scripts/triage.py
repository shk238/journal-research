"""Cheap keyword triage over a raw file — narrows ~1000 items to a shortlist
the model then scores properly against config/scoring.md.

Usage:
    python scripts/triage.py data/raw/2026-09-07.json            # -> data/raw/2026-09-07.shortlist.json
    python scripts/triage.py data/raw/2026-09-07.json --top 200

This is a coarse pre-filter, not the scorer. It ranks by substring hits on an
expanded polymer lexicon (title weighted 2x over abstract), subtracts for
exclude terms, and adds a small bump for polymer-first journals. The model
still applies the real Relevance/Novelty/Topicality rubric to the survivors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORE = [
    r"\bpolymer", r"\bcopolymer", r"polymeriz", r"polymerisa", r"macromolecul",
    r"\bRAFT\b", r"\bATRP\b", r"\bNMP\b", r"\bROMP\b", r"\bROP\b", r"ring-opening",
    r"chain[- ]growth", r"step[- ]growth", r"\bmonomer", r"\bmacromonomer",
    r"block copolymer", r"\bbCP\b", r"microphase", r"self-assembl",
    r"\bhydrogel", r"\borganogel", r"\bionogel", r"\bgel\b", r"\bnetwork\b", r"crosslink", r"cross-link",
    r"\bvitrimer", r"covalent adaptable", r"\bCAN\b", r"dynamic covalent", r"\bdynamer",
    r"self-healing", r"reprocess", r"recyclable", r"depolymeriz", r"chemical recycling",
    r"conjugated polymer", r"semiconducting polymer", r"\bOFET\b", r"\bOPV\b", r"\bOLED\b",
    r"polymer electrolyte", r"\bSPE\b", r"ion-conduct", r"single-ion",
    r"stimuli-responsive", r"\bLCST\b", r"\bUCST\b", r"thermoresponsive", r"shape memory",
    r"sequence-controlled", r"sequence-defined", r"precision polymer",
    r"\brheolog", r"viscoelastic", r"glass transition", r"\bTg\b", r"entangle", r"reptation",
    r"single-chain nanoparticle", r"\bSCNP\b", r"bottlebrush", r"\bstar polymer",
    r"\bmiktoarm", r"\bdendrimer", r"topological polymer", r"cyclic polymer",
    r"\belastomer", r"\bthermoplastic", r"\bthermoset", r"\blatex\b",
    r"\bPEG\b", r"\bPEO\b", r"\bPLA\b", r"\bPCL\b", r"\bPDMS\b", r"\bPMMA\b", r"\bPS-b-",
    r"polyurethane", r"polyester", r"polyamide", r"polyolefin", r"polycarbonate",
    r"polypeptide", r"polypeptoid", r"polyelectrolyte", r"coacervat",
    r"living polymeriz", r"controlled radical", r"\bRDRP\b",
]
ADJACENT = [
    r"bio-based", r"biobased", r"renewable feedstock", r"\bCO2\b.*polym", r"lignin", r"\bPHA\b",
    r"supramolecular", r"host-guest", r"hydrogen[- ]bond", r"\bmetallosupramolecul",
    r"\bmembrane", r"gas separation", r"nanofiltration", r"pervaporation",
    r"organic solar", r"photovoltaic", r"\bnon-fullerene", r"charge transport",
    r"nanocomposite", r"\bfiller\b", r"interphase", r"\bnanofiller",
    r"machine learning", r"\bML\b", r"high-throughput", r"generative model", r"inverse design",
    r"3D print", r"additive manufactur", r"\bDLP\b", r"vat photopolymer", r"direct ink writing",
    r"\bmicelle", r"\bvesicle", r"\bPISA\b", r"nanoparticle assembl",
]
EXCLUDE = [
    r"drug delivery", r"tumou?r", r"\bcancer\b", r"anticancer", r"chemotherap",
    r"\bin vivo\b", r"\bmice\b", r"\bmurine\b", r"antibacterial", r"antimicrobial",
    r"\bantibody", r"\bvaccine", r"wound healing", r"tissue engineer", r"bone regenerat",
    r"biosensor for detection of", r"clinical",
]
POLYMER_JOURNALS = {
    "Macromolecules", "ACS Macro Lett.", "Polym. Chem. (RSC)", "Polymer",
    "Eur. Polym. J.", "Prog. Polym. Sci.", "Giant", "Polym. J.",
    "Polym. Degrad. Stab.", "React. Funct. Polym.", "Soft Matter",
}

core_re = [re.compile(p, re.I) for p in CORE]
adj_re = [re.compile(p, re.I) for p in ADJACENT]
exc_re = [re.compile(p, re.I) for p in EXCLUDE]


def hits(patterns, text):
    return [p.pattern for p in patterns if p.search(text)]


def score_item(it: dict) -> dict:
    title = it.get("title", "")
    abstract = it.get("abstract", "")
    c_t, c_a = hits(core_re, title), hits(core_re, abstract)
    a_t, a_a = hits(adj_re, title), hits(adj_re, abstract)
    e_all = set(hits(exc_re, title)) | set(hits(exc_re, abstract))

    raw = 2.0 * len(set(c_t)) + 1.0 * len(set(c_a)) + 1.0 * len(set(a_t)) + 0.5 * len(set(a_a))
    if it.get("journal_short") in POLYMER_JOURNALS:
        raw += 1.5
    raw -= 2.5 * len(e_all)
    # exclude with no core support at all -> hard drop
    hard_drop = bool(e_all) and not (c_t or c_a)

    return {
        "triage_score": round(raw, 2),
        "core_hits": sorted(set(c_t) | set(c_a)),
        "adjacent_hits": sorted(set(a_t) | set(a_a)),
        "exclude_hits": sorted(e_all),
        "hard_drop": hard_drop,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw", help="path to data/raw/<date>.json")
    ap.add_argument("--top", type=int, default=180, help="how many to keep in the shortlist")
    args = ap.parse_args()

    path = Path(args.raw)
    items = json.loads(path.read_text(encoding="utf-8"))
    for it in items:
        it["triage"] = score_item(it)

    kept = [it for it in items if not it["triage"]["hard_drop"]]
    kept.sort(key=lambda it: it["triage"]["triage_score"], reverse=True)
    shortlist = kept[: args.top]

    out = path.with_suffix(".shortlist.json")
    out.write_text(json.dumps(shortlist, ensure_ascii=False, indent=2), encoding="utf-8")

    n_hard = sum(1 for it in items if it["triage"]["hard_drop"])
    below = len(kept) - len(shortlist)
    cutoff = shortlist[-1]["triage"]["triage_score"] if shortlist else 0
    print(f"{len(items)} items")
    print(f"  hard-dropped (exclude, no core): {n_hard}")
    print(f"  ranked survivors:               {len(kept)}")
    print(f"  shortlist written:              {len(shortlist)}  (score >= {cutoff})")
    print(f"  left below shortlist:           {below}")
    print(f"-> {out}")

    by_j: dict[str, int] = {}
    for it in shortlist:
        by_j[it["journal_short"]] = by_j.get(it["journal_short"], 0) + 1
    print("\nshortlist by journal:")
    for j, n in sorted(by_j.items(), key=lambda x: -x[1]):
        print(f"  {n:>3}  {j}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
