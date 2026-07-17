#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
oracle_ceiling.py — stage 3, step 0: is an LLM adjudicator even worth building?

The planned day-adjudicator lets an LLM PICK among the matcher's candidates for
a comment line; it never searches raw text. So the best it could ever do is
capped by whether the correct (gold) base line is IN the matcher's candidate
window at all. That window, in the no-intermediate run mode, is exactly the base
lines under the same daf_key as the comment line (the matcher parses both books
and buckets by <h2> daf; see build_daf_index).

This script decomposes every gold comment line into three buckets:

  * hit           — matcher's argmax already lands on a gold line. Nothing to do.
  * recoverable   — gold IS in the daf window but the matcher's argmax missed it.
                    THIS is the adjudicator's entire opportunity: a better pick
                    from the same candidates would fix it.
  * unreachable   — gold is NOT in the daf window. No selection-stage LLM can fix
                    this; the fault is upstream (daf tracking / windowing / the
                    comment quotes a different daf than its heading). Needs a
                    different fix, not an adjudicator.

oracle_ceiling = (hit + recoverable) / gold  == the hit@set an adjudicator would
reach if it picked perfectly. The gap (ceiling - current) is the real headroom.
If 'unreachable' dominates, stop — build window/daf fixes, not an LLM.

It also reports, for recoverable lines, the matcher's score margin (best -
runner_up among the *gold-containing* window), to design the triage signal:
recoverable lines with a SMALL margin are where the LLM has the clearest opening.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "matcher_b26"))
from dibur_matcher import (  # noqa: E402
    match_citing_book, parse_book, build_daf_index, score_candidate,
)

ACHARON_ONLY = True  # the 49.8% gap; rishonim are already ~72%


def analyze(gold_path, repo_root):
    g = json.load(open(gold_path, encoding="utf-8"))
    citing = os.path.join(repo_root, g["commentary_txt"])
    base = os.path.join(repo_root, g["base_txt"])

    comm_lines = {ln.line_index: ln for ln in parse_book(citing)}
    base_lines = parse_book(base)
    base_daf = build_daf_index(base_lines)          # daf_key -> [Line]
    base_by_idx = {ln.line_index: ln for ln in base_lines}

    res = match_citing_book(citing, g["base_title"], base, {}, {})
    pred = {}
    for e in res.entries:
        s = e["line_index_2"]
        end = e.get("line_index_2_end", s)
        pred[e["line_index_1"]] = set(range(min(s, end), max(s, end) + 1))

    buckets = {"hit": 0, "recoverable": 0, "unreachable": 0, "nopred": 0}
    recov_small_margin = 0   # recoverable AND matcher margin < 30 (weak pick)
    for li_s, v in g["gold"].items():
        li = int(li_s)
        targets = set(v["targets"])
        cl = comm_lines.get(li)
        window = base_daf.get(cl.daf_key, []) if cl else []
        window_idx = {ln.line_index for ln in window}
        gold_in_window = bool(targets & window_idx)

        if li in pred and targets & pred[li]:
            buckets["hit"] += 1
        elif not gold_in_window:
            buckets["unreachable"] += 1
        elif li not in pred:
            # gold reachable but matcher emitted nothing (rare) — still recoverable
            buckets["recoverable"] += 1
        else:
            buckets["recoverable"] += 1
            # margin among window candidates: best vs best-gold
            scored = sorted((score_candidate(_dibur_of(cl), ln.content), ln.line_index)
                            for ln in window)
            if scored:
                best = scored[-1][0]
                gold_best = max((s for s, idx in scored if idx in targets), default=0)
                if best - gold_best < 30:
                    recov_small_margin += 1

    total = sum(buckets.values())
    return {
        "title": g["commentary_title"],
        "gold": total,
        "super_pct": round(100 * g["super_commentary_lines"] / g["gold_lines"], 1),
        **buckets,
        "recov_small_margin": recov_small_margin,
    }


def _dibur_of(cl):
    # cheap dibbur proxy: strip a leading <b>..</b> label, use the rest.
    import re
    t = re.sub(r"^<b>.*?</b>\s*", "", cl.content).strip()
    return t or cl.content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(HERE, "truth"))
    ap.add_argument("--repo", default=os.path.join(HERE, ".."))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "oracle.json"))
    args = ap.parse_args()

    from evaluate import DEFAULT_SUITE
    if args.all:
        titles = [f[:-len(".gold.json")] for f in sorted(os.listdir(args.truth))
                  if f.endswith(".gold.json")]
    else:
        titles = DEFAULT_SUITE

    rows = []
    for t in titles:
        gp = os.path.join(args.truth, t + ".gold.json")
        if not os.path.exists(gp):
            continue
        g = json.load(open(gp, encoding="utf-8"))
        if not g.get("aligned"):
            continue
        if ACHARON_ONLY and g["super_commentary_lines"] == 0:
            continue
        try:
            rows.append(analyze(gp, args.repo))
        except Exception as exc:  # noqa: BLE001
            print(f"[err] {t}: {exc}", file=sys.stderr)

    def p(n, d):
        return f"{100*n/d:5.1f}%" if d else "  n/a"

    print(f"\n{'book':34} {'gold':>5} {'hit':>7} {'recov':>7} {'unreach':>8} {'ceiling':>8} {'sm-marg':>7}")
    print("-" * 88)
    agg = {"hit": 0, "recoverable": 0, "unreachable": 0, "nopred": 0, "gold": 0,
           "recov_small_margin": 0}
    for r in rows:
        ceil = r["hit"] + r["recoverable"]
        print(f"{r['title'][:34]:34} {r['gold']:5} {p(r['hit'],r['gold']):>7} "
              f"{p(r['recoverable'],r['gold']):>7} {p(r['unreachable'],r['gold']):>8} "
              f"{p(ceil,r['gold']):>8} {r['recov_small_margin']:>7}")
        for k in agg:
            agg[k] += r.get(k, 0)
    print("-" * 88)
    G = agg["gold"]
    cur = agg["hit"]
    ceil = agg["hit"] + agg["recoverable"]
    print(f"AGGREGATE ({len(rows)} acharon books, {G} gold lines):")
    print(f"  current matcher hit@set : {p(cur,G)} ({cur})")
    print(f"  ORACLE CEILING          : {p(ceil,G)}  (+{p(agg['recoverable'],G).strip()} headroom)")
    print(f"  unreachable (upstream)  : {p(agg['unreachable'],G)} ({agg['unreachable']})")
    print(f"  recoverable w/ margin<30 : {agg['recov_small_margin']} "
          f"({p(agg['recov_small_margin'],max(agg['recoverable'],1))} of recoverable)")

    json.dump({"rows": rows, "aggregate": agg}, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
