#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ולידציה של קבצי הלוואי של ספר: _links.json, _alt_toc.json, _headings.json.

  python -X utf8 validate_sidecars.py --links "…/ספר_links.json" --book "…/ספר.txt" \
         [--target "…/יעד.txt"] [--sefaria-titles .github/data/sefaria_he_titles.txt]
  python -X utf8 validate_sidecars.py --alt-toc "…/ספר_alt_toc.json" --book "…/ספר.txt"
  python -X utf8 validate_sidecars.py --headings "…/ספר_headings.json" --book "…/ספר.txt"

הכללים מ-references/sidecars.md. exit 1 על שגיאה.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADING_RE = re.compile(r"^\s*<\s*h[1-6]\b", re.I)
REQUIRED = {"line_index_1", "line_index_2", "heRef_2", "path_2", "Conection Type"}
DEPENDENT_TYPES = {"commentary", "super_commentary", "targum", "midrash", "parshanut",
                   "dibur_hamatchil", "elucidation", "explication"}
REFERENCE_TYPES = {"reference", "quotation", "mesorat hashas", "ein mishpat",
                   "ein mishpat / ner mitsvah", "mishnah in talmud", "related",
                   "related passage", "allusion", "liturgy", "law", "summary",
                   "sifrei mitsvot", "essay", "linker", "other", "quotation_auto",
                   "quotation_auto_tanakh", "midrash", "footnotes"}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def check_links(path: Path, book: Path | None, target: Path | None,
                sefaria_titles: set[str] | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        err(f"{path.name}: הקובץ חייב להיות מערך של רשומות")
        return

    src_lines = read_lines(book) if book else None
    tgt_lines = read_lines(target) if target else None
    if book and path.stem != f"{book.stem}_links":
        warn(f"שם קובץ הקישורים ({path.stem}) אינו '<{book.stem}>_links'")

    prev_key = None
    seen: set[tuple] = set()
    for idx, entry in enumerate(data):
        tag = f"{path.name}[{idx}]"
        if not isinstance(entry, dict):
            err(f"{tag}: רשומה שאינה אובייקט")
            continue
        missing = REQUIRED - set(entry)
        if missing:
            err(f"{tag}: חסרים שדות: {', '.join(sorted(missing))}")
        if "Connection Type" in entry:
            err(f"{tag}: הכתיב חייב להיות 'Conection Type' (n אחת) — אחרת הסוג נקרא ריק")
        ctype = str(entry.get("Conection Type", "")).strip().lower()
        if ctype and ctype not in DEPENDENT_TYPES and ctype not in REFERENCE_TYPES:
            warn(f"{tag}: סוג קשר לא מוכר ({ctype!r}) — ייכתב כ-OTHER")
        if ctype == "source":
            err(f"{tag}: 'source' וירטואלי ולעולם אינו נשמר — החליפו כיוון בין המקור ליעד")

        p2 = str(entry.get("path_2", ""))
        if p2 and not p2.endswith(".txt"):
            err(f"{tag}: path_2 חייב להסתיים ב-.txt")
        if "ref_1" in entry and "ref_2" in entry:
            err(f"{tag}: ref_1 ו-ref_2 אינם יכולים להופיע יחד")
        if sefaria_titles is not None and p2:
            title = p2[:-4]
            is_sefaria = title in sefaria_titles
            if is_sefaria and not entry.get("ref_2"):
                err(f"{tag}: היעד {title!r} הוא ספר ספריא — חובה ref_2 (new_target_ref_required)")
            if not is_sefaria and entry.get("ref_2"):
                err(f"{tag}: ref_2 על יעד שאינו ספריא ({title!r}) — ייפול ב-ref_2 side classification changed")

        for field, lines_ref, label in (("line_index_1", src_lines, "ספר המקור"),
                                        ("line_index_2", tgt_lines, "ספר היעד")):
            val = entry.get(field)
            if not isinstance(val, int) or val < 1:
                err(f"{tag}: {field} חייב להיות מספר שלם 1-based")
                continue
            if lines_ref is not None:
                if val > len(lines_ref):
                    err(f"{tag}: {field}={val} מעבר לסוף {label} ({len(lines_ref)} שורות)")
                elif HEADING_RE.match(lines_ref[val - 1]):
                    err(f"{tag}: {field}={val} מצביע על שורת כותרת — הגנרטור ידלג על הקישור")
                elif not lines_ref[val - 1].strip():
                    err(f"{tag}: {field}={val} מצביע על שורה ריקה")

        for field, base in (("line_index_1_end", "line_index_1"),
                            ("line_index_2_end", "line_index_2")):
            if field in entry:
                end, start = entry[field], entry.get(base)
                if not isinstance(end, int) or not isinstance(start, int):
                    err(f"{tag}: {field} חייב להיות מספר שלם")
                elif end < start:
                    err(f"{tag}: {field}={end} קטן מ-{base}={start} — הטווח יושמט")

        if "start" in entry:
            s, e = entry.get("start"), entry.get("end")
            if not isinstance(s, int) or s < 0:
                err(f"{tag}: start חייב להיות אופסט תו לא-שלילי")
            elif src_lines and isinstance(entry.get("line_index_1"), int):
                li = entry["line_index_1"]
                if 1 <= li <= len(src_lines) and s > len(src_lines[li - 1]):
                    err(f"{tag}: start={s} מעבר לאורך שורת המקור")
            if e is not None and isinstance(s, int) and isinstance(e, int) and e < s:
                err(f"{tag}: end={e} קטן מ-start={s}")
            if " אות " not in str(entry.get("heRef_2", "")):
                warn(f"{tag}: עוגן בלי ' אות X' ב-heRef_2 — לא תיווצר תווית לסמן")

        key = (entry.get("path_2"), entry.get("line_index_2"))
        if prev_key and key != prev_key and key in seen:
            warn(f"{tag}: רשומות לאותה שורת יעד אינן רצופות — groupConsecutiveLinks יפצל אותן בתצוגה")
        seen.add(key)
        prev_key = key

    print(f"{path.name}: {len(data)} רשומות")


def check_alt_toc(path: Path, book: Path | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        err(f"{path.name}: הקובץ חייב להיות מערך מבנים")
        return
    total = len(read_lines(book)) if book else None
    keys: set[str] = set()

    def walk(nodes, parent: str, seen_lines: set[int]) -> int:
        count = 0
        if not isinstance(nodes, list):
            err(f"{path.name}: nodes תחת {parent} אינו מערך")
            return 0
        for node in nodes:
            if not isinstance(node, dict):
                err(f"{path.name}: צומת שאינו אובייקט תחת {parent}")
                continue
            if not node.get("heTitle"):
                err(f"{path.name}: צומת בלי heTitle תחת {parent}")
            line = node.get("line")
            if not isinstance(line, int) or line < 1:
                err(f"{path.name}: {node.get('heTitle')!r} — line חייב להיות 1-based")
            else:
                if total and line > total:
                    err(f"{path.name}: {node.get('heTitle')!r} — line={line} מעבר לסוף הספר ({total})")
                if line in seen_lines:
                    err(f"{path.name}: שורה {line} כפולה תחת {parent} — הצומת יושמט")
                seen_lines.add(line)
            count += 1
            if node.get("children"):
                count += walk(node["children"], node.get("heTitle", "?"), set())
        return count

    nodes_total = 0
    for struct in data:
        if not isinstance(struct, dict):
            err(f"{path.name}: מבנה שאינו אובייקט")
            continue
        key = struct.get("key")
        if not key:
            err(f"{path.name}: מבנה בלי key (מזהה יציב באנגלית)")
        elif key in keys:
            err(f"{path.name}: key כפול {key!r}")
        else:
            keys.add(key)
        nodes_total += walk(struct.get("nodes", []), str(key), set())
    print(f"{path.name}: {len(data)} מבנים, {nodes_total} צמתים")


def check_headings(path: Path, book: Path | None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        err(f"{path.name}: הקובץ חייב להיות מילון {{כותרת: מספר שורה}}")
        return
    total = len(read_lines(book)) if book else None
    prev = 0
    for title, line in data.items():
        if not isinstance(line, int) or line < 1:
            err(f"{path.name}: {title!r} — הערך חייב להיות מספר שורה 1-based")
            continue
        if total and line > total:
            err(f"{path.name}: {title!r} — שורה {line} מעבר לסוף הספר ({total})")
        if line < prev:
            warn(f"{path.name}: {title!r} — שורה {line} קטנה מהקודמת ({prev}); הסדר אמור לעלות")
        prev = line
    print(f"{path.name}: {len(data)} כותרות")


def main() -> int:
    ap = argparse.ArgumentParser(description="ולידציה של קבצי הלוואי של ספר אוצריא")
    ap.add_argument("--links")
    ap.add_argument("--alt-toc")
    ap.add_argument("--headings")
    ap.add_argument("--book", help="קובץ הספר (ספר המקור) — מאפשר בדיקת טווחי שורות וכותרות")
    ap.add_argument("--target", help="קובץ ספר היעד — מאפשר בדיקת line_index_2")
    ap.add_argument("--sefaria-titles", help="נתיב ל-.github/data/sefaria_he_titles.txt")
    args = ap.parse_args()

    if not any([args.links, args.alt_toc, args.headings]):
        ap.error("יש לציין לפחות אחד מ---links / --alt-toc / --headings")

    book = Path(args.book) if args.book else None
    target = Path(args.target) if args.target else None
    titles = None
    if args.sefaria_titles:
        titles = {l.strip() for l in
                  Path(args.sefaria_titles).read_text(encoding="utf-8").splitlines() if l.strip()}

    if args.links:
        check_links(Path(args.links), book, target, titles)
    if args.alt_toc:
        check_alt_toc(Path(args.alt_toc), book)
    if args.headings:
        check_headings(Path(args.headings), book)

    for msg in errors:
        print(f"[שגיאה] {msg}")
    for msg in warnings:
        print(f"[אזהרה] {msg}")
    print(f"סה\"כ: {len(errors)} שגיאות, {len(warnings)} אזהרות")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
