#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check 8 — daf agreement, over 100% of entries.

The daf heading a citing line is printed under must equal the daf its link
resolves to. This is the highest-precision check available without reading
text: it needs no judgement and no DB, and it catches whole-page misses that
word-overlap heuristics happily rate as good matches.

A mismatch is `major`. Per the skill's overriding principle, a mismatch you
cannot repair against the correct daf is REMOVED, not shipped.

Usage:
  python -X utf8 check_daf.py --links "<...>_links.json" --citing "<citing>.txt"
  python -X utf8 check_daf.py --dir "<links dir>" --books-root "<repo root>"

Exit code 1 if any mismatch is found.
"""
import argparse, json, os, re, sys, io, collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daf_util import heading_daf_map, daf_from_heref, same_daf

LINKED = ("commentary", "super_commentary")


def check(links_path, citing_path):
    lines = open(citing_path, encoding="utf-8").read().split("\n")
    dmap = heading_daf_map(lines)
    recs = json.load(open(links_path, encoding="utf-8"))
    out = collections.Counter()
    bad = []
    for r in recs:
        if not isinstance(r, dict) or r.get("Conection Type") not in LINKED:
            continue
        li = r.get("line_index_1")
        cd = dmap[li] if isinstance(li, int) and li <= len(lines) else None
        td = daf_from_heref(r.get("heRef_2"))
        if cd is None:
            out["citing_daf_unknown"] += 1; continue
        if td is None:
            out["target_daf_unknown"] += 1; continue
        if same_daf(cd, td):
            out["match"] += 1
        else:
            out["MISMATCH"] += 1
            bad.append((li, f"{cd[0]}{cd[1] or ''}", f"{td[0]}{td[1] or ''}",
                        r.get("heRef_2"),
                        re.sub(r"<[^>]+>", "", lines[li - 1])[:58]))
    return out, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--links"); ap.add_argument("--citing")
    ap.add_argument("--dir"); ap.add_argument("--books-root")
    a = ap.parse_args()

    pairs = []
    if a.links and a.citing:
        pairs.append((a.links, a.citing))
    elif a.dir and a.books_root:
        idx = {}
        for root, _, files in os.walk(a.books_root):
            if ".git" in root: continue
            for f in files:
                if f.endswith(".txt"): idx.setdefault(f, os.path.join(root, f))
        for f in sorted(os.listdir(a.dir)):
            if not f.endswith("_links.json"): continue
            src = idx.get(f.replace("_links.json", "") + ".txt")
            if src: pairs.append((os.path.join(a.dir, f), src))
            else: print(f"  !! citing .txt not found for {f}")
    else:
        ap.error("pass --links and --citing, or --dir and --books-root")

    tot = collections.Counter(); worst = []
    for lp, cp in pairs:
        out, bad = check(lp, cp)
        tot.update(out)
        if bad:
            name = os.path.basename(lp).replace("_links.json", "")
            print(f"\n--- {name}: {len(bad)} mismatches ---")
            for li, cd, td, h, tx in bad[:10]:
                print(f"  line {li}: citing daf {cd} -> link {td}   ({h})")
                print(f"      {tx}")
            worst.extend(bad)

    n = tot["match"] + tot["MISMATCH"]
    print("\n" + "=" * 60)
    for k in ("match", "MISMATCH", "citing_daf_unknown", "target_daf_unknown"):
        print(f"  {k:<22} {tot[k]:>6}")
    if n:
        print(f"\n  daf accuracy: {100 * tot['match'] / n:.2f}%")
    return 1 if tot["MISMATCH"] else 0


if __name__ == "__main__":
    sys.exit(main())
