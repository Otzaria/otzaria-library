#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remove the 'אוצר הספרים היהודי השיתופי' intro-message header block from every
book under wikiJewishBooksToOtzaria, and shift the line_index_1 references in
the corresponding *_links.json files so no commentary link breaks.

Modes:
  python fix_wiki_headers.py verify   # dry run: shift in memory, prove content equality, write nothing
  python fix_wiki_headers.py apply    # actually edit txt + json
"""
import json, re, sys
from pathlib import Path

ROOT = Path("/Users/david/Documents/otzaria-books/otzaria-library/wikiJewishBooksToOtzaria")
PHRASE = "אוצר הספרים היהודי השיתופי"
PLAIN = "באדיבות 'אוצר הספרים היהודי השיתופי'"
PLAIN2_PREFIX = "(במצב מקוון אפשר ללחוץ"
HTML_PREFIX = '<p style="color: gray;">באדיבות'

def detect_block(lines):
    """Return (start_idx0, length) of header message block, or None."""
    for i, ln in enumerate(lines):
        s = ln.rstrip("\n")
        if s.strip() == PLAIN:
            if i + 1 < len(lines) and lines[i+1].lstrip().startswith(PLAIN2_PREFIX):
                return (i, 2)
            return (i, 1)
        if s.lstrip().startswith(HTML_PREFIX):
            return (i, 1)
    return None

def read_text_lines(p):
    txt = p.read_text(encoding="utf-8")
    return txt.split("\n")

def new_index1(idx1, block):
    """1-based idx1 -> new 1-based idx after removing block=(start0,blen)."""
    start1 = block[0] + 1
    end1 = block[0] + block[1]
    if idx1 < start1:
        return idx1
    if start1 <= idx1 <= end1:
        raise RuntimeError(f"link points INSIDE removed block: idx1={idx1} block={block}")
    return idx1 - block[1]

def main(mode):
    all_txt = sorted(ROOT.rglob("*.txt"))
    stem_to_path = {p.stem: p for p in all_txt}
    # 1. detect blocks per book
    blocks = {}          # path -> (start0, blen)
    for p in all_txt:
        blk = detect_block(read_text_lines(p))
        if blk:
            blocks[p] = blk

    link_dirs = [ROOT/"links", ROOT/"ספרים"/"לא להכנסה כרגע"/"links"]

    total_links = 0
    verify_fail = 0
    plan_txt = []     # (path, block, new_line_count)
    plan_json = []    # (jf, blen) -- textual decrement to preserve formatting

    # 2. verify + build json plan (content-equality proof)
    for ld in link_dirs:
        if not ld.exists():
            continue
        for jf in sorted(ld.glob("*_links.json")):
            stem = jf.stem[:-len("_links")]
            book_path = stem_to_path.get(stem)
            blk = blocks.get(book_path)
            data = json.loads(jf.read_text(encoding="utf-8"))
            if blk is None:
                # source has no header -> no shift; still record unchanged
                continue
            blen = blk[1]
            old_lines = read_text_lines(book_path)
            new_lines = old_lines[:blk[0]] + old_lines[blk[0]+blk[1]:]
            # target files (path_2) are untouched -> line_index_2 stays valid trivially
            for e in data:
                oi = e["line_index_1"]
                ni = new_index1(oi, blk)
                # uniform-decrement must hold for the textual regex apply to be exact
                assert ni == oi - blen, f"non-uniform shift in {jf.name}: {oi}->{ni}"
                # PROOF: content at old idx1 (old file) == content at new idx1 (new file)
                old_c = old_lines[oi-1]
                new_c = new_lines[ni-1]
                total_links += 1
                if old_c != new_c:
                    verify_fail += 1
                    print(f"  MISMATCH {jf.name}: idx {oi}->{ni}\n    OLD: {old_c[:70]!r}\n    NEW: {new_c[:70]!r}")
            plan_json.append((jf, blen))

    # 3. build txt plan (all books with a block, incl. those without json)
    for p, blk in blocks.items():
        old_lines = read_text_lines(p)
        new_lines = old_lines[:blk[0]] + old_lines[blk[0]+blk[1]:]
        plan_txt.append((p, blk, len(old_lines), len(new_lines), "\n".join(new_lines)))

    print(f"\nbooks with header block: {len(plan_txt)}")
    print(f"json files to shift: {len(plan_json)}")
    print(f"links verified (content equality): {total_links}, mismatches: {verify_fail}")

    if verify_fail:
        print("\n*** VERIFICATION FAILED — not writing anything ***")
        sys.exit(1)

    if mode == "verify":
        print("\nDRY RUN ok. Nothing written.")
        return

    # 4. APPLY
    for p, blk, oldn, newn, content in plan_txt:
        p.write_text(content, encoding="utf-8")
    # JSON: textually decrement ONLY the line_index_1 values, preserving all
    # original formatting (indent / \u-escaping / spacing) byte-for-byte otherwise.
    for jf, blen in plan_json:
        raw = jf.read_text(encoding="utf-8")
        n_before = len(re.findall(r'"line_index_1"\s*:\s*\d+', raw))
        def dec(m):
            return f'{m.group(1)}{int(m.group(2)) - blen}'
        new_raw, n = re.subn(r'("line_index_1"\s*:\s*)(\d+)', dec, raw)
        assert n == n_before, (jf.name, n, n_before)
        jf.write_text(new_raw, encoding="utf-8")
    print("\nAPPLIED: txt files and json files written.")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "verify")
