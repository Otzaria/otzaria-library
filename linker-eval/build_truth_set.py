#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_truth_set.py — Stage 1 of the commentary-linker evaluation harness.

Extracts a GROUND-TRUTH ("gold") dataset of commentary->Talmud line mappings from
an existing seforim.db, to be used later to MEASURE how well the deterministic
dibbur matcher (linker/dibur_matcher.py on branch 26) reproduces human links.

Why this works
--------------
seforim.db already contains ~2.25M human-curated COMMENTARY links. The subset that
matters here: links whose *base* side is a Talmud Bavli tractate and whose
*commentary* side is a Sefaria-sourced book. Those come from Sefaria's own link
data (connection_type COMMENTARY, id 1) -- NOT from the automated linker
(connection_type LINKER, id 15) -- so they are independent of anything the matcher
produces. That makes them a valid gold standard.

Link direction in the DB (verified): for a COMMENTARY link,
    sourceBookId / sourceLineId  = the BASE text (the Gemara)
    targetBookId / targetLineId  = the COMMENTARY (the מפרש)
i.e. the base text "has a commentary" pointing at it.

Index alignment (verified against the .txt files):
    physical .txt line number (1-based)  ==  DB line.lineIndex + 1  ==  the
    line_index used in the *_links.json files the matcher emits.
So a gold set built in DB space converts to matcher/JSON space by +1, with no
line dropping (base .txt line count == DB totalLines exactly).

Important caveats baked into the output
---------------------------------------
1. PARTIAL COVERAGE. Sefaria does not link every comment. E.g. פני יהושע על בבא קמא
   has gold on ~40% of content lines. Therefore the honest metric this set supports
   is PRECISION ON THE COVERED SUBSET: "of the comment lines that DO have a gold
   answer, what fraction did the matcher place on a gold-accepted base line?"
   Absence of a gold link means "Sefaria didn't record one", NOT "no link exists".

