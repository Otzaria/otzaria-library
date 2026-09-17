#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""פיצול כותרות שנדבקו לאמצע שורה — תיקון גנרי לקבצי "ים החכמה".

בעיית המקור
-----------
בקבצי המאגר של ים החכמה (https://github.com/torahtyh/yam-HaHachma) תגי הכותרת
`<hN>…</hN>` מופיעים לא פעם **בתוך** שורת גוף, בדרך כלל בסופה (הכותרת הבאה נדבקה
לסוף הפסקה הקודמת), ולעיתים באמצעה (כותרת ואחריה המשך הפסקה). באוצריא שורה נחשבת
כותרת רק אם היא **מתחילה** ב-`<hN` (`lib/utils/file/toc_parser.dart`), וכל טקסט
שנשאר באותה שורה אחרי `</hN>` נבלע לתוך שם הכותרת בתוכן העניינים. לכן כותרת
כזו פשוט לא מגיעה לתוכן העניינים — או מגיעה מעוותת.

מה הסקריפט עושה
---------------
עובר שורה-שורה ומפצל כל שורה לשלושה סוגי מקטעים לפי מיקום תגי הכותרת:
טקסט שלפני הכותרת → שורה משלו, הכותרת → שורה משלה, וההמשך → שורה משלה.
כך כל כותרת יושבת לבדה בתחילת שורה, ולשון גוף הספר אינה משתנה — רק חלוקת השורות.

בנוסף (ברירת מחדל, ניתן לכבות):
* `--normalize-heading-text` — כיווץ רווחים בתוך טקסט הכותרת.
* `--strip-empty` — השמטת שורות שנותרו ריקות אחרי הפיצול.
* `--author "שם"` — הזרקת שורת מחבר כשורה 2 (אחרי ה-`<h1>`), אם אין כזו.
* `--trailing-newline` — הבטחת ירידת שורה בסוף הקובץ.

הסקריפט עורך **במקום** (in-place) ומדפיס סיכום: כמה כותרות פוצלו וכמה שורות נוספו.

שימוש
-----
    python3 -X utf8 split_inline_headings.py "ספר.txt" --author "פלוני, אלמוני בן פלוני"
    python3 -X utf8 split_inline_headings.py "ספר.txt" --dry-run
"""

import argparse
import re
import sys

HEADING_RE = re.compile(r"<h([1-6])(\s[^>]*)?>(.*?)</h\1\s*>", re.DOTALL)
HEADING_OPEN_RE = re.compile(r"<h[1-6](\s[^>]*)?>")


def unmatched_heading_lines(lines):
    """מספרי שורות שבהן יש פתיחת <hN> שאין לה סגירה תואמת באותה שורה.

    כותרת כזו (למשל תג שנפתח בשורה אחת ונסגר בשורה אחרת) אינה מפוצלת על ידי
    הסקריפט — היא מדווחת בלבד, כדי שלא תישאר בלי טיפול בשקט.
    """
    bad = []
    for idx, line in enumerate(lines, 1):
        opens = len(HEADING_OPEN_RE.findall(line))
        pairs = len(HEADING_RE.findall(line))
        if opens != pairs:
            bad.append(idx)
    return bad


def split_line(line, normalize_heading_text=True):
    """מחזיר רשימת שורות עבור שורה אחת; כל כותרת בשורה נפרדת."""
    out = []
    pos = 0
    found = 0
    for m in HEADING_RE.finditer(line):
        before = line[pos:m.start()].strip()
        if before:
            out.append(before)
        level, attrs, text = m.group(1), m.group(2) or "", m.group(3)
        if normalize_heading_text:
            text = re.sub(r"\s+", " ", text).strip()
        out.append("<h{0}{1}>{2}</h{0}>".format(level, attrs, text))
        pos = m.end()
        found += 1
    tail = line[pos:].strip()
    if tail:
        out.append(tail)
    if not found:
        return [line], 0
    return out, found


def process(text, normalize_heading_text=True, strip_empty=True, author=None):
    lines = text.split("\n")
    result = []
    split_count = 0
    for line in lines:
        pieces, found = split_line(line, normalize_heading_text)
        if found and len(pieces) > 1:
            split_count += len(pieces) - 1
        for p in pieces:
            if strip_empty and not p.strip():
                continue
            result.append(p)
    if author:
        if result and result[0].lstrip().startswith("<h1"):
            has_author = len(result) > 1 and result[1].strip() == author
            starts_heading = len(result) > 1 and result[1].lstrip().startswith("<h")
            if not has_author and starts_heading:
                result.insert(1, author)
    return result, split_count


def main(argv=None):
    ap = argparse.ArgumentParser(description="פיצול כותרות inline לשורות נפרדות")
    ap.add_argument("path", help="נתיב לקובץ הספר (נערך במקום)")
    ap.add_argument("--author", help="שורת מחבר להזרקה כשורה 2 אם חסרה")
    ap.add_argument("--keep-empty", action="store_true", help="לא להשמיט שורות ריקות")
    ap.add_argument("--no-normalize-heading-text", action="store_true",
                    help="לא לכווץ רווחים בטקסט הכותרת")
    ap.add_argument("--no-trailing-newline", action="store_true",
                    help="לא להוסיף ירידת שורה בסוף הקובץ")
    ap.add_argument("--dry-run", action="store_true", help="רק לדווח, בלי לכתוב")
    args = ap.parse_args(argv)

    with open(args.path, encoding="utf-8") as fh:
        text = fh.read()
    src_lines = text.split("\n")
    before_lines = len(src_lines)
    unmatched = unmatched_heading_lines(src_lines)

    result, split_count = process(
        text,
        normalize_heading_text=not args.no_normalize_heading_text,
        strip_empty=not args.keep_empty,
        author=args.author,
    )

    out = "\n".join(result)
    if not args.no_trailing_newline:
        out += "\n"

    print("שורות לפני: {}  שורות אחרי: {}  פיצולים: {}".format(
        before_lines, len(result), split_count))
    if unmatched:
        print("אזהרה: {} שורות עם <hN> בלי סגירה תואמת באותה שורה (לא פוצלו): {}".format(
            len(unmatched), ", ".join(str(n) for n in unmatched[:20])
            + (" …" if len(unmatched) > 20 else "")))

    if args.dry_run:
        return 0
    with open(args.path, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("נכתב: {}".format(args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
