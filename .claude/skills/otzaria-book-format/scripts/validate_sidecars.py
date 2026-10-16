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
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADING_RE = re.compile(r"^\s*<\s*h[1-6]\b", re.I)
# HearotCompanionMerge.isMergeableCompanionTitle: רק השם הזה ממוזג לספר הבסיס.
COMPANION_PREFIX = "הערות על "
REQUIRED = {"line_index_1", "line_index_2", "heRef_2", "path_2", "Conection Type"}
# "source" = the canonical value of a links file named after the CITING book: the
# generator flips the pair into base→מפרש order and stores it as COMMENTARY
# (Generator.kt: `flip = declaredType == SOURCE`). It is a dependent-text link like
# the rest, not an unknown value, and never reaches the DB as SOURCE.
# "footnotes" = הערות שוליים בספר נלווה "הערות על X". סוג תלוי-טקסט ככל השאר,
# והוא מה שמזהה את הצמד ספר↔הערות בלי לנחש לפי כותרת הספר הנלווה.
#
# Every set below is spelled in the form SeforimLibrary compares against
# (Link.kt `fromKnownStringOrNull`: trim, lowercase, ' ' -> '_'), and every value is
# first put through `normalize_ctype`. So "mesorat hashas" (the Sefaria spelling the
# repo's links files actually use) and "mesorat_hashas" are the same valid type.
DEPENDENT_TYPES = {"source", "commentary", "super_commentary", "supercommentary",
                   "targum", "midrash", "parshanut", "dibur_hamatchil", "elucidation",
                   "ellucidation", "explication", "footnotes", "footnote"}
# Oriented by the generator (ORIENTED_DEPENDANT_TYPES) but not a dependent text in the app.
ORIENTED_REFERENCE_TYPES = {"ein_mishpat", "ein_mishpat_/_ner_mitsvah",
                            "ein_mishpat_/_ner_mitzvah"}
LATERAL_TYPES = {"reference", "quotation", "quotation_auto", "quotation_auto_tanakh",
                 "mesorat_hashas", "mishnah_in_talmud", "related", "related_passage",
                 "allusion", "liturgy", "law", "summary", "sifrei_mitzvot", "essay",
                 "linker", "other", "none"}
REFERENCE_TYPES = ORIENTED_REFERENCE_TYPES | LATERAL_TYPES


def _kt_ws(c: str) -> bool:
    """Kotlin Char.isWhitespace(): Character.isWhitespace || Character.isSpaceChar.
    Unlike str.strip() it does NOT treat U+0085 (NEL) as whitespace. Kept identical to
    .claude/skills/otzaria-commentary-linker-qa/scripts/connection_type.py (tested)."""
    return c in "\t\n\x0b\f\r\x1c\x1d\x1e\x1f" or unicodedata.category(c) in ("Zs", "Zl", "Zp")


def _kt_trim(s: str) -> str:
    """Kotlin String.trim()."""
    i, j = 0, len(s)
    while i < j and _kt_ws(s[i]):
        i += 1
    while j > i and _kt_ws(s[j - 1]):
        j -= 1
    return s[i:j]


def normalize_ctype(value: object) -> str:
    """The key SeforimLibrary looks a Conection Type up by (Link.kt): Kotlin trim,
    lowercase, ' ' -> '_'. null / missing -> "" (generator: coerceInputValues)."""
    return _kt_trim("" if value is None else str(value)).lower().replace(" ", "_")


