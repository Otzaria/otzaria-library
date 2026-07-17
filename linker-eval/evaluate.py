#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
evaluate.py — Stage 2 of the commentary-linker evaluation harness.

Runs the branch-26 deterministic matcher (linker/dibur_matcher.py) against the
gold set built in stage 1 and produces the numerical BASELINE the project was
missing: how well does the matcher reproduce Sefaria's human links?

Run mode
--------
The matcher is called as a library (no file I/O, no "refuse on unresolved" gate)
with intermediate_books={} and heref_lookup={}. Consequences, both intentional:

  * No intermediate books  ->  every comment line (including "בתוספות ד\"ה ..."
    super-openers) is matched against the BASE text. Sefaria's gold also points
    super-openers at the base Gemara line, so this mode is DIRECTLY comparable to
    gold on every line, and it measures the matcher's core skill: "given a dibbur,
    find the right base line." (The production matcher, with intermediate books,
    reroutes super-openers to the Rashi/Tosafot book — not comparable to this gold;
    that is scored separately via the is_super breakdown below.)
  * Empty heref dump  ->  heRef_2 is synthesized, but we never score heRef here;
    only line_index_2 matters, and that is unaffected.

Metric
------
hit@set: a comment line is a HIT if the matcher's chosen base line (or its
[start..end] range, for range links) intersects the gold target SET for that line.
Reported two ways:
  * of-predicted : hits / (hits + misses)     -> "when it commits, is it right?"
  * of-gold      : hits / all-gold-lines      -> "of all human answers reproduced"
Broken down by: overall / non-super / super / single-target / multi-target.

low-confidence diagnostic
-------------------------
The matcher already flags uncertain matches (result.low_confidence). We cross this
with correctness to answer the load-bearing design question for stage 3: if we sent
ONLY the flagged lines to an LLM adjudicator, how many of the real errors would we
catch, and how much work would that be? (recall of misses among flagged lines, and
the flagged fraction of the book.)
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "matcher_b26"))
from dibur_matcher import match_citing_book  # noqa: E402

# Curated suite spanning difficulty (see REPORT.md). All version-aligned and
# daf-structured. Use --all for the full 135-book aligned population.
DEFAULT_SUITE = [
    "תוספות על ראש השנה",            # structural rishon — the floor
    "חידושי חתם סופר על בבא מציעא",  # clean acharon
    "ערוך לנר על ראש השנה",          # branch-26's book (same author/style)
    "רבינו חננאל על בבא קמא",        # paraphrase-style rishon (harder)
    "פני יהושע על בבא קמא",          # hard acharon (manually verified gold)
    "הפלאה על כתובות",               # hard acharon, many-to-many heavy
    "חדושי הלכות על בבא מציעא",      # מהרש"א — hardest of the suite
]


def pct(n, d):
    return f"{100*n/d:5.1f}%" if d else "  n/a"


def eval_book(gold_path, repo_root):
    g = json.load(open(gold_path, encoding="utf-8"))
    citing = os.path.join(repo_root, g["commentary_txt"])
    base = os.path.join(repo_root, g["base_txt"])
    res = match_citing_book(citing, g["base_title"], base, {}, {})

    pred = {}      # line_index_1 -> set(covered base lines)
    for e in res.entries:
        s = e["line_index_2"]
        end = e.get("line_index_2_end", s)
        pred[e["line_index_1"]] = set(range(min(s, end), max(s, end) + 1))
    low_conf = {idx for idx, _ in res.low_confidence}

    # segments: (name, predicate on gold entry v)
    segs = {
        "overall": lambda v: True,
        "non_super": lambda v: not v["is_super"],
        "super": lambda v: v["is_super"],
        "single": lambda v: len(v["targets"]) == 1,
        "multi": lambda v: len(v["targets"]) > 1,
    }
    stat = {k: {"hit": 0, "miss": 0, "nopred": 0} for k in segs}
    # miss/hit vs low-confidence flag (overall only)
    flagged_miss = flagged_hit = 0
    total_miss = 0

    for li_s, v in g["gold"].items():
        li = int(li_s)
        tset = set(v["targets"])
        if li not in pred:
            outcome = "nopred"
        elif tset & pred[li]:
            outcome = "hit"
        else:
            outcome = "miss"
        for name, ok in segs.items():
            if ok(v):
                stat[name][outcome] += 1
        if outcome == "miss":
            total_miss += 1
            if li in low_conf:
                flagged_miss += 1
        elif outcome == "hit" and li in low_conf:
            flagged_hit += 1

    return {
        "title": g["commentary_title"],
        "base": g["base_title"],
        "gold_lines": g["gold_lines"],
        "super_pct": round(100 * g["super_commentary_lines"] / g["gold_lines"], 1),
        "entries": len(res.entries),
        "unresolved": len(res.unresolved),
        "low_conf": len(low_conf),
        "seg": stat,
        "flagged_miss": flagged_miss,
        "flagged_hit": flagged_hit,
        "total_miss": total_miss,
    }


