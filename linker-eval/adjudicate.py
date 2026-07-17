#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adjudicate.py — stage 3: the Haiku day-adjudicator, measured against gold.

The oracle ceiling (oracle_ceiling.py) proved that for aligned acharonim the
correct base line is in the matcher's daf window ~95% of the time; the matcher's
token-overlap argmax just picks wrong. So we let an LLM PICK among the same
candidates. It never searches raw text — per daf it sees the numbered Gemara
segments and the commentary snippets, and returns, for each snippet, the segment
number it comments on (or 0).

This script runs a real slice through Haiku (via the `claude -p` CLI, so no API
key wiring is needed) and reports, on the adjudicated lines only:
    matcher hit@set   vs   Haiku hit@set   vs   oracle (gold-in-window)
so the lift is measured on identical lines against identical gold.

Backend: `claude -p --model <haiku>`; swap _call_llm for the Batch API later.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "matcher_b26"))
from dibur_matcher import match_citing_book, parse_book, build_daf_index  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
TAG_RE = re.compile(r"<[^>]+>")


def clean(txt, limit=220):
    t = TAG_RE.sub("", txt).strip()
    return t[:limit]


def _call_llm(prompt, model):
    try:
        out = subprocess.run(["claude", "-p", prompt, "--model", model],
                             capture_output=True, text=True, timeout=420).stdout
    except subprocess.TimeoutExpired:
        print("  [warn] LLM call timed out; keeping matcher picks for this daf", file=sys.stderr)
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def build_prompt(daf, gem_cands, seq):
    """seq: ordered list of dicts with pos, text, decide(bool), anchor(int|None).

    Anchor lines are already-placed (the matcher's confident picks) and are shown
    with their Gemara number as fixed context; [?] lines are the ones Haiku must
    place. Showing the full daf sequence in order is the neighbor-context lever:
    a "שם"/"בא\"ד"/"עוד" line continues the previous line's Gemara segment, so
    Haiku needs to see what the previous line was placed on.
    """
    lines = [
        "אתה ממקם קטעי פירוש על התלמוד, לפי הסדר בדף. לפניך קטעי גמרא ממוספרים, ואז רצף",
        "קטעי הפירוש. שורות [גמרא N] כבר משויכות (הקשר בלבד). לשורות [? נוכחי:N] יש ניחוש",
        "אוטומטי — תפקידך לאשר או לתקן: החזר את N הנוכחי אלא אם אתה בטוח שקטע גמרא אחר",
        "מתאים יותר; בספק — השאר את הנוכחי. (ניחוש:0 = עדיין לא שויך, מצא את המתאים.)",
        "כלל המשך: קטע שפותח ב\"שם\"/\"בא\"ד\"/\"עוד\"/\"והנה\"/\"בד\"ה\" בלי שם חדש — לרוב",
        "ממשיך את אותו קטע גמרא של הקטע שלפניו. הדיבור-המתחיל בתחילת הקטע הוא הרמז העיקרי.",
        "אם קטע אינו על אף קטע גמרא בדף — החזר 0.",
        f"\n=== קטעי גמרא (דף {daf}) ===",
    ]
    for n, (_idx, txt) in enumerate(gem_cands, 1):
        lines.append(f"{n}. {clean(txt,340)}")   # wider: the dibbur may be deep in the segment
    lines.append("\n=== רצף קטעי הפירוש ===")
    for s in seq:
        if not s["decide"]:
            mark = f"[גמרא {s['anchor']}]" if s["anchor"] else "[גמרא ?]"
        else:
            mark = f"[? נוכחי:{s.get('current') or 0}]"
        lines.append(f"{s['pos']}. {mark} {clean(s['text'],260)}")
    lines.append('\nהחזר JSON בלבד: {"picks":[{"c":<מספר קטע פירוש שמסומן [?]>,"g":<מספר קטע גמרא או 0>}]}')
    return "\n".join(lines)


