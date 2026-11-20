#!/usr/bin/env python3
"""אזהרה (לא כשל) כששם המחבר של ספר של המאגר ב־heAuthors או ב־authorName שונה מ־metadata.json.

שם המחבר של ספר של המאגר נקבע ב־`author` (או `authors[]`) של metadata.json שבשורש — זה מה שנכנס
לטבלת `author` במסד. `heAuthors` ב־ForDB/all_metadata.json, ב־all_metadata.json וב־
all_metadata_with_file_paths.json, ו־`authorName` ב־ForDB/book_info.csv, הם העתקים בלבד, וכשהם
מפגרים אחריו הם מציגים באתר שם ישן, ומי שיסנכרן מהם אל metadata.json יחזיר צורות שתוקנו.

הבדיקה רק מדווחת ואינה מתקנת: יש הפרשים שאדם צריך להכריע בהם, ושינוי `authorName` מחייב
אירוע ביומן הזהות של האתר. הפרשים ישנים רבים עומדים, ולכן עם --base מסומן ב־`::warning` רק
הפרש *חדש*, שלא היה בקומיט הבסיס (הראשון מבין המועמדים שהוא אב של --rev); השאר נספרים בשורת
סיכום. בלי בסיס מסומנים הראשונים בלבד. קריסה של הבדיקה עצמה היא כשל (exit 2), לא אזהרה.

ספר של המאגר = קובץ ‎.txt‎ בשורש ספרים נארז (DB_BOOK_PREFIXES) בעץ של --rev. רשומת העתק נבדקת
רק כשהכותר שלה הוא שם הקובץ (או איות ה־DB שלו, או שם התצוגה עם הגרשיים) *וגם* תיקיית המקור שלה (Sourcefolder) היא של
אותו ספר: רשומה ישנה של ספר אחר באותו שם (למשל רשומת דיקטה של ספר שהקובץ הנארז שלו הוא ספר
אחר) אינה נבדקת מולו. ב־metadata.json נלקחת הרשומה *האחרונה* לכל כותר, בהתאמה מדויקת, כמו
`associateBy { it.title }` במחולל. ספר שכותרו הוא גם כותר של ספר ספריא אינו נבדק. ב־book_info.csv
נבדק ספר עם שורה אחת ומחבר אחד; שורה עם authorName ריק אינה נבדקת. ההשוואה אחרי
normalizeAuthorName (ניקוד, תווי כיוון ורווחים), כמו במחולל.
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys

import book_display_titles
from validate_fordb_book_names import DB_BOOK_PREFIXES, db_title

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAX_ANNOTATIONS = 30
JSON_MIRRORS = ("ForDB/all_metadata.json", "all_metadata.json", "all_metadata_with_file_paths.json")
BOOK_INFO = "ForDB/book_info.csv"

_NIKUD = re.compile("[֑-ֽֿ-ׇ]")
_BIDI = re.compile("[‎‏‪-‮⁦-⁩﻿]")
_SPACE = re.compile("[\\s\u00a0\u2000-\u200b\u202f\u205f\u3000]+")


def normalize_author_name(raw):
    """כמו normalizeAuthorName ב־SeforimLibrary: גרשיים וגרש נשמרים."""
    return _SPACE.sub(" ", _BIDI.sub("", _NIKUD.sub("", raw or ""))).strip()


def source_key(name):
    """'wiki_jewish_books' ו־'wikiJewishBooksToOtzaria' -> 'wikijewishbooks'."""
    key = re.sub("[^a-z0-9]", "", (name or "").lower())
    return key[:-len("tootzaria")] if key.endswith("tootzaria") else key


def metadata_authors(record):
    authors = record.get("authors")
    if isinstance(authors, list) and any(isinstance(a, str) and a.strip() for a in authors):
        names = [a.strip() for a in authors if isinstance(a, str) and a.strip()]
    else:
        author = record.get("author")
        names = [author.strip()] if isinstance(author, str) and author.strip() else []
    return list(dict.fromkeys(names))


def _git(root, *args):
    result = subprocess.run(["git", "-C", root, *args], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout


class Snapshot:
    """הקבצים של קומיט אחד, נקראים מ־git (ה־checkout של ה־CI אינו מכיל את קובצי הספרים)."""

    def __init__(self, root, rev):
        self.root, self.rev = root, rev

    def text(self, rel):
        try:
            return _git(self.root, "cat-file", "-p", f"{self.rev}:{rel}").decode("utf-8")
        except RuntimeError:
            return None

    def json(self, rel):
        text = self.text(rel)
        return None if text is None else json.loads(text)

    def display_titles(self):
        """שם קובץ -> book.title (עם הגרשיים שהמחולל מחזיר), לכל ספר נארז."""
        tree = _git(self.root, "ls-tree", "-r", "-z", "--name-only", "--full-tree", self.rev).decode("utf-8")
        paths = [p for p in tree.split("\0") if p.endswith(".txt") and p.startswith(DB_BOOK_PREFIXES)]
        titles = book_display_titles.display_titles(self.root, self.rev, paths)
        return {path.rsplit("/", 1)[-1][:-4]: title for path, title in titles.items()}

    def books(self):
        """שם קובץ -> מפתח מקור, לכל ספר נארז; שם שיש לו יותר מקובץ אחד אינו נבדק."""
        tree = _git(self.root, "ls-tree", "-r", "-z", "--name-only", "--full-tree", self.rev).decode("utf-8")
        found = {}
        for path in filter(None, tree.split("\0")):
            if path.endswith(".txt") and path.startswith(DB_BOOK_PREFIXES):
                found.setdefault(path.rsplit("/", 1)[-1][:-4], []).append(source_key(path.split("/", 1)[0]))
        return {stem: sources[0] for stem, sources in found.items() if len(sources) == 1}


def find_mismatches(snap):
    """[(קובץ, ספר, ערך בשדה, ערך ב־metadata.json)] לספרי המאגר."""
    meta = {}
    for record in snap.json("metadata.json"):
        if isinstance(record, dict) and isinstance(record.get("title"), str):
            meta[record["title"]] = metadata_authors(record)  # האחרונה גוברת, כמו במחולל

    sefaria_titles = set()
    canonical = snap.json("all_metadata_with_file_paths.json") or []
    for r in canonical:
        if r.get("Sourcefolder") == "sefaria" and isinstance(r.get("title"), str):
            sefaria_titles |= {r["title"], db_title(r["title"])}
    by_title = {}  # כותר בעותק (שם הקובץ, איות ה־DB או שם התצוגה) -> (שם הקובץ, מפתח מקור)
    display = snap.display_titles()
    for stem, source in snap.books().items():
        if not meta.get(stem) or db_title(stem) in sefaria_titles:
            continue
        for title in {stem, db_title(stem), display.get(stem, stem)}:
            by_title[title] = (stem, source)

    def same(left, right):
        return [normalize_author_name(x) for x in left] == [normalize_author_name(x) for x in right]

    out = []
    for rel in JSON_MIRRORS:
        records = canonical if rel == "all_metadata_with_file_paths.json" else snap.json(rel)
        for record in records or []:
            hit = by_title.get(record.get("title"))
            if hit is None or source_key(record.get("Sourcefolder")) != hit[1]:
                continue
            expected = meta[hit[0]]
            he = [h.strip() for h in (record.get("heAuthors") or []) if isinstance(h, str) and h.strip()]
            if not same(he, expected):
                out.append((rel, record["title"], " / ".join(he), " / ".join(expected)))

    text = snap.text(BOOK_INFO)
    rows = list(csv.reader(io.StringIO(text, newline="")))[1:] if text is not None else []
    per_book = {}
    for row in rows:
        if row:
            per_book.setdefault(row[0], []).append(row[1])
    for book, names in per_book.items():
        hit = by_title.get(book)
        if hit is None or len(names) != 1 or not names[0]:
            continue
        expected = meta[hit[0]]
        if len(expected) == 1 and not same(names, expected):
            out.append((BOOK_INFO, book, names[0], expected[0]))
    return out


def _data(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _prop(text):
    return _data(text).replace(":", "%3A").replace(",", "%2C")


def pick_base(root, candidates, rev):
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if not candidate or set(candidate) == {"0"}:
            continue
        try:
            sha = _git(root, "rev-parse", "--verify", "--quiet", candidate + "^{commit}").decode().strip()
            _git(root, "merge-base", "--is-ancestor", sha, rev)
        except RuntimeError:
            continue
        return sha
    return None


def main(argv=None, root=REPO_ROOT, stream=sys.stdout):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rev", default="HEAD")
    parser.add_argument("--base", action="append", default=[], help="annotate only differences new since it")
    args = parser.parse_args(argv)
    try:
        mismatches = find_mismatches(Snapshot(root, args.rev))
        base = pick_base(root, args.base, args.rev)
        before = set(find_mismatches(Snapshot(root, base))) if base else None
    except Exception as error:  # באג בבדיקה עצמה: מפילים, לא מסתירים
        print(f"::error title=Author mirrors::the check crashed: {_data(repr(error))}", file=stream)
        return 2
    shown = mismatches if before is None else [m for m in mismatches if m not in before]
    for path, book, field, expected in shown[:MAX_ANNOTATIONS]:
        print(f"::warning file={_prop(path)},title=Author mirror differs from metadata.json::"
              f"{_data(book)}: '{_data(field)}' != '{_data(expected)}'", file=stream)
    by_file = {}
    for path, *_ in mismatches:
        by_file[path] = by_file.get(path, 0) + 1
    summary = ", ".join(f"{path}: {count}" for path, count in sorted(by_file.items())) or "none"
    print(f"Author mirror differences (metadata.json is the source): {summary}", file=stream)
    if before is None:
        print(f"no base commit: the first {min(len(shown), MAX_ANNOTATIONS)} of {len(shown)} are annotated", file=stream)
    else:
        print(f"{len(shown)} new since {base[:12]}" +
              (f"; the first {MAX_ANNOTATIONS} are annotated" if len(shown) > MAX_ANNOTATIONS else ""), file=stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