# ערכים שנראים נכונים אבל אינם ConnectionType (Link.kt `fromKnownStringOrNull`).
# הם נופלים ל-OTHER, ו-OTHER נפסל ב-`LinkTypes.isDependentTextLink` — כלומר
# הקישור לא יוצג כמפרש, ולא ייכנס למנגנון סמני-ההערות הממוספרות.
TRAP_TYPES = {
    "sifrei_mitsvot": 'איות שגוי — הערך המוכר הוא "sifrei mitzvot" (z, לא s)',
    "note": 'אינו ConnectionType. הערך הנכון הוא "footnotes"',
    "notes": 'אינו ConnectionType. הערך הנכון הוא "footnotes"',
}

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
        raw_ctype = entry.get("Conection Type", "")
        ctype = normalize_ctype(raw_ctype)
        if ctype in TRAP_TYPES:
            err(f"{tag}: סוג קשר {raw_ctype!r} — {TRAP_TYPES[ctype]}. "
                f"הוא ייכתב כ-OTHER, ו-isDependentTextLink יפסול אותו: הקישור לא יוצג כמפרש")
        elif ctype and ctype not in DEPENDENT_TYPES and ctype not in REFERENCE_TYPES:
            warn(f"{tag}: סוג קשר לא מוכר ({raw_ctype!r}) — ייכתב כ-OTHER")
        # Direction: a citing-named file (line_index_1 = the מפרש) must declare "source";
        # "commentary"/"super_commentary" there get no flip and store the pair backwards.
        # A base-named file (line_index_1 = the base text) is the opposite. The file name
        # decides which is right, so warn rather than fail.
        stem = path.name[: -len("_links.json")] if path.name.endswith("_links.json") else ""
        raw_p2 = str(entry.get("path_2", "")).replace("\\", "/")
        tgt = raw_p2.rsplit("/", 1)[-1]
        if tgt.endswith(".txt"):
            tgt = tgt[:-4]
        if ctype in {"commentary", "super_commentary", "supercommentary"} and tgt and tgt in stem and tgt != stem:
            err(f"{tag}: הקובץ קרוי על שם המפרש ו-{raw_ctype!r} נשמר בכיוון הפוך — "
                f"הערך הנכון הוא 'source'")

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

    check_companion_merge(path, data, book, src_lines, target, tgt_lines)
    print(f"{path.name}: {len(data)} רשומות")


def _target_title(entry: dict) -> str:
    title = str(entry.get("path_2", "")).replace("\\", "/").rsplit("/", 1)[-1]
    return title[:-4] if title.endswith(".txt") else title


def check_companion_merge(path: Path, data: list, book: Path | None, src_lines: list[str] | None,
                          target: Path | None, tgt_lines: list[str] | None) -> None:
    """חוזה המיזוג של HearotCompanionMerge (ADDING_BOOKS.md סעיף 3): כישלון משאיר את
    ספר ההערות עצמאי, בשקט, והסמנים בגוף הספר לא מציגים את ההערה בריחוף."""
    notes = [e for e in data if isinstance(e, dict)
             and normalize_ctype(e.get("Conection Type")) in {"footnotes", "footnote"}]
    for title in sorted({_target_title(e) for e in notes}):
        if title and not title.startswith(COMPANION_PREFIX):
            warn(f"{path.name}: ספר ההערות {title!r} אינו מתחיל ב-'{COMPANION_PREFIX}' — "
                 f"הוא לא ימוזג לספר הבסיס ויישאר ספר עצמאי")
    if tgt_lines is not None and target is not None:
        own = [e for e in notes if _target_title(e) == target.stem]
        if own:
            linked = {e.get("line_index_2") for e in own}
            unlinked = [i for i, l in enumerate(tgt_lines, 1)
                        if i not in linked and l.strip() and not HEADING_RE.match(l)]
            if unlinked:
                err(f"{target.name}: {len(unlinked)} שורות בלי קישור (הראשונה: {unlinked[0]}) — "
                    f"המיזוג נפסל לכל הכרך. שורת קרדיט/זכויות שייכת לספר הבסיס")
            for i in sorted(x for x in linked if isinstance(x, int) and 1 <= x <= len(tgt_lines)):
                if re.search(r"<i[\s>]|</i>", tgt_lines[i - 1]):
                    err(f"{target.name}: שורה {i} — <i> בגוף ההערה פוסל את המיזוג")
                    break
    if src_lines is not None and book is not None:
        for e in notes:
            li = e.get("line_index_1")
            if isinstance(li, int) and 1 <= li <= len(src_lines) and 'class="footnote' in src_lines[li - 1]:
                err(f"{book.name}: שורה {li} כבר נושאת הערות inline — המיזוג נפסל")
                break


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