def run(gold_path, repo_root, model, max_dafim, only_flagged):
    g = json.load(open(gold_path, encoding="utf-8"))
    citing = os.path.join(repo_root, g["commentary_txt"])
    base = os.path.join(repo_root, g["base_title"] and g["base_txt"])

    comm = parse_book(citing)
    comm_by_idx = {ln.line_index: ln for ln in comm}
    base_lines = parse_book(base)
    base_daf = build_daf_index(base_lines)

    res = match_citing_book(citing, g["base_title"], base, {}, {})
    matcher_pick = {}
    for e in res.entries:
        s = e["line_index_2"]; end = e.get("line_index_2_end", s)
        matcher_pick[e["line_index_1"]] = set(range(min(s, end), max(s, end) + 1))
    flagged = {idx for idx, _ in res.low_confidence}
    gold = {int(k): set(v["targets"]) for k, v in g["gold"].items()}

    # group gold comment lines by their daf, in file order
    by_daf = {}
    for li in sorted(gold):
        cl = comm_by_idx.get(li)
        if not cl or not cl.daf_key:
            continue
        by_daf.setdefault(cl.daf_key, []).append(li)

    dafim = [d for d in by_daf if base_daf.get(d)][:max_dafim]
    # hybrid = matcher's confident picks kept as-is; Haiku decides only flagged lines.
    tot = {"n": 0, "matcher": 0, "hybrid": 0, "oracle": 0, "sent": 0}
    per_daf = []
    for daf in dafim:
        window = base_daf[daf]
        gem_cands = [(ln.line_index, ln.content) for ln in window]
        num2base = {n: idx for n, (idx, _) in enumerate(gem_cands, 1)}
        base2num = {idx: n for n, idx in num2base.items()}
        win_idx = {idx for idx, _ in gem_cands}

        lis = by_daf[daf]  # ALL gold lines in the daf, in order (context sequence)
        seq = []
        for pos, li in enumerate(lis, 1):
            decide = (li in flagged) if only_flagged else True
            anchor = None
            current = None
            mpick_num = base2num.get(min(matcher_pick[li])) if li in matcher_pick else None
            if not decide:
                anchor = mpick_num
                if anchor is None:      # matcher pointed outside window: let Haiku decide
                    decide = True
            if decide:
                current = mpick_num or 0  # matcher's guess shown for confirm-or-correct
            seq.append({"pos": pos, "li": li, "decide": decide, "anchor": anchor,
                        "current": current, "text": comm_by_idx[li].content})

        to_decide = [s for s in seq if s["decide"]]
        picks = {}
        if to_decide:
            resp = _call_llm(build_prompt(daf, gem_cands, seq), model)
            if resp and isinstance(resp.get("picks"), list):
                for p in resp["picks"]:
                    try:
                        picks[int(p["c"])] = int(p["g"])
                    except (KeyError, ValueError, TypeError):
                        pass

        d_stat = {"daf": daf, "n": 0, "matcher": 0, "hybrid": 0, "oracle": 0,
                  "sent": len(to_decide)}
        for s in seq:
            li = s["li"]; tset = gold[li]
            d_stat["n"] += 1
            if li in matcher_pick and tset & matcher_pick[li]:
                d_stat["matcher"] += 1
            if tset & win_idx:
                d_stat["oracle"] += 1
            # hybrid decision
            if s["decide"]:
                if s["pos"] in picks:
                    gpick = picks[s["pos"]]
                    final = num2base.get(gpick) if gpick else None   # 0 => "none"
                else:  # Haiku didn't answer this line: keep matcher's guess
                    final = min(matcher_pick[li]) if li in matcher_pick else None
            else:
                final = min(matcher_pick[li]) if li in matcher_pick else None
            if final is not None and final in tset:
                d_stat["hybrid"] += 1
        per_daf.append(d_stat)
        for k in ("n", "matcher", "hybrid", "oracle", "sent"):
            tot[k] += d_stat[k]
        print(f"  daf {daf:8} n={d_stat['n']:3} sent={d_stat['sent']:3}  "
              f"matcher={d_stat['matcher']:3}  hybrid={d_stat['hybrid']:3}  "
              f"oracle={d_stat['oracle']:3}", file=sys.stderr)

    return {"book": g["commentary_title"], "model": model,
            "only_flagged": only_flagged, "total": tot, "per_daf": per_daf}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="פני יהושע על בבא קמא")
    ap.add_argument("--truth", default=os.path.join(HERE, "truth"))
    ap.add_argument("--repo", default=os.path.join(HERE, ".."))
    ap.add_argument("--model", default=HAIKU)
    ap.add_argument("--max-dafim", type=int, default=5)
    ap.add_argument("--only-flagged", action="store_true",
                    help="adjudicate only matcher-low-confidence lines (triage)")
    ap.add_argument("--out", default=os.path.join(HERE, "adjudicate.json"))
    args = ap.parse_args()

    gp = os.path.join(args.truth, args.book + ".gold.json")
    print(f"adjudicating {args.book} (<= {args.max_dafim} dafim) via {args.model}", file=sys.stderr)
    r = run(gp, args.repo, args.model, args.max_dafim, args.only_flagged)

    t = r["total"]
    def pct(n): return f"{100*n/t['n']:.1f}%" if t["n"] else "n/a"
    print(f"\n=== {r['book']}  [{r['model']}]  ({t['n']} gold lines, {t['sent']} sent to LLM) ===")
    print(f"  matcher hit@set : {pct(t['matcher'])} ({t['matcher']}/{t['n']})")
    print(f"  HYBRID  hit@set : {pct(t['hybrid'])} ({t['hybrid']}/{t['n']})  "
          f"(matcher-confident + LLM on the rest)")
    print(f"  oracle ceiling  : {pct(t['oracle'])} ({t['oracle']}/{t['n']})")
    lift = t["hybrid"] - t["matcher"]
    print(f"  lift over matcher: {lift:+d} lines ({100*lift/t['n']:+.1f} pts)" if t["n"] else "")
    json.dump(r, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
