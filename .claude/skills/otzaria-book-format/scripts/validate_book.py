#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ולידציה של קובץ ספר באוצריא (.txt שורה-אחר-שורה).

מה נבדק (כל כלל מסומן במקורו ב-references/book-file.md):
  * שורה 1 = <h1> לבדה, שורה 2 = מחבר או ריקה
  * איזון תגים בכל שורה בנפרד; מבנים מרובי-חלקים בשורה אחת
  * כותרות: בתחילת השורה, שורה שלמה, בלי דילוג רמות, בלי h7+, בלי Markdown
  * הערות שוליים inline: סמן+גוף צמודים
  * מלכודת ההיפוך RTL: לכל היותר "תיבה" אחת בשורה
  * CSS/תגים שאינם נתמכים; class-ים שמורים

שימוש:
  python -X utf8 validate_book.py "<ספר>.txt" [עוד קבצים/תיקיות] [--json] [--quiet]

קוד יציאה: 0 = אין שגיאות (אזהרות אינן מפילות), 1 = יש שגיאה, 2 = שימוש שגוי.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VOID_TAGS = {"br", "hr", "img", "wbr", "col", "source"}

# התגים שהמדריך הרשמי מתעד כנבדקים. תג שאינו כאן אינו בהכרח שבור — הוא פשוט לא מתועד.
DOCUMENTED_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "b", "strong", "i", "em", "var", "cite", "dfn",
    "big", "small", "u", "ins", "s", "del", "strike", "acronym", "abbr",
    "mark", "sup", "sub", "a", "details", "summary",
    "ol", "ul", "li", "table", "tr", "td", "th", "caption", "thead", "tbody",
    "div", "p", "blockquote", "center", "hr", "pre", "code",
    "br", "img", "ruby", "rt", "rp", "span", "font",
}

RESERVED_CLASSES = {
    "footnote-marker-number", "book-note-marker", "numbered-note-marker",
    "link-anchor", "link-anchor-active", "link-anchor-range",
}

TAG_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)([^>]*)>")
HEADING_OPEN_RE = re.compile(r"^\s*<\s*h([1-9][0-9]?)\b", re.I)
HEADING_FULL_RE = re.compile(r"^\s*<\s*h([1-6])\b[^>]*>(.*?)</\s*h\1\s*>\s*$", re.I | re.S)
MD_HEADING_RE = re.compile(r"^\s*#{1,6}\s+\S")
FOOTNOTE_MARKER_RE = re.compile(r"<sup\b[^>]*\bfootnote-marker\b[^>]*>(.*?)</sup>", re.I | re.S)
FOOTNOTE_BODY_RE = re.compile(r"<i\b[^>]*\bclass\s*=\s*\"[^\"]*\bfootnote\b[^\"]*\"[^>]*>", re.I)
SUP_SUB_RE = re.compile(r"<(sup|sub)\b([^>]*)>(.*?)</\1>", re.I | re.S)
STYLE_ATTR_RE = re.compile(r"style\s*=\s*\"([^\"]*)\"", re.I)
CLASS_ATTR_RE = re.compile(r"class\s*=\s*\"([^\"]*)\"", re.I)

BAD_CSS = [
    (re.compile(r"\b\d*\.?\d+rem\b", re.I), "יחידת rem אינה נתמכת — em או אחוזים"),
    (re.compile(r"font-style\s*:\s*oblique", re.I), "font-style: oblique אינו נתמך — italic"),
    (re.compile(r"font-weight\s*:\s*(bolder|lighter)", re.I), "font-weight: bolder/lighter אינו נתמך — bold או 100-900"),
    (re.compile(r"text-emphasis", re.I), "text-emphasis הופך אותיות והמילה מוצגת הפוכה"),
    (re.compile(r"text-decoration-thickness\s*:\s*[\d.]+px", re.I), "text-decoration-thickness בפיקסלים אינו נתמך — אחוזים"),
    (re.compile(r"\b(position|transform|float|opacity|border-radius|animation|transition)\s*:", re.I), "תכונה שאינה ברשימת ההיתר ואינה נתמכת בקורא"),
    (re.compile(r"rebeccapurple", re.I), "שם הצבע rebeccapurple אינו נתמך — קוד HEX"),
]

SANITIZE_STRIP = re.compile(r"[֑-ׇ]")
SANITIZE_ILLEGAL = re.compile(r"[\\/:*\"״?<>|]")


def sanitize_filename(name: str) -> str:
    """זהה ל-sefariaToOtzaria/סקריפטים/otzaria/utils.py::sanitize_filename."""
    s = SANITIZE_STRIP.sub("", name)
    s = SANITIZE_ILLEGAL.sub("", s)
    s = s.replace("_", " ").replace("''", "").replace("'", "")
    return s.strip()


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


class Report:
    def __init__(self, path: Path):
        self.path = path
        self.errors: list[tuple[int, str]] = []
        self.warnings: list[tuple[int, str]] = []

    def err(self, line: int, msg: str) -> None:
        self.errors.append((line, msg))

    def warn(self, line: int, msg: str) -> None:
        self.warnings.append((line, msg))


