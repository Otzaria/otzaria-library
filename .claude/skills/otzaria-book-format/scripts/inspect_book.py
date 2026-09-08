#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""סקירת מבנה של קובץ ספר באוצריא: עץ כותרות, מספרי שורות, סטטיסטיקה, חיפוש שורה.

  python -X utf8 inspect_book.py "ספר.txt" --toc --stats
  python -X utf8 inspect_book.py "ספר.txt" --line 42 --context 2
  python -X utf8 inspect_book.py "ספר.txt" --find "דיבור המתחיל"

זיהוי הכותרות זהה ל-TocParser של האפליקציה: השורה (אחרי trimLeft) מתחילה ב-<h1..h6>,
טקסט הכותרת = כל השורה בלי תגיות, ו-data-toc="none" מוחרג.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADING_RE = re.compile(r"^\s*<\s*h([1-6])\b", re.I)
TAG_RE = re.compile(r"<[^>]+>")
FOOTNOTE_MARKER_RE = re.compile(r"<sup\b[^>]*\bfootnote-marker\b[^>]*>", re.I)
GRAY_MARKER_RE = re.compile(r'<sup style="color: ?gray;">', re.I)


def read_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    out = []
    for i, line in enumerate(lines, start=1):
        m = HEADING_RE.match(line)
        if not m:
            continue
        head = line[: line.find(">") + 1].lower()
        if 'data-toc="none"' in head:
            continue
        out.append((i, int(m.group(1)), TAG_RE.sub("", line).strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="סקירת מבנה של ספר אוצריא")
    ap.add_argument("path")
    ap.add_argument("--toc", action="store_true", help="עץ תוכן העניינים עם מספרי שורות")
    ap.add_argument("--stats", action="store_true", help="סטטיסטיקה")
    ap.add_argument("--line", type=int, help="הצגת שורה לפי מספר (1-based)")
    ap.add_argument("--context", type=int, default=0, help="שורות הקשר סביב --line")
    ap.add_argument("--find", help="חיפוש טקסט והחזרת מספרי השורות")
    ap.add_argument("--max-depth", type=int, default=6)
    args = ap.parse_args()

    path = Path(args.path)
    lines = read_lines(path)
    hs = headings(lines)

    if not any([args.toc, args.stats, args.line, args.find]):
        args.toc = args.stats = True

    if args.stats:
        content = [l for l in lines if l.strip() and not HEADING_RE.match(l)]
        blanks = sum(1 for l in lines if not l.strip())
        inline_notes = sum(len(FOOTNOTE_MARKER_RE.findall(l)) for l in lines)
        gray_notes = sum(len(GRAY_MARKER_RE.findall(l)) for l in lines)
        chars = sum(len(TAG_RE.sub("", l)) for l in lines)
        print(f"קובץ: {path.name}")
        print(f"  שורות סה\"כ: {len(lines)} | תוכן: {len(content)} | כותרות: {len(hs)} | ריקות: {blanks}")
        print(f"  תווים (בלי תגיות): {chars:,}")
        print(f"  הערות inline: {inline_notes} | סמני הערה אפורים (מנגנון קובץ נפרד): {gray_notes}")
        levels = sorted({lvl for _, lvl, _ in hs})
        print(f"  רמות כותרת בשימוש: {levels if levels else 'אין'}")
        skips = [(ln, prev, lvl) for (ln, lvl, _), prev in
                 zip(hs, [0] + [x[1] for x in hs]) if prev and lvl > prev + 1]
        if skips:
            print("  ⚠ דילוגי רמה: " + ", ".join(f"שורה {ln}: h{p}→h{l}" for ln, p, l in skips))

    if args.toc:
        print("תוכן העניינים:")
        for ln, lvl, text in hs:
            if lvl > args.max_depth:
                continue
            print(f"  {'  ' * (lvl - 1)}h{lvl} [{ln}] {text}")

    if args.line:
        lo = max(1, args.line - args.context)
        hi = min(len(lines), args.line + args.context)
        for i in range(lo, hi + 1):
            mark = ">>" if i == args.line else "  "
            print(f"{mark} {i}: {lines[i - 1]}")

    if args.find:
        needle = args.find
        hits = [(i, l) for i, l in enumerate(lines, start=1) if needle in l]
        print(f"נמצאו {len(hits)} שורות עבור {needle!r}:")
        for i, l in hits[:50]:
            print(f"  {i}: {l[:160]}")
        if len(hits) > 50:
            print(f"  … ועוד {len(hits) - 50}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
