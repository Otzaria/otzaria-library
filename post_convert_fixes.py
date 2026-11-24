"""תיקונים לאחר המרה: תיקונים ידניים שהמרה חוזרת מחילה מחדש.

כשהשגיאה נמצאת במקור עצמו (שגיאת הקלדה או סריקה של המקור), המרה חוזרת מחזירה אותה
ודורסת את התיקון הידני שנעשה בספר. לכן לכל מקור יש קובץ
`<מקור>/post_convert_fixes.tsv`, והממיר מחיל אותו על כל ספר שהוא כותב.

פורמט הקובץ (UTF-8, מופרד בטאבים, שורה ראשונה = כותרת, '#' בתחילת שורה = הערה):

    book<TAB>old<TAB>new<TAB>note

* book - שם הספר, כלומר שם קובץ הפלט בלי ‎.txt (כמו בספרייה).
* old  - הטקסט השגוי כפי שהממיר מוציא אותו, עם מספיק הקשר כדי שיופיע בספר פעם אחת בלבד.
* new  - הטקסט המתוקן.
* note - מקור התיקון (קומיט, דיווח). לא משפיע.
בתוך old/new: ‎\\t = טאב, ‎\\n = מעבר שורה, ‎\\\\ = לוכסן הפוך.

ההחלה מעוגנת לטקסט ולא למספר שורה, ואידמפוטנטית:
* old מופיע פעם אחת (מחוץ למופע של new) - מוחלף.
* old לא מופיע ו-new מופיע - התיקון כבר קיים; לא נוגעים.
* old לא מופיע וגם new לא - שגיאה: העוגן חסר (המקור או הממיר השתנו, צריך לעדכן את השורה).
* old מופיע יותר מפעם אחת - שגיאה: צריך להאריך את ההקשר.
שגיאה עוצרת את ההמרה (PostConvertFixError), כדי שתיקון לא ילך לאיבוד בשקט.

שימוש בממיר:
    import post_convert_fixes
    text = post_convert_fixes.apply_book(SOURCE_DIR, book_name, text)

בדיקה מול הספרים שבמאגר (כל שורה חייבת להיות כבר מוחלת בספר שלה):
    python post_convert_fixes.py --check <מקור> [<מקור> ...]
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass

FILE_NAME = "post_convert_fixes.tsv"
HEADER = ["book", "old", "new", "note"]
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


class PostConvertFixError(Exception):
    pass


@dataclass(frozen=True)
class Fix:
    book: str
    old: str
    new: str
    note: str
    where: str  # "<file>:<line>" לצורך הודעות שגיאה


def _unescape(s: str, where: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            nxt = s[i + 1:i + 2]
            if nxt not in ("t", "n", "\\"):
                raise PostConvertFixError(f"{where}: escape לא מוכר '\\{nxt}'")
            out.append({"t": "\t", "n": "\n", "\\": "\\"}[nxt])
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def load(path: str) -> dict[str, list[Fix]]:
    """קורא קובץ תיקונים -> {שם ספר: [Fix, ...]} לפי סדר הקובץ."""
    fixes: dict[str, list[Fix]] = {}
    with open(path, encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    if not lines or lines[0].rstrip("\r").split("\t") != HEADER:
        raise PostConvertFixError(f"{path}: שורת הכותרת חייבת להיות {'<TAB>'.join(HEADER)}")
    for n, line in enumerate(lines[1:], start=2):
        line = line.rstrip("\r")
        if not line.strip() or line.startswith("#"):
            continue
        where = f"{path}:{n}"
        cols = line.split("\t")
        if len(cols) != 4:
            raise PostConvertFixError(f"{where}: צריך 4 עמודות, יש {len(cols)}")
        book, old, new, note = cols[0], _unescape(cols[1], where), _unescape(cols[2], where), cols[3]
        if not book or not old or old == new:
            raise PostConvertFixError(f"{where}: book ו-old חובה, ו-new חייב להיות שונה מ-old")
        fixes.setdefault(book, []).append(Fix(book, old, new, note, where))
    return fixes


def _occurrences(text: str, s: str) -> list[int]:
    out, i = [], text.find(s)
    while i != -1:
        out.append(i)
        i = text.find(s, i + 1)
    return out


def _free_old(text: str, fix: Fix) -> list[int]:
    """מופעי old שאינם חלק ממופע של new (כשה-old מוכל ב-new, למשל הוספת מילה)."""
    old_pos = _occurrences(text, fix.old)
    offsets = _occurrences(fix.new, fix.old)
    if not offsets:
        return old_pos
    covered = {q + k for q in _occurrences(text, fix.new) for k in offsets}
    return [p for p in old_pos if p not in covered]


def apply_text(text: str, fixes: list[Fix]) -> str:
    """מחיל את התיקונים לפי הסדר. זורק PostConvertFixError כשעוגן חסר או כפול."""
    for fix in fixes:
        free = _free_old(text, fix)
        if len(free) == 1:
            p = free[0]
            text = text[:p] + fix.new + text[p + len(fix.old):]
        elif len(free) > 1:
            raise PostConvertFixError(
                f"{fix.where}: '{fix.old}' מופיע {len(free)} פעמים ב'{fix.book}' - צריך להאריך את ההקשר")
        elif fix.new not in text:
            raise PostConvertFixError(
                f"{fix.where}: העוגן '{fix.old}' חסר ב'{fix.book}' (וגם התיקון לא נמצא) - לעדכן את השורה")
    return text


_cache: dict[str, dict[str, list[Fix]]] = {}


def fixes_for_source(source_dir: str) -> dict[str, list[Fix]]:
    path = os.path.join(source_dir, FILE_NAME)
    if path not in _cache:
        _cache[path] = load(path) if os.path.exists(path) else {}
    return _cache[path]


def apply_book(source_dir: str, book: str, text: str) -> str:
    """מחיל על טקסט הספר `book` (שם הקובץ בלי ‎.txt) את התיקונים של המקור."""
    if book.endswith(".txt"):
        book = book[:-4]
    fixes = fixes_for_source(source_dir).get(book)
    return apply_text(text, fixes) if fixes else text


def apply_file(source_dir: str, path: str) -> bool:
    """מחיל על קובץ ספר במקום. מחזיר True אם הקובץ השתנה."""
    book = os.path.splitext(os.path.basename(path))[0]
    if book not in fixes_for_source(source_dir):
        return False
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    new = apply_book(source_dir, book, text)
    if new == text:
        return False
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return True


def books_root(source_dir: str) -> list[str]:
    """תיקיות ספרים שמותר לבדוק במקור; חומר שסומן «לא רלוונטי» אינו מקור."""
    roots = [
        os.path.join(source_dir, "ספרים", kind)
        for kind in ("אוצריא", "לא ממויין")
    ] + [
        os.path.join(source_dir, "ערוך", "ספרים", kind)
        for kind in ("אוצריא", "לא ממויין")
    ]
    return [r for r in roots if os.path.isdir(r)]


def check(source_dir: str) -> list[str]:
    """כל שורה בקובץ חייבת להיות כבר מוחלת בספר שלה במאגר. מחזיר רשימת בעיות."""
    fixes = fixes_for_source(source_dir)
    paths: dict[str, list[str]] = {}
    for root in books_root(source_dir):
        for dirpath, _, files in os.walk(root):
            for name in files:
                if name.endswith(".txt"):
                    paths.setdefault(name[:-4], []).append(os.path.join(dirpath, name))
    problems = []
    for book, items in fixes.items():
        found = paths.get(book, [])
        if len(found) != 1:
            problems.append(f"{items[0].where}: הספר '{book}' נמצא {len(found)} פעמים במקור")
            continue
        with open(found[0], encoding="utf-8") as f:
            text = f.read()
        for fix in items:
            if _free_old(text, fix) or fix.new not in text:
                problems.append(f"{fix.where}: התיקון לא מוחל בספר שבמאגר")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="לוודא שכל התיקונים כבר מוחלים בספרים שבמאגר")
    ap.add_argument("sources", nargs="+", help="תיקיית מקור, למשל OraytaToOtzaria")
    a = ap.parse_args(argv)
    bad = 0
    for src in a.sources:
        src = src if os.path.isabs(src) else os.path.join(REPO_ROOT, src)
        try:
            problems = check(src) if a.check else []
            n = sum(len(v) for v in fixes_for_source(src).values())
        except PostConvertFixError as e:
            problems, n = [str(e)], 0
        for p in problems:
            print(p, file=sys.stderr)
        bad += len(problems)
        print(f"{os.path.basename(src)}: {n} תיקונים, {len(problems)} בעיות")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