def check_balance(line: str, rep: Report, n: int) -> None:
    stack: list[str] = []
    for m in TAG_RE.finditer(line):
        closing, tag, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if tag in VOID_TAGS or attrs.rstrip().endswith("/"):
            continue
        if not closing:
            stack.append(tag)
        else:
            if not stack:
                rep.err(n, f"תג סוגר </{tag}> בלי תג פותח באותה שורה")
                return
            if stack[-1] != tag:
                if tag in stack:
                    rep.warn(n, f"קינון בסדר שגוי: נסגר </{tag}> בעוד <{stack[-1]}> פתוח (הפרסר משחזר, אבל אל תייצרו כך)")
                    while stack and stack[-1] != tag:
                        stack.pop()
                    stack.pop()
                    continue
                rep.err(n, f"תג סוגר </{tag}> בלי תג פותח תואם")
                return
            stack.pop()
    if stack:
        rep.err(n, "תגים שנפתחו ולא נסגרו בשורה: " + ", ".join(f"<{t}>" for t in stack))


def count_boxes(line: str) -> list[str]:
    """מחזיר תיאור לכל 'תיבה' בשורה — מעל אחת = היפוך טקסט ב-RTL."""
    boxes = []
    for m in SUP_SUB_RE.finditer(line):
        inner = strip_tags(m.group(3))
        if inner and not inner.isdigit():
            boxes.append(f"<{m.group(1).lower()}> לא-מספרי ({inner[:12]})")
    for m in STYLE_ATTR_RE.finditer(line):
        if re.search(r"display\s*:\s*inline-block", m.group(1), re.I):
            boxes.append("display:inline-block")
    for m in TAG_RE.finditer(line):
        if m.group(2).lower() == "img" and not m.group(1):
            boxes.append("<img>")
    return boxes


def check_footnotes(line: str, rep: Report, n: int) -> None:
    markers = list(FOOTNOTE_MARKER_RE.finditer(line))
    bodies = list(FOOTNOTE_BODY_RE.finditer(line))
    if not markers and not bodies:
        return
    if len(markers) != len(bodies):
        rep.err(n, f"הערות שוליים לא מאוזנות: {len(markers)} סמנים מול {len(bodies)} גופי הערה")
    for m in markers:
        rest = line[m.end():]
        if not FOOTNOTE_BODY_RE.match(rest.lstrip()):
            rep.err(n, "סמן הערה footnote-marker שאין אחריו <i class=\"footnote\"> צמוד")
        elif rest[:1] == " " or rest[:1] == "\t":
            rep.warn(n, "רווח בין סמן ההערה לגוף ההערה — המדריך דורש צמידות מלאה")
        inner = strip_tags(m.group(1))
        if not inner:
            rep.err(n, "סמן הערה ריק")