2. MANY-TO-MANY. A single comment line can carry several gold base lines (a dibbur
   plus thematic cross-refs). The gold value is therefore a SET; the fair metric is
   hit@set (matcher's chosen base line ∈ gold set). `primary` (lowest base index) is
   recorded for an optional stricter check but is a heuristic, not authoritative.

3. SUPER-COMMENTARY MISMATCH. Sefaria maps a "בתוספות ד\"ה" / "בפרש\"י ד\"ה" comment
   to the *base Gemara* line, whereas the branch-26 matcher tries to route it to the
   Rashi/Tosafot book as super_commentary. These comment lines are TAGGED
   (`is_super`) so evaluation can score them separately instead of counting a
   philosophical difference as an error.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

# ---- super-commentary opener detection (mirrors branch-26 matcher intent) ----
_B_TAG_RE = re.compile(r"</?b>", re.I)
_SUPER_PATTERNS = [
    re.compile(r'^(?:ב|ו)?(?:רש["״]י|רשי)\s+ב?ד["״]ה\b'),
    re.compile(r'^(?:ב|ו)?(?:פרש["״]י|פירש["״]י)\s+ב?ד["״]ה\b'),
    re.compile(r'^(?:ב|ו)?(?:רשב["״]ם|רשבם)\s+ב?ד["״]ה\b'),
    re.compile(r'^(?:ב|ו)?(?:תוספות|תוספ[\'׳]?|תוס[\'׳]?)\s+ב?ד["״]ה\b'),
    re.compile(r'^רד["״]ה\b'),   # רש"י ד"ה
    re.compile(r'^תוד["״]ה\b'),  # תוספות ד"ה
]


def _flatten_leading_bold(text):
    return _B_TAG_RE.sub(" ", text).strip()


def is_super_opener(content):
    t = _flatten_leading_bold(content)
    t = re.sub(r'^(?:שם|עוד שם)\s+', '', t)
    return any(p.match(t) for p in _SUPER_PATTERNS)


def build_txt_index(repo_root):
    """basename(without dir) -> list of repo-relative paths, Sefaria tree first."""
    idx = defaultdict(list)
    for dirpath, _dirs, files in os.walk(repo_root):
        if "/.git" in dirpath:
            continue
        for fn in files:
            if fn.endswith(".txt"):
                rel = os.path.relpath(os.path.join(dirpath, fn), repo_root)
                idx[fn].append(rel)
    for fn in idx:
        idx[fn].sort(key=lambda p: (0 if "SefariaToOtzria" in p else 1, len(p)))
    return idx


def resolve_txt(title, txt_index):
    return (txt_index.get(title + ".txt") or [None])[0]


def verify_alignment(cur, book_id, total_lines, txt_abs):
    """Confirm the on-disk .txt is the SAME version the DB was built from.

    The gold indices live in DB space; they are only valid against the on-disk
    file if that file is byte-for-byte the version the DB ingested. Books that
    were re-pulled after the DB was built (e.g. the sefaria_api/<year> trees)
    drift and must be excluded, or every gold index is silently off.

    Check: (1) physical line count == DB totalLines, and (2) a sample of lines
    matches DB content exactly. Returns (ok: bool, reason: str).
    """
    try:
        with open(txt_abs, encoding="utf-8") as f:
            disk = [ln.rstrip("\n") for ln in f]
    except OSError as e:
        return False, f"unreadable: {e}"
    if len(disk) != total_lines:
        return False, f"line count {len(disk)} != DB {total_lines}"
    # sample ~8 evenly spaced content lines and compare to DB
    n = len(disk)
    if n == 0:
        return False, "empty file"
    sample = sorted({(i * n) // 9 for i in range(1, 9)})
    cur.execute(
        f"SELECT lineIndex, content FROM line WHERE bookId=? AND lineIndex IN "
        f"({','.join('?' * len(sample))})",
        (book_id, *sample),
    )
    dbmap = {li: c for li, c in cur.fetchall()}
    for idx0 in sample:
        if dbmap.get(idx0, "\0") != disk[idx0]:  # idx0 is 0-based == physical idx0
            return False, f"content drift at line {idx0 + 1}"
    return True, "ok"


def tractate_ids(cur):
    cur.execute("""
        WITH RECURSIVE sub(id) AS (
            SELECT 12 UNION SELECT c.id FROM category c JOIN sub ON c.parentId = sub.id
        )
        SELECT id FROM book
        WHERE categoryId IN (SELECT id FROM sub) AND isBaseBook = 1
    """)
    return {r[0] for r in cur.fetchall()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="path to seforim.db")
    ap.add_argument("--repo", default=".", help="otzaria-library repo root (for .txt resolution)")
    ap.add_argument("--out", default="linker-eval", help="output dir")
    ap.add_argument("--gold-source", default="Sefaria",
                    help="source name whose commentary books count as gold")
    ap.add_argument("--min-gold", type=int, default=100,
                    help="min gold links for a book to enter the manifest")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    tractates = tractate_ids(cur)
    print(f"[i] {len(tractates)} Bavli base tractates", file=sys.stderr)

    # gold source id
    cur.execute("SELECT id FROM source WHERE name = ?", (args.gold_source,))
    row = cur.fetchone()
    if not row:
        sys.exit(f"source {args.gold_source!r} not found")
    gold_src = row[0]

    qmarks = ",".join("?" * len(tractates))
    cur.execute(f"""
        SELECT l.targetBookId, cb.title, l.sourceBookId, bb.title,
               cl.lineIndex, bl.lineIndex, cl.content
        FROM link l
        JOIN book cb ON cb.id = l.targetBookId
        JOIN book bb ON bb.id = l.sourceBookId
        JOIN line cl ON cl.id = l.targetLineId
        JOIN line bl ON bl.id = l.sourceLineId
        WHERE l.connectionTypeId = 1
          AND cb.sourceId = ?
          AND l.sourceBookId IN ({qmarks})
        ORDER BY l.targetBookId, cl.lineIndex, bl.lineIndex
    """, (gold_src, *tractates))

    # books[comm_book_id] = {...}
    books = {}
    for comm_id, comm_title, base_id, base_title, comm_li, base_li, comm_content in cur.fetchall():
        b = books.get(comm_id)
        if b is None:
            b = books[comm_id] = {
                "commentary_book_id": comm_id,
                "commentary_title": comm_title,
                "base_book_id": base_id,
                "base_title": base_title,
                "_gold": defaultdict(set),      # comm_line_1based -> set(base_line_1based)
                "_content": {},                 # comm_line_1based -> content
                "_base_multi": defaultdict(set),
            }
        # If a commentary somehow links to >1 base book, keep the dominant one later.
        b["_gold"][comm_li + 1].add(base_li + 1)
        b["_base_multi"][comm_li + 1].add(base_id)
        b["_content"][comm_li + 1] = comm_content

    print(f"[i] {len(books)} {args.gold_source} commentary books touch Bavli", file=sys.stderr)

    txt_index = build_txt_index(args.repo)

    # totalLines per book, to verify the on-disk .txt matches the ingested version
    cur.execute("SELECT id, totalLines FROM book")
    total_lines_by_id = dict(cur.fetchall())

    os.makedirs(os.path.join(args.out, "truth"), exist_ok=True)
    manifest = []

    for comm_id, b in books.items():
        gold_lines = b["_gold"]
        n_links = sum(len(v) for v in gold_lines.values())
        if n_links < args.min_gold:
            continue

        comm_txt = resolve_txt(b["commentary_title"], txt_index)
        base_txt = resolve_txt(b["base_title"], txt_index)

        # version-alignment gate: gold indices are only valid if the on-disk .txt
        # is the exact version the DB was built from (see verify_alignment).
        comm_ok, comm_reason = (False, "no txt")
        base_ok, base_reason = (False, "no txt")
        if comm_txt:
            comm_ok, comm_reason = verify_alignment(
                cur, comm_id, total_lines_by_id.get(comm_id, -1),
                os.path.join(args.repo, comm_txt))
        if base_txt:
            base_ok, base_reason = verify_alignment(
                cur, b["base_book_id"], total_lines_by_id.get(b["base_book_id"], -1),
                os.path.join(args.repo, base_txt))
        aligned = comm_ok and base_ok
        alignment_reason = "ok" if aligned else f"comm:{comm_reason} | base:{base_reason}"

        n_gold_lines = len(gold_lines)
        n_multi = sum(1 for v in gold_lines.values() if len(v) > 1)
        n_super = sum(1 for li in gold_lines if is_super_opener(b["_content"].get(li, "")))
        max_targets = max(len(v) for v in gold_lines.values())

        entry = {
            "commentary_title": b["commentary_title"],
            "commentary_book_id": comm_id,
            "base_title": b["base_title"],
            "base_book_id": b["base_book_id"],
            "commentary_txt": comm_txt,
            "base_txt": base_txt,
            "runnable": bool(comm_txt and base_txt),
            "aligned": aligned,
            "alignment_reason": alignment_reason,
            "gold_links": n_links,
            "gold_lines": n_gold_lines,           # distinct comment lines with an answer
            "multi_target_lines": n_multi,        # of those, how many are many-to-many
            "super_commentary_lines": n_super,    # of those, how many open with בתוס'/בפרש"י ד"ה
            "max_targets_per_line": max_targets,
        }
        manifest.append(entry)

        # per-book gold file
        gold_obj = {
            **{k: entry[k] for k in (
                "commentary_title", "commentary_book_id", "base_title", "base_book_id",
                "commentary_txt", "base_txt", "aligned", "alignment_reason",
                "gold_links", "gold_lines",
                "multi_target_lines", "super_commentary_lines", "max_targets_per_line")},
            "index_base": "1-based physical .txt line (== DB lineIndex + 1)",
            "gold": {
                str(li): {
                    "targets": sorted(gold_lines[li]),
                    "primary": min(gold_lines[li]),
                    "is_super": is_super_opener(b["_content"].get(li, "")),
                }
                for li in sorted(gold_lines)
            },
        }
        safe = b["commentary_title"].replace("/", "_")
        with open(os.path.join(args.out, "truth", safe + ".gold.json"), "w", encoding="utf-8") as f:
            json.dump(gold_obj, f, ensure_ascii=False, indent=1)

    manifest.sort(key=lambda e: (-e["aligned"], -e["runnable"], -e["gold_links"]))
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    runnable = [m for m in manifest if m["runnable"]]
    aligned = [m for m in manifest if m["aligned"]]
    print(f"[i] wrote {len(manifest)} gold books "
          f"({len(runnable)} runnable, {len(aligned)} version-aligned) to {args.out}/",
          file=sys.stderr)
    con.close()


if __name__ == "__main__":
    main()
