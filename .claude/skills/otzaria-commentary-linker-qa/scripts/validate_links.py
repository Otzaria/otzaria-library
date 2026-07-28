#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic QA for Otzaria commentary `_links.json` files.

Checks: JSON/schema, duplicates, completeness vs citing text, file-derived heRef
(for primary target), optional seforim.db heRef sampling across all path_2 titles,
super-commentary attribution scan (רש"י/תוס'/בד"ה → not Gemara).

Does NOT fully judge semantic match quality — that remains LLM/manual per SKILL.md.

Example:
  python validate_links.py \\
    --links path/to/X_links.json \\
    --citing path/to/X.txt \\
    --target path/to/Y.txt \\
    --skip-line 2 \\
    --db "%APPDATA%/io.github.kdroidfilter.seforimapp/databases/seforim.db"

Batch / multi-path tip: pass the Gemara as --target; super_commentary rows may point
at רש"י/תוספות — those are allowed and checked via --scan-super + DB sample.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXPECTED_KEYS = {"line_index_1", "line_index_2", "heRef_2", "path_2", "Conection Type"}
HEADER_RE = re.compile(r"^<h([1-6])>(.*?)</h\1>\s*$", re.I)
# Generic placeholders / colophons. Author bylines are book-specific — pass --skip-line
# and/or rely on short-line-after-h1 heuristics via --auto-byline-max-len.
PLACEHOLDER_RE = re.compile(r"@@@חסר\s*עמוד\s*מקורי@@@", re.I)
COLOPHON_RE = re.compile(
    r"^\s*(?:סליק\s+מסכת\b|תם\s+ונשלם\b|סליק\b)",
    re.I,
)

# Explicit intermediate + ד"ה. NOTE: the connective between the commentator's name and
# ד"ה is very often "ב" fused onto ד"ה itself (e.g. "רש\"י בד\"ה X" = "Rashi, in the
# dibur-hamatchil X"), not a bare space before ד"ה — every alternative below allows an
# optional ב there (`ב?ד["״]ה`). A regex that requires ד"ה immediately after the name
# (no ב) silently fails to flag real openers and is exactly how a past run's super-scan
# reported 0 problems while ~32 explicit-opener lines were still wrongly linked to the
# Gemara (confirmed case: אבן העוזר על תלמוד בבלי, round-3 audit). Also covers רשב"ם
# (the running commentary after Rashi ends, e.g. in Bava Batra) and חוס' (a recurring
# print/OCR variant of תוס' seen in at least one source) — both were missing here too.
EXPLICIT_SUPER_RE = re.compile(
    r"""^\s*(?:
        <b>\s*(?:ב?תוס['׳]?|ותוס['׳]?|תוספות|בתוספות|ותוספות|
                 ב?חוס['׳]?|ותוס['׳]?|
                 ב?רש["״]י|ורש["״]י|
                 ב?רשב["״]ם|ורשב["״]ם|
                 תוספות\s*ישנים)\s*</b>\s*ב?ד["״]ה
      | <b>\s*(?:ב?תוס['׳]?|ותוס['׳]?|תוספות|ב?חוס['׳]?|ב?רש["״]י|ב?רשב["״]ם|תוספות\s*ישנים)\s+ב?ד["״]ה
      | (?:ב?תוס['׳]?|ותוס['׳]?|תוספות|ב?חוס['׳]?|ב?רש["״]י|ב?רשב["״]ם)\s*ב?ד["״]ה
    )""",
    re.I | re.X,
)
# Bare continuation (no commentator name at all — inherits whichever intermediate book
# the run was already in). Allow both "ד\"ה X" and the far more common "בד\"ה X", and the
# composite "שם בד\"ה X" form.
BDH_RE = re.compile(
    r'^\s*(?:<b>\s*)?(?:שם\s+)?(?:<b>\s*)?ב?ד["״]ה(?:\s*</b>)?\b',
    re.I,
)
# Primary-text labels that reset "current intermediate commentator" inheritance
PRIMARY_LABEL_RE = re.compile(
    r'^\s*<b>\s*(?:ב?גמרא|בגמ[\'׳]?|במשנה|משנה|פסוק|תורה|נביא|כתובים)\s*</b>',
    re.I,
)

