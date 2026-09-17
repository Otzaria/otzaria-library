#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ביטול כותרות תלושות — תיקון גנרי לקבצי "ים החכמה".

בעיית המקור
-----------
בקבצי המאגר של ים החכמה (https://github.com/torahtyh/yam-HaHachma) הכותרות נגזרו
מהעימוד של הדפוס: כל מה שהודפס גדול, מרוכז או בשורה נפרדת קיבל `<hN>`. לכן מילה
בודדת שהיא **חלק מהמשפט** — למשל המילה "של" בשורות השער ("בית מסחר הספרים / של /
הר"ר שמשון..."), או אות בודדת שנשברה מפסוק — מתויגת ככותרת.

למה זה מזיק: באוצריא תוכן העניינים נבנה מכל שורה שמתחילה ב-`<hN`
(`lib/utils/file/toc_parser.dart`), כך שהרסיסים האלה הופכים לערכים חסרי משמעות
בעץ; ולעיתים הם גם שוברים את רציפות ההיררכיה (h1 ← h3 בלי h2 באמצע),
מה ש-`validate_book.py` מסמן כשגיאה והופך את הכותרת ליתומה בעץ.

מה הסקריפט עושה
---------------
מסיר את תגי הכותרת משורות נבחרות ומחזיר אותן לטקסט רגיל — **בלי לשנות מילה אחת**
מלשון הספר. אפשר גם למזג את השורה המשוחררת לשורה שלפניה או שאחריה, כדי לאחות
משפט שנשבר לשתי שורות (מיזוג = צירוף ברווח יחיד, בלי הוספת תווים).

הבחירה אילו שורות לשחרר היא **מפורשת ובאחריות העורך** — אין כאן היוריסטיקה של
אורך, משום שבספרי ים החכמה כותרות לגיטימיות רבות הן אות בודדת ("א", "ב", "ג"
כמספור סעיפים) או מילה אחת ("שם"). לכן:

* `--line N`   — שורה (לפי מספרה בקובץ המקורי), ניתן לחזור על הדגל.
* `--match RE` — כל שורת כותרת שטקסטה (בלי התגים) תואם ביטוי רגולרי.
* `--merge {none,prev,next}` — מיזוג השורה המשוחררת לשכנה.
* `--dry-run`  — רק דיווח, בלי כתיבה.
* `--no-trailing-newline` — לא להוסיף ירידת שורה בסוף הקובץ.

הסקריפט עורך במקום (in-place) ומדפיס את מספרי השורות שטופלו ואת הטקסט שלהן.

שימוש
-----
    python3 -X utf8 unwrap_stray_headings.py "ספר.txt" --line 5 --dry-run
    python3 -X utf8 unwrap_stray_headings.py "ספר.txt" --line 24 --merge next
    python3 -X utf8 unwrap_stray_headings.py "ספר.txt" --match '^של$'

אחרי ההרצה חובה להריץ שוב:
    python3 -X utf8 .claude/skills/otzaria-book-format/scripts/validate_book.py "ספר.txt"
"""

import argparse
import re
import sys

HEADING_LINE_RE = re.compile(r"^\s*<h([1-6])(\s[^>]*)?>(.*?)</h\1\s*>\s*$", re.DOTALL)


def heading_text(line):
    """טקסט הכותרת אם השורה כולה היא כותרת אחת, אחרת None."""
    m = HEADING_LINE_RE.match(line)
    return None if m is None else m.group(3).strip()


def process(text, line_numbers=(), match_re=None, merge="none"):
    lines = text.split("\n")
    selected = set(line_numbers)
    touched = []

    for idx, line in enumerate(lines):
        n = idx + 1
        txt = heading_text(line)
        if txt is None:
            continue
        if n in selected or (match_re and match_re.search(txt)):
            lines[idx] = txt
            touched.append((n, txt))

    if merge != "none" and touched:
        # ממזגים מהסוף להתחלה כדי שמספרי השורות שנאספו יישארו תקפים
        for n, _txt in sorted(touched, reverse=True):
            idx = n - 1
            if merge == "next" and idx + 1 < len(lines):
                joined = (lines[idx].strip() + " " + lines[idx + 1].strip()).strip()
                lines[idx:idx + 2] = [joined]
            elif merge == "prev" and idx > 0:
                joined = (lines[idx - 1].strip() + " " + lines[idx].strip()).strip()
                lines[idx - 1:idx + 1] = [joined]

    return lines, touched


def main(argv=None):
    ap = argparse.ArgumentParser(description="ביטול כותרות תלושות בקובץ ספר של אוצריא")
    ap.add_argument("path", help="נתיב לקובץ הספר (נערך במקום)")
    ap.add_argument("--line", type=int, action="append", default=[],
                    help="מספר שורה לשחרור (ניתן לחזור על הדגל)")
    ap.add_argument("--match", help="ביטוי רגולרי על טקסט הכותרת")
    ap.add_argument("--merge", choices=("none", "prev", "next"), default="none",
                    help="מיזוג השורה המשוחררת לשורה הקודמת/הבאה")
    ap.add_argument("--no-trailing-newline", action="store_true",
                    help="לא להוסיף ירידת שורה בסוף הקובץ")
    ap.add_argument("--dry-run", action="store_true", help="רק לדווח, בלי לכתוב")
    args = ap.parse_args(argv)

    if not args.line and not args.match:
        ap.error("צריך --line או --match")

    with open(args.path, encoding="utf-8") as fh:
        text = fh.read()
    before = len(text.split("\n"))

    lines, touched = process(
        text,
        line_numbers=args.line,
        match_re=re.compile(args.match) if args.match else None,
        merge=args.merge,
    )

    if not touched:
        print("לא נמצאה שורת כותרת מתאימה — לא בוצע שינוי")
        return 1

    for n, txt in touched:
        print("שורה {}: כותרת שוחררה → {!r}".format(n, txt[:60]))
    print("שורות לפני: {}  שורות אחרי: {}  מיזוג: {}".format(before, len(lines), args.merge))

    if args.dry_run:
        return 0

    out = "\n".join(lines)
    if not args.no_trailing_newline and not out.endswith("\n"):
        out += "\n"
    with open(args.path, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("נכתב: {}".format(args.path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