def validate_file(path: Path) -> Report:
    rep = Report(path)
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        rep.warn(0, "הקובץ מתחיל ב-BOM")
        raw = raw[3:]
    if b"\r\n" in raw:
        rep.warn(0, "שורות בסיומת CRLF (עדיף LF)")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        rep.err(0, f"הקובץ אינו UTF-8 תקין: {exc}")
        return rep

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    stem = path.stem
    is_notes_file = stem.startswith("הערות על ")

    # --- שורה 1 ו-2 ---
    if not lines:
        rep.err(0, "קובץ ריק")
        return rep
    first = lines[0].lstrip("﻿").strip()
    if is_notes_file:
        if HEADING_OPEN_RE.match(first):
            rep.warn(1, "קובץ הערות שמתחיל בכותרת — הערה N יושבת בשורה N+1; ודאו שה-line_index_2 בקישורים תואם (בקורפוס קיימות שתי המוסכמות)")
    else:
        m1 = HEADING_FULL_RE.match(first)
        if not m1 or m1.group(1) != "1":
            rep.err(1, "שורה 1 חייבת להיות <h1>שם הספר</h1> לבדה")
        else:
            title = strip_tags(m1.group(2))
            if sanitize_filename(title) != sanitize_filename(stem):
                rep.warn(1, f"שם ב-<h1> ({title!r}) שונה משם הקובץ ({stem!r}) גם אחרי ניקוי — ודאו שזה מכוון")
        if len(lines) > 1:
            second = lines[1].strip()
            if second and HEADING_OPEN_RE.match(second):
                rep.warn(2, "שורה 2 היא כותרת — המוסכמה היא שם המחבר או שורה ריקה")

    # --- מעבר על השורות ---
    h1_count = 0
    last_level = 0
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        if line != line.rstrip():
            rep.warn(i, "רווחים בסוף השורה")

        low = line.lower()
        if "<script" in low:
            rep.err(i, "<script> חסום לחלוטין")
        if "<style" in low:
            rep.err(i, "<style> אינו נתמך — אין CSS גלובלי; העיצוב inline בכל שורה")
        if MD_HEADING_RE.match(line):
            rep.err(i, "כותרת בסגנון Markdown — הסולמיות יוצגו כטקסט; השתמשו ב-<h2>..<h6>")

        # כותרות
        hm = HEADING_OPEN_RE.match(line)
        if hm:
            level = int(hm.group(1))
            if level > 6:
                rep.err(i, f"<h{level}> אינו קיים בתקן; מותר h1–h6")
            else:
                full = HEADING_FULL_RE.match(line.strip())
                if not full:
                    rep.err(i, "כותרת שאינה תופסת את השורה כולה — הטקסט שאחריה נבלע לתוך שם הכותרת בתוכן העניינים")
                else:
                    if not strip_tags(full.group(2)):
                        rep.err(i, "כותרת ריקה")
                    if re.search(r"<big\b", full.group(2), re.I):
                        rep.warn(i, "<big> בתוך כותרת — כותרות כבר מוגדלות ומודגשות")
                if level == 1:
                    h1_count += 1
                    if i != 1:
                        rep.warn(i, "<h1> נוסף באמצע הקובץ — המוסכמה היא h1 אחד, בשורה 1")
                excluded = 'data-toc="none"' in line.lower()
                if not excluded and last_level and level > last_level + 1:
                    rep.err(i, f"דילוג רמת כותרת: h{last_level} ← h{level}; הקינון חייב להיות רציף, אחרת הכותרת נשארת בלי הורה בעץ")
                if not excluded:
                    last_level = level

        check_balance(line, rep, i)
        check_footnotes(line, rep, i)

        boxes = count_boxes(line)
        if len(boxes) > 1:
            rep.err(i, "יותר מ'תיבה' אחת בשורה (" + " · ".join(boxes) + ") — הטקסט יוצג הפוך ב-RTL")

        for m in STYLE_ATTR_RE.finditer(line):
            style = m.group(1)
            for rx, msg in BAD_CSS:
                if rx.search(style):
                    rep.err(i, msg)
            if re.search(r"text-align\s*:", style, re.I):
                before = line[:m.start()]
                open_tag = re.findall(r"<\s*([a-zA-Z][a-zA-Z0-9]*)[^>]*$", before)
                if open_tag and open_tag[-1].lower() == "span":
                    rep.err(i, "text-align על <span> אינו עובד — תג בלוק בלבד (div/p/כותרת)")

        for m in CLASS_ATTR_RE.finditer(line):
            for cls in m.group(1).split():
                if cls in RESERVED_CLASSES:
                    rep.err(i, f'class="{cls}" שמור לשימוש פנימי של התוכנה')

        if re.search(r"\sid\s*=\s*\"", line):
            rep.warn(i, "התכונה id אינה משמשת לקישורים באוצריא (הקישור לפי טקסט הכותרת)")

        for m in TAG_RE.finditer(line):
            tag = m.group(2).lower()
            if tag not in DOCUMENTED_TAGS and not re.fullmatch(r"h[1-9][0-9]?", tag):
                rep.warn(i, f"<{tag}> אינו ברשימת התגים המתועדים — בדקו בפועל באפליקציה")

    if not is_notes_file and h1_count == 0:
        rep.err(1, "אין <h1> בקובץ")
    return rep


def gather(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            out.extend(sorted(path.rglob("*.txt")))
        else:
            out.append(path)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ולידציה של קובץ ספר באוצריא")
    ap.add_argument("paths", nargs="+", help="קובץ .txt או תיקייה")
    ap.add_argument("--json", action="store_true", help="פלט JSON")
    ap.add_argument("--quiet", action="store_true", help="רק שגיאות, בלי אזהרות")
    ap.add_argument("--max", type=int, default=10, help="מקסימום מספרי שורה שיוצגו לכל הודעה")
    args = ap.parse_args()

    files = gather(args.paths)
    if not files:
        print("לא נמצאו קבצים", file=sys.stderr)
        return 2

    reports = []
    failed = False
    for f in files:
        if not f.exists():
            print(f"לא קיים: {f}", file=sys.stderr)
            failed = True
            continue
        rep = validate_file(f)
        reports.append(rep)
        if rep.errors:
            failed = True

    if args.json:
        print(json.dumps(
            [{"file": str(r.path),
              "errors": [{"line": l, "message": m} for l, m in r.errors],
              "warnings": [{"line": l, "message": m} for l, m in r.warnings]}
             for r in reports], ensure_ascii=False, indent=2))
        return 1 if failed else 0

    def emit(kind: str, items, limit: int) -> None:
        grouped: dict[str, list[int]] = {}
        for line, msg in items:
            grouped.setdefault(msg, []).append(line)
        for msg, ln in grouped.items():
            head = ", ".join(str(x) for x in ln[:limit])
            more = f" (+עוד {len(ln) - limit} שורות)" if len(ln) > limit else ""
            print(f"  [{kind}] {msg} — שורות {head}{more}")

    for rep in reports:
        print(f"=== {rep.path.name}: {len(rep.errors)} שגיאות, {len(rep.warnings)} אזהרות")
        emit("שגיאה", rep.errors, args.max)
        if not args.quiet:
            emit("אזהרה", rep.warnings, args.max)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