GEMATRIA = [
    "א", "ב", "ג", "ד", "ה", "ו", "ז", "ח", "ט", "י",
    "יא", "יב", "יג", "יד", "טו", "טז", "יז", "יח", "יט", "כ",
    "כא", "כב", "כג", "כד", "כה", "כו", "כז", "כח", "כט", "ל",
    "לא", "לב", "לג", "לד", "לה", "לו", "לז", "לח", "לט", "מ",
    "מא", "מב", "מג", "מד", "מה", "מו", "מז", "מח", "מט", "נ",
    "נא", "נב", "נג", "נד", "נה", "נו", "נז", "נח", "נט", "ס",
    "סא", "סב", "סג", "סד", "סה", "סו", "סז", "סח", "סט", "ע",
    "עא", "עב", "עג", "עד", "עה", "עו", "עז", "עח", "עט", "פ",
    "פא", "פב", "פג", "פד", "פה", "פו", "פז", "פח", "פט", "צ",
    "צא", "צב", "צג", "צד", "צה", "צו", "צז", "צח", "צט", "ק",
]


def to_gematria(n: int) -> str:
    if 1 <= n <= len(GEMATRIA):
        return GEMATRIA[n - 1]
    rem, parts = n, []
    for val, let in [
        (400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"), (90, "צ"), (80, "פ"),
        (70, "ע"), (60, "ס"), (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"),
        (10, "י"), (9, "ט"), (8, "ח"), (7, "ז"), (6, "ו"), (5, "ה"),
        (4, "ד"), (3, "ג"), (2, "ב"), (1, "א"),
    ]:
        while rem >= val:
            parts.append(let)
            rem -= val
    s = "".join(parts)
    return s.replace("יה", "טו").replace("יו", "טז")


def load_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def is_header(line: str) -> bool:
    return bool(HEADER_RE.match(line.strip()))


def is_blank(line: str) -> bool:
    return line.strip() == ""


def is_front_matter(line: str, *, byline_max_len: int, line_index: int, lines: list[str]) -> bool:
    """Generic skips: placeholders, colophons, and a short byline right under <h1>."""
    s = line.strip()
    if not s:
        return False
    if PLACEHOLDER_RE.search(s) or (s.startswith("@@@") and "חסר" in s):
        return True
    plain = re.sub(r"<[^>]+>", "", s).strip()
    if COLOPHON_RE.match(plain):
        return True
    # Short non-heading line immediately after <h1> is usually an author byline
    if (
        byline_max_len > 0
        and line_index == 2
        and len(lines) >= 1
        and is_header(lines[0])
        and HEADER_RE.match(lines[0].strip())
        and int(HEADER_RE.match(lines[0].strip()).group(1)) == 1
        and len(s) <= byline_max_len
        and not is_header(s)
    ):
        return True
    return False


def content_indices(
    lines: list[str],
    skip: set[int],
    auto_front_matter: bool,
    byline_max_len: int,
) -> list[int]:
    out = []
    for i, raw in enumerate(lines, start=1):
        if i in skip or is_blank(raw) or is_header(raw):
            continue
        if auto_front_matter and is_front_matter(
            raw, byline_max_len=byline_max_len, line_index=i, lines=lines
        ):
            continue
        out.append(i)
    return out


def derive_herefs(target_lines: list[str], book_title: str) -> dict[int, str]:
    """1-based physical line -> heRef for non-h1/h2 lines after an h2 section starts."""
    herefs: dict[int, str] = {}
    current_h2: str | None = None
    counter = 0
    for i, raw in enumerate(target_lines, start=1):
        m = HEADER_RE.match(raw.strip())
        if m:
            level = int(m.group(1))
            content = m.group(2).strip()
            if level == 1:
                continue
            if level == 2:
                label = re.sub(r"^דף\s+", "", content)
                current_h2 = label
                counter = 0
                continue
        if current_h2 is None:
            continue
        if m and int(m.group(1)) <= 2:
            continue
        counter += 1
        herefs[i] = f"{book_title} {current_h2}, {to_gematria(counter)}"
    return herefs


def guess_book_title(target_path: Path, target_lines: list[str]) -> str:
    if target_lines:
        m = HEADER_RE.match(target_lines[0].strip())
        if m and int(m.group(1)) == 1:
            return m.group(2).strip()
    return target_path.stem


def title_variants(title: str) -> list[str]:
    variants = [title]
    if title.startswith("רשי "):
        variants.append('רש"י ' + title[4:])
    if title.startswith("רשבם "):
        variants.append('רשב"ם ' + title[5:])
    return list(dict.fromkeys(variants))


def resolve_book_id(conn: sqlite3.Connection, title: str) -> int | None:
    for variant in title_variants(title):
        row = conn.execute(
            "SELECT id, title FROM book WHERE title = ? LIMIT 1", (variant,)
        ).fetchone()
        if row:
            return int(row[0])
    rows_by_id = {}
    for variant in title_variants(title):
        for row in conn.execute(
            "SELECT id, title FROM book WHERE title LIKE ? LIMIT 5", (f"%{variant}%",)
        ).fetchall():
            rows_by_id[int(row[0])] = row
    if len(rows_by_id) == 1:
        return next(iter(rows_by_id))
    return None


def path_title(path2: str) -> str:
    return path2[:-4] if path2.endswith(".txt") else path2


def is_intermediate_path(path2: str) -> bool:
    return any(x in path2 for x in ('רש"י', "רשי", "תוספות", "תוס'", "ישנים", 'רשב"ם', "רשבם"))


def super_kind(line: str) -> str | None:
    s = line.strip()
    if EXPLICIT_SUPER_RE.match(s):
        return "explicit"
    if BDH_RE.match(s):
        return "bdh"
    return None


def first_words(s: str, n: int = 16) -> str:
    t = re.sub(r"<[^>]+>", "", s or "")
    t = re.sub(r"\s+", " ", t).strip()
    return " ".join(t.split()[:n])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--links", required=True, type=Path)
    p.add_argument("--citing", required=True, type=Path)
    p.add_argument("--target", required=True, type=Path, help="Primary (Gemara) target .txt")
    p.add_argument("--skip-line", action="append", type=int, default=[], dest="skip_lines")
    p.add_argument(
        "--no-auto-front-matter",
        action="store_true",
        help="Do not auto-skip byline-under-h1 / colophons / @@@חסר@@@",
    )
    p.add_argument(
        "--auto-byline-max-len",
        type=int,
        default=80,
        help="If >0, treat a short line 2 under <h1> as author byline (0 disables)",
    )
    p.add_argument("--db", type=Path, default=None)
    p.add_argument("--book-id", type=int, default=None, help="Override primary target bookId")
    p.add_argument("--book-title", default=None, help="Override primary title for heRef/DB")
    p.add_argument("--db-sample", type=int, default=20, help="Random DB heRef samples across path_2")
    p.add_argument("--scan-super", action="store_true", default=True,
                   help="Scan רש\"י/תוס'/בד\"ה attribution (default on)")
    p.add_argument("--no-scan-super", action="store_true", help="Disable super-attribution scan")
    p.add_argument("--expected-linker", type=int, default=None,
                   help="Expected count of Conection Type=linker entries")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    random.seed(args.seed)
    scan_super = args.scan_super and not args.no_scan_super
    auto_fm = not args.no_auto_front_matter
    byline_max = args.auto_byline_max_len

    issues: list[dict] = []
    stats: dict = {}

    # --- source integrity ---
    if not args.citing.is_file() or args.citing.stat().st_size == 0:
        print(json.dumps({
            "ok": False,
            "error": f"citing missing or empty: {args.citing}",
        }, ensure_ascii=False))
        return 2
    if args.links.name.endswith(".links.json"):
        issues.append({
            "severity": "blocker", "check": "source_integrity", "line_index_1": None,
            "summary": f"bad links filename {args.links.name!r} — expected *_links.json",
        })
    bad_sibling = args.links.with_name(args.links.name.replace("_links.json", ".links.json"))
    if bad_sibling.is_file() and bad_sibling != args.links:
        issues.append({
            "severity": "blocker", "check": "source_integrity", "line_index_1": None,
            "summary": f"leftover bad-name file exists: {bad_sibling.name}",
        })

    skip = set(args.skip_lines)
    citing = load_lines(args.citing)
    target = load_lines(args.target)

    if citing:
        h1 = citing[0].strip()
        if not HEADER_RE.match(h1):
            issues.append({
                "severity": "major", "check": "source_integrity", "line_index_1": 1,
                "summary": f"citing line 1 is not <h1>: {first_words(h1, 12)!r}",
            })
    hebrew = sum(1 for c in "".join(citing) if "\u0590" <= c <= "\u05FF")
    if hebrew < 200:
        issues.append({
            "severity": "blocker", "check": "source_integrity", "line_index_1": None,
            "summary": f"citing has too little Hebrew content ({hebrew} letters)",
        })
    stats["citing_bytes"] = args.citing.stat().st_size
    stats["citing_lines"] = len(citing)
    stats["citing_hebrew_letters"] = hebrew

    try:
        links = json.loads(args.links.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"JSON parse failed: {e}"}, ensure_ascii=False))
        return 2

    if not isinstance(links, list):
        print(json.dumps({"ok": False, "error": "links root must be a JSON array"}, ensure_ascii=False))
        return 2

    book_title = args.book_title or guess_book_title(args.target, target)
    expected_path2 = f"{args.target.stem}.txt"

    type_counts: Counter = Counter()
    commentary_like: list[dict] = []
    linker_entries: list[dict] = []

    for idx, e in enumerate(links):
        if not isinstance(e, dict):
            issues.append({
                "severity": "blocker", "check": "schema", "line_index_1": None,
                "summary": f"entry #{idx} is not an object",
            })
            continue
        ctype = e.get("Conection Type")
        type_counts[ctype] += 1
        keys = set(e.keys())

        if "Conection Type" not in e and "Connection Type" in e:
            issues.append({
                "severity": "blocker", "check": "schema",
                "line_index_1": e.get("line_index_1"),
                "summary": 'uses "Connection Type" — app expects misspelled "Conection Type"',
            })

        if ctype == "linker":
            linker_entries.append(e)
            for req in EXPECTED_KEYS:
                if req not in e:
                    issues.append({
                        "severity": "blocker", "check": "schema",
                        "line_index_1": e.get("line_index_1"),
                        "summary": f"linker entry missing {req}",
                    })
            continue

        commentary_like.append(e)
        required_ok = EXPECTED_KEYS <= keys
        unknown = keys - EXPECTED_KEYS - {
            "start", "end", "line_index_1_end", "line_index_2_end", "heRef_1", "path_1",
        }
        # Prefer exactly 5 keys for commentary/super_commentary
        if keys != EXPECTED_KEYS:
            if not required_ok:
                issues.append({
                    "severity": "blocker", "check": "schema",
                    "line_index_1": e.get("line_index_1"),
                    "summary": f"missing keys: {sorted(EXPECTED_KEYS - keys)}",
                })
            elif unknown:
                issues.append({
                    "severity": "info", "check": "schema",
                    "line_index_1": e.get("line_index_1"),
                    "summary": f"unexpected keys: {sorted(unknown)}",
                })
            elif keys != EXPECTED_KEYS:
                # has extras that are known optional — already handled
                pass

        if ctype not in ("commentary", "super_commentary"):
            issues.append({
                "severity": "major", "check": "schema",
                "line_index_1": e.get("line_index_1"),
                "summary": f"unexpected Conection Type: {ctype!r}",
            })

        for k in ("line_index_1", "line_index_2"):
            if k in e and not isinstance(e[k], int):
                issues.append({
                    "severity": "blocker", "check": "schema",
                    "line_index_1": e.get("line_index_1"),
                    "summary": f"{k} is not int: {e[k]!r}",
                })

        # path_2 may be Gemara OR intermediate book for super_commentary
        path2 = e.get("path_2")
        if path2 and path2 != expected_path2:
            if ctype == "super_commentary" and is_intermediate_path(path2):
                pass  # expected
            elif ctype == "super_commentary":
                issues.append({
                    "severity": "major", "check": "schema",
                    "line_index_1": e.get("line_index_1"),
                    "summary": f"super_commentary path_2={path2!r} is not Rashi/Tosafot-like",
                })
            else:
                issues.append({
                    "severity": "major", "check": "schema",
                    "line_index_1": e.get("line_index_1"),
                    "summary": f"path_2={path2!r} (expected {expected_path2!r} for commentary)",
                })

    stats["type_counts"] = dict(type_counts)
    if args.expected_linker is not None:
        got = type_counts.get("linker", 0)
        if got != args.expected_linker:
            issues.append({
                "severity": "major", "check": "linker_preserve", "line_index_1": None,
                "summary": f"linker count {got} != expected {args.expected_linker}",
            })

    # duplicates among commentary+super only
    c1 = Counter(e.get("line_index_1") for e in commentary_like)
    for d, n in c1.items():
        if d is None:
            continue
        if n > 1:
            issues.append({
                "severity": "blocker", "check": "duplicates",
                "line_index_1": d, "summary": f"appears {n} times among commentary/super",
            })

    auto_skipped = []
    if auto_fm:
        for i, raw in enumerate(citing, start=1):
            if (
                i not in skip
                and not is_blank(raw)
                and not is_header(raw)
                and is_front_matter(
                    raw, byline_max_len=byline_max, line_index=i, lines=citing
                )
            ):
                auto_skipped.append(i)
    stats["auto_skipped_front_matter"] = auto_skipped

    expected = set(content_indices(citing, skip, auto_fm, byline_max))
    actual = {k for k in c1 if isinstance(k, int)}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    stats["citing_content_lines"] = len(expected)
    stats["link_entries_commentary_like"] = len(commentary_like)
    stats["link_entries_total"] = len(links)
    stats["missing_count"] = len(missing)
    stats["extra_count"] = len(extra)
    stats["duplicate_line_index_1"] = sorted(
        k for k, n in c1.items() if isinstance(k, int) and n > 1
    )

    for m in missing[:100]:
        issues.append({
            "severity": "blocker", "check": "completeness",
            "line_index_1": m, "summary": "content line missing from links",
            "preview": citing[m - 1][:160] if 1 <= m <= len(citing) else "",
        })
    if len(missing) > 100:
        issues.append({
            "severity": "blocker", "check": "completeness", "line_index_1": None,
            "summary": f"...and {len(missing) - 100} more missing (total {len(missing)})",
        })
    for x in extra:
        issues.append({
            "severity": "major", "check": "completeness",
            "line_index_1": x,
            "summary": "line_index_1 is not an expected content line (header/blank/skipped)",
            "preview": citing[x - 1][:160] if 1 <= x <= len(citing) else "",
        })

    # file-derived heRef for primary Gemara path only
    derived = derive_herefs(target, book_title)
    file_mismatch = 0
    for e in commentary_like:
        if e.get("path_2") != expected_path2:
            continue
        li1, li2 = e.get("line_index_1"), e.get("line_index_2")
        if not isinstance(li2, int):
            continue
        exp = derived.get(li2)
        got = e.get("heRef_2")
        if exp is None:
            issues.append({
                "severity": "major", "check": "heRef_file",
                "line_index_1": li1,
                "summary": f"line_index_2={li2} has no derived heRef (out of range / before first h2)",
            })
            file_mismatch += 1
        elif got != exp:
            file_mismatch += 1
            if file_mismatch <= 30:
                issues.append({
                    "severity": "major", "check": "heRef_file",
                    "line_index_1": li1,
                    "summary": f"heRef_2={got!r} != file-derived={exp!r} (line_index_2={li2})",
                })
    if file_mismatch > 30:
        issues.append({
            "severity": "major", "check": "heRef_file", "line_index_1": None,
            "summary": f"...and more heRef_file mismatches (total {file_mismatch})",
        })
    stats["heref_file_mismatches"] = file_mismatch
    stats["book_title_used"] = book_title

    # --- super-attribution scan ---
    by_li1 = {e["line_index_1"]: e for e in commentary_like if isinstance(e.get("line_index_1"), int)}
    super_wrong: list[dict] = []
    super_ok = 0
    super_candidates = 0
    if scan_super:
        last_intermediate: str | None = None
        for i, raw in enumerate(citing, start=1):
            if is_blank(raw) or is_header(raw):
                last_intermediate = None
                continue
            if PRIMARY_LABEL_RE.match(raw.strip()):
                last_intermediate = None
            kind = super_kind(raw)
            if not kind:
                # track explicit intermediate mentions for inheritance hint
                if EXPLICIT_SUPER_RE.match(raw.strip()) or (
                    'רש"י' in raw[:40] or "תוס" in raw[:40]
                ):
                    if "רש" in raw[:50]:
                        last_intermediate = "rashi"
                    elif "תוס" in raw[:50]:
                        last_intermediate = "tosafot"
                continue
            super_candidates += 1
            e = by_li1.get(i)
            if not e:
                super_wrong.append({
                    "line_index_1": i, "kind": kind,
                    "issue": "NO_ENTRY", "preview": first_words(raw),
                })
                continue
            ctype = e.get("Conection Type")
            path2 = e.get("path_2") or ""
            ok = ctype == "super_commentary" and is_intermediate_path(path2)
            if ok:
                super_ok += 1
            else:
                super_wrong.append({
                    "line_index_1": i,
                    "kind": kind,
                    "issue": "SHOULD_BE_SUPER_COMMENTARY",
                    "Conection Type": ctype,
                    "path_2": path2,
                    "heRef_2": e.get("heRef_2"),
                    "line_index_2": e.get("line_index_2"),
                    "inferred_intermediate": last_intermediate,
                    "preview": first_words(raw),
                })
                issues.append({
                    "severity": "major",
                    "check": "super_commentary",
                    "line_index_1": i,
                    "summary": (
                        f"{kind} label but type={ctype!r} path_2={path2!r} "
                        f"(expected super_commentary → Rashi/Tosafot)"
                    ),
                    "preview": first_words(raw),
                })
    stats["super_candidates"] = super_candidates
    stats["super_ok"] = super_ok
    stats["super_wrong_count"] = len(super_wrong)

    # --- DB heRef sample across all path_2 ---
    db_path = args.db
    if db_path is None:
        appdata = os.environ.get("APPDATA", "")
        cand = Path(appdata) / "io.github.kdroidfilter.seforimapp" / "databases" / "seforim.db"
        if cand.is_file():
            db_path = cand
    stats["db_path"] = str(db_path) if db_path else None
    db_ok = 0
    db_fail: list[dict] = []
    if db_path and Path(db_path).is_file() and commentary_like:
        conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        sample_n = min(args.db_sample, len(commentary_like))
        sample = random.sample(commentary_like, sample_n)
        # force some supers
        supers = [e for e in commentary_like if e.get("Conection Type") == "super_commentary"]
        for e in random.sample(supers, min(5, len(supers))):
            if e not in sample:
                sample.append(e)
        book_cache: dict[str, int | None] = {}
        for e in sample:
            title = path_title(e.get("path_2") or "")
            if title not in book_cache:
                if title == book_title and args.book_id is not None:
                    book_cache[title] = args.book_id
                else:
                    book_cache[title] = resolve_book_id(conn, title)
            bid = book_cache[title]
            if bid is None:
                db_fail.append({
                    "line_index_1": e.get("line_index_1"),
                    "issue": "BOOK_NOT_FOUND",
                    "path_2": e.get("path_2"),
                })
                continue
            li2 = e.get("line_index_2")
            if not isinstance(li2, int):
                continue
            row = conn.execute(
                "SELECT heRef FROM line WHERE bookId=? AND lineIndex=?",
                (bid, li2 - 1),
            ).fetchone()
            if not row:
                db_fail.append({
                    "line_index_1": e.get("line_index_1"),
                    "issue": "LINE_NOT_FOUND",
                    "path_2": e.get("path_2"),
                    "line_index_2": li2,
                })
            elif row[0] != e.get("heRef_2"):
                db_fail.append({
                    "line_index_1": e.get("line_index_1"),
                    "issue": "HEREF_MISMATCH",
                    "heRef_2": e.get("heRef_2"),
                    "db_heRef": row[0],
                    "path_2": e.get("path_2"),
                    "line_index_2": li2,
                })
            else:
                db_ok += 1
        for f in db_fail[:25]:
            issues.append({
                "severity": "major", "check": "heRef_db",
                "line_index_1": f.get("line_index_1"),
                "summary": json.dumps(f, ensure_ascii=False),
            })
        if len(db_fail) > 25:
            issues.append({
                "severity": "major", "check": "heRef_db", "line_index_1": None,
                "summary": f"...and more heRef_db failures (total {len(db_fail)})",
            })
        conn.close()
        stats["db_sample_n"] = len(sample)
        stats["db_sample_ok"] = db_ok
        stats["db_sample_fail"] = len(db_fail)
        stats["db_books_resolved"] = {k: v for k, v in book_cache.items()}
    else:
        issues.append({
            "severity": "info", "check": "heRef_db", "line_index_1": None,
            "summary": "DB not available — skipped heRef_db check",
        })
        stats["db_sample_n"] = 0
        stats["db_sample_ok"] = 0
        stats["db_sample_fail"] = 0

    sev = Counter(i["severity"] for i in issues)
    stats["issues_by_severity"] = dict(sev)
    blockers = sev.get("blocker", 0)
    majors = sev.get("major", 0)
    ok = blockers == 0 and majors == 0 and stats["missing_count"] == 0

    report = {
        "ok": ok,
        "stats": stats,
        "missing_line_index_1": missing,
        "extra_line_index_1": extra,
        "super_wrong": super_wrong[:200],
        "issues": issues,
        "note": (
            "Semantic match beyond super-attribution scan is NOT fully checked — "
            "required separately per SKILL.md (sample + low-conf list)."
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