def hitrate(s, mode):
    h, m, n = s["hit"], s["miss"], s["nopred"]
    if mode == "predicted":
        return h, (h + m)
    return h, (h + m + n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(HERE, "truth"))
    ap.add_argument("--repo", default=os.path.join(HERE, ".."))
    ap.add_argument("--all", action="store_true", help="evaluate every runnable gold book")
    ap.add_argument("--out", default=os.path.join(HERE, "baseline.json"))
    args = ap.parse_args()

    if args.all:
        titles = [f[:-len(".gold.json")] for f in sorted(os.listdir(args.truth))
                  if f.endswith(".gold.json")]
    else:
        titles = DEFAULT_SUITE

    results = []
    for t in titles:
        gp = os.path.join(args.truth, t + ".gold.json")
        if not os.path.exists(gp):
            print(f"[skip] no gold file: {t}", file=sys.stderr)
            continue
        try:
            g = json.load(open(gp, encoding="utf-8"))
            if not g.get("aligned"):
                # on-disk .txt version differs from the DB the gold was built from;
                # its indices would score as noise. Excluded from the baseline.
                print(f"[skip] version-misaligned: {t} ({g.get('alignment_reason')})",
                      file=sys.stderr)
                continue
            results.append(eval_book(gp, args.repo))
        except Exception as exc:  # noqa: BLE001
            print(f"[err] {t}: {exc}", file=sys.stderr)

    # ---- per-book table ----
    print(f"\n{'book':38} {'gold':>5} {'sup%':>5} {'overall':>8} {'non-sup':>8} {'super':>7} "
          f"{'multi':>7} {'flag→miss':>10}")
    print("-" * 100)
    agg = {k: {"hit": 0, "miss": 0, "nopred": 0} for k in
           ("overall", "non_super", "super", "single", "multi")}
    agg_fm = agg_fh = agg_tm = 0
    for r in results:
        def show(seg):
            h, d = hitrate(r["seg"][seg], "predicted")
            return pct(h, d)
        fm = f"{r['flagged_miss']}/{r['total_miss']}"
        print(f"{r['title'][:38]:38} {r['gold_lines']:5} {r['super_pct']:4.0f}% "
              f"{show('overall'):>8} {show('non_super'):>8} {show('super'):>7} "
              f"{show('multi'):>7} {fm:>10}")
        for k in agg:
            for o in ("hit", "miss", "nopred"):
                agg[k][o] += r["seg"][k][o]
        agg_fm += r["flagged_miss"]; agg_fh += r["flagged_hit"]; agg_tm += r["total_miss"]

    # ---- aggregate ----
    print("-" * 100)
    print("AGGREGATE (of-predicted hit@set):")
    for k in ("overall", "non_super", "super", "single", "multi"):
        h, d = hitrate(agg[k], "predicted")
        h2, d2 = hitrate(agg[k], "gold")
        print(f"  {k:12} predicted={pct(h,d)} ({h}/{d})   of-gold={pct(h2,d2)} ({h2}/{d2})")
    print(f"\nLOW-CONFIDENCE DIAGNOSTIC (for stage-3 LLM triage):")
    print(f"  misses caught by matcher's own low-conf flag: {pct(agg_fm,agg_tm)} ({agg_fm}/{agg_tm})")
    total_gold = sum(r["gold_lines"] for r in results)
    total_flag = sum(r["low_conf"] for r in results)
    print(f"  flagged lines as share of all gold lines:     {pct(total_flag,total_gold)} "
          f"({total_flag}/{total_gold})")
    print(f"  flagged-but-actually-correct (false alarms):  {agg_fh}")

    json.dump(
        {"results": results,
         "aggregate": {k: agg[k] for k in agg},
         "low_conf": {"flagged_miss": agg_fm, "total_miss": agg_tm,
                      "flagged_hit": agg_fh, "flagged_lines": total_flag,
                      "total_gold": total_gold}},
        open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
