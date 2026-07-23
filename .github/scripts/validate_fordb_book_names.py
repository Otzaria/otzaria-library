#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
אימות שמות הספרים בתיקיית ForDB.

מטרה: לוודא שכל שם ספר המופיע בקבצי ForDB (בעמודות הרלוונטיות) קיים *בדיוק כצורתו*
(בלי שום שינוי תו או אות) ברשימת הספרים שתיבנה ביצירת ה-DB.

קבוצות השמות הנבנות (כל השמות עוברים ניקוי sanitize הזהה לזה שבונה את שמות הקבצים ב-DB,
sefariaToOtzaria/.../otzaria/utils.py):
  מרכיבים:
     1. *מקור האמת* לאוצריא: שמות קבצי הספרים הנארזים ל-release בלבד - הנתיבים תואמים
        בדיוק את .github/workflows/update-library.yml (PACKAGED_PREFIXES). תיקיות
        ביניים/ארכיון (extraBooks, KSK) אינן נכנסות ל-DB ולכן אינן
        נחשבות. נמנים דרך `git ls-tree` (ללא הורדת תוכן - עובד עם sparse/partial).
     2. שמות ספרי *ספריא*: נמשכים חיים מ-API (רשומות sefaria שב-all_metadata הן בסיס, ה-API
        מתאחד עליהן). ספרי ספריא נוצרים בבנייה ואין להם קובץ מקומי, לכן זה מקורם. כשל
        במשיכה החיה תחת SEFARIA_FETCH=1 מפיל את הבדיקה (exit 2) — אסור לאמת מול רשימה חלקית.
     3. שאר רשומות all_metadata_with_file_paths.json (אוצריא) - לבדיקות מטא-דאטה בלבד.
  A. "db_final" = (1)+(2) אחרי שינויי השמות - מה שבאמת מגיע ל-DB. ספר אוצריא נכנס ל-DB
     רק כקובץ נארז, ולכן שם במטא-דאטה לבדו (בלי קובץ נארז) אינו נכלל. כך נתפס ספר שהוזז
     לתיקייה לא-נארזת (כגון KSK) ושומר מטא-דאטה ישנה.
  B. "final_canon" = (1)+(2)+(3) אחרי שינויי השמות - רשימה רחבה לבדיקות המטא-דאטה.
     ("sources" = אותם מרכיבים לפני שינויי השמות; משמש לבדיקת book_renames.)
  שינויי השם (srename) נלקחים מ-book_renames.csv: sanitize(old)->sanitize(new).

אופן הבדיקה:
  * generations / book_moves: חייבים להתאים בדיוק ל-book.title שב-DB -> נבדקים מול db_final.
  * sefaria_metadata_changes / ForDB/all_metadata.json: מטא-דאטה -> נבדקים מול final_canon.
  * דליפת-מקור ב-ForDB/all_metadata.json: רשומה של ספר *ספריא* עם Sourcefolder שאינו
    "sefaria" היא שגיאה — שלב seed-המטא-דאטה (SeedAllMetadataPostProcess) מתאים לפי
    כותרת ודורס את book.sourceId מ-"Sefaria" ל-Dicta/וכו' (updateBookMetadata), וכך
    "אודות הספר" מציג מקור שגוי. מקורה בדרך כלל ברשומה כפולה (sefaria + לא-ספריא) במטא-דאטה.
  * book_renames.csv: שם ה*מקור* (העמודה השמאלית) מול sources - הספר שמשנים חייב להתקיים
    (שינוי לא "יתום"). שם היעד אינו נבדק בנפרד.
  * כפילויות שם בתוך ה-ZIP: שני קבצי ספרים שונים עם אותו שם מנוקה בתיקיות הנארזות
    יחד ל-otzaria_latest.zip (SAME_ZIP_PREFIXES) מתנגשים ב-DB (book.title זהה) ולכן
    נחשבים שגיאה. DictaToOtzaria/לא ערוך נארז ל-ZIP נפרד ואינו משתתף בבדיקה זו.

ללא --fix: יציאה בקוד 1 אם נמצא ולו שם אחד שאינו קיים, כפילות שם בתיקיות הנארזות,
או דליפת-מקור ב-all_metadata.json. במצב --fix מוסרות רק בעיות שהתיקון שלהן
דטרמיניסטי ובטוח: שורות ספר יתומות ב-generations.csv וב-book_moves.csv, ורשומות
לא-ספריא כפולות של ספרי ספריא ב-all_metadata.json. שינויי rename/category ובעיות
סמנטיות אחרות נשארים report-only ומפילים את הריצה, כי הסרתם תאבד כוונה אנושית.
משיכת ספריא חיה היא תנאי מוקדם ל--fix; כשל API יוצא בקוד 2 לפני כל כתיבה, כדי שכשל
רשת לעולם לא ימחק שורה תקינה.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import urllib.request

# ---------------------------------------------------------------------------
# נתיבים
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FORDB = os.path.join(REPO_ROOT, "ForDB")

CANONICAL_METADATA = os.path.join(REPO_ROOT, "all_metadata_with_file_paths.json")

BOOK_RENAMES = os.path.join(FORDB, "book_renames.csv")
GENERATIONS = os.path.join(FORDB, "generations.csv")
SEFARIA_CHANGES = os.path.join(FORDB, "sefaria_metadata_changes.csv")
BOOK_MOVES = os.path.join(FORDB, "book_moves.csv")
FORDB_METADATA = os.path.join(FORDB, "all_metadata.json")

# דוח --fix עבור ה-workflow: נכתב רק כאשר הוסר משהו בפועל.
REMOVED_REPORT = os.path.join(REPO_ROOT, "fordb_removed.json")

# API של ספריא: עץ התוכן המלא (TOC) - מכיל את כל שמות הספרים, ללא הטקסטים.
SEFARIA_INDEX_URL = "https://www.sefaria.org/api/index/"
SEFARIA_FETCH = os.environ.get("SEFARIA_FETCH", "1") not in ("0", "false", "False", "")


# ---------------------------------------------------------------------------
# עזרי קריאה
# ---------------------------------------------------------------------------
def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_csv_rows(path, has_header):
    """מחזיר (header_or_None, list_of_rows). שומר על השם בדיוק כפי שהוא בקובץ."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return (None, [])
    if has_header:
        return (rows[0], rows[1:])
    return (None, rows)


def col_index(header, name):
    """אינדקס עמודה לפי שם כותרת מדויק."""
    if not header:
        raise ValueError(f"כותרת ריקה/חסרה - לא ניתן לאתר את העמודה {name!r}")
    for i, h in enumerate(header):
        if h == name:
            return i
    raise KeyError(f"לא נמצאה עמודה בשם {name!r} בכותרת {header!r}")


# ---------------------------------------------------------------------------
# ניקוי שם - חייב להיות זהה *בדיוק* ל-sanitize_filename שבונה את שמות הספרים ב-DB
# (sefariaToOtzaria/סקריפטים/otzaria/utils.py). זה מה שקובע כיצד ייראה שם הספר ב-DB:
#   * הסרת טעמים/ניקוד (֑-ׇ)
#   * הסרת התווים \ / : * " ״ ? < > |
#   * המרת '_' לרווח, והסרת ' ו-''
# כך למשל 'גליון הש"ס' הופך ל'גליון השס' - כפי שהספר נשמר ב-DB.
# ---------------------------------------------------------------------------
def sanitize_title(name):
    if name is None:
        return None
    s = re.sub("[֑-ׇ]", "", name)            # טעמים וניקוד
    s = re.sub("[\\\\/:*\"״?<>|]", "", s)          # \ / : * " ״ ? < > |
    s = s.replace("_", " ").replace("''", "").replace("'", "")
    return s.strip()


# ---------------------------------------------------------------------------
# מקור האמת: קבצי הספרים בפועל הנארזים ל-release/DB.
# הנתיבים תואמים *בדיוק* לאלו שנארזים ב-.github/workflows/update-library.yml
# (שלבי "Create otzaria Release Archive" + "Create dicta Release Archive").
# חשוב: לא כל תיקייה שבה רכיב 'אוצריא' נכנסת ל-DB - תיקיות ביניים/ארכיון כמו
# extraBooks ו-KSK *אינן* נארזות, ולכן אינן נחשבות.
# ---------------------------------------------------------------------------
BOOK_EXTS = (".txt", ".pdf", ".docx")
PACKAGED_PREFIXES = (
    "Ben-YehudaToOtzaria/ספרים/אוצריא/",
    "DictaToOtzaria/ערוך/ספרים/אוצריא/",
    "DictaToOtzaria/לא ערוך/ספרים/אוצריא/",
    "OnYourWayToOtzaria/ספרים/אוצריא/",
    "OraytaToOtzaria/ספרים/אוצריא/",
    "tashmaToOtzaria/ספרים/אוצריא/",
    "sefariaToOtzaria/sefaria_export/ספרים/אוצריא/",
    "sefariaToOtzaria/sefaria_api/ספרים/אוצריא/",
    "MoreBooks/ספרים/אוצריא/",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא/",
    "wikisourceToOtzaria/ספרים/אוצריא/",
    "ToratEmetToOtzaria/ספרים/אוצריא/",
    "pninimToOtzaria/ספרים/אוצריא/",
    "National-LibraryToOtzaria/ספרים/אוצריא/",
)

# תיקיות הנארזות יחד ל-otzaria_latest.zip (בדיקת כפילויות שמות בתוך אותו ZIP).
# שני קבצים עם אותו שם מנוקה בקבוצה זו מתנגשים ב-DB (book.title זהה) ולכן נחשבים
# כפילות. הערה: DictaToOtzaria/לא ערוך נארז ל-ZIP נפרד (otzaria_dicta_latest.zip)
# ולכן אינו משתתף בבדיקה זו - הוא מודר מהקבוצה.
SAME_ZIP_PREFIXES = tuple(
    p for p in PACKAGED_PREFIXES if not p.startswith("DictaToOtzaria/לא ערוך/")
)


def list_tracked_paths():
    """
    מחזיר את רשימת הנתיבים העקובים ב-HEAD דרך `git ls-tree -r HEAD` (קורא את עץ
    הקומיט בלבד - אין צורך בהורדת תוכן הקבצים; עובד עם partial-clone + sparse).
    אם git אינו זמין, נופל ל-os.walk על עץ העבודה.
    """
    try:
        result = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-tree", "-r", "HEAD", "--name-only", "-z"],
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8").split("\0")
    except Exception as e:  # noqa: BLE001
        print(f"::warning::git ls-tree נכשל ({e}); נופלים ל-os.walk על עץ העבודה.")
        paths = []
        for root, _dirs, files in os.walk(REPO_ROOT):
            for fn in files:
                rel = os.path.relpath(os.path.join(root, fn), REPO_ROOT)
                paths.append(rel)
        return paths


def tracked_book_basenames():
    """
    מחזיר set של שמות-בסיס מנוקים של קבצי הספרים הנארזים ל-release (לפי
    PACKAGED_PREFIXES בלבד).
    """
    names = set()
    for p in list_tracked_paths():
        if not p:
            continue
        norm = p.replace("\\", "/")
        if not any(norm.startswith(prefix) for prefix in PACKAGED_PREFIXES):
            continue
        base, ext = os.path.splitext(norm.rsplit("/", 1)[-1])
        if ext.lower() in BOOK_EXTS:
            clean = sanitize_title(base)
            if clean:
                names.add(clean)
    return names


def find_packaged_duplicates():
    """
    מאתר שמות ספרים *כפולים* בתוך otzaria_latest.zip: שם-בסיס מנוקה (sanitize)
    של קובץ ספר המופיע ביותר מתיקיית-מקור אחת מ-SAME_ZIP_PREFIXES. שני קבצים כאלה
    מתנגשים ב-DB כי book.title נגזר מהשם המנוקה. מחזיר dict: שם מנוקה -> רשימת
    נתיבים ממוינת (רק שמות שמופיעים יותר מפעם אחת).
    """
    groups = {}
    for p in list_tracked_paths():
        if not p:
            continue
        norm = p.replace("\\", "/")
        if not any(norm.startswith(prefix) for prefix in SAME_ZIP_PREFIXES):
            continue
        base, ext = os.path.splitext(norm.rsplit("/", 1)[-1])
        if ext.lower() not in BOOK_EXTS:
            continue
        clean = sanitize_title(base)
        if clean:
            groups.setdefault(clean, []).append(norm)
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}


# ---------------------------------------------------------------------------
# בניית הרשימה הקנונית
# ---------------------------------------------------------------------------
def build_sanitized_rename(rename_pairs):
    """מיפוי שינויי-שם במרחב המנוקה: sanitize(old) -> sanitize(new) (ללא זהויות)."""
    smap = {}
    for _line, old, new in rename_pairs:
        so, sn = sanitize_title(old), sanitize_title(new)
        if so and sn and so != sn:
            smap[so] = sn
    return smap


def load_canonical(srename):
    """
    מחזיר (sources, final_canon, db_final, sefaria_final):
      * sources    = כל שמות המקור (מנוקים): קבצי ספרים נארזים + all_metadata (כל הרשומות) + ספריא חיה.
      * final_canon = sources אחרי החלת שינויי השמות. רשימה רחבה לבדיקות מטא-דאטה.
      * db_final    = השמות שבאמת *מגיעים ל-DB* אחרי שינויי שם: קבצים נארזים בפועל +
                      ספרי ספריא בלבד. ספרי אוצריא נכנסים ל-DB רק כקובץ נארז — ולכן שם
                      במטא-דאטה לבדו (בלי קובץ נארז) אינו נכלל כאן. כך נתפס ספר שהוזז
                      לתיקייה לא-נארזת (כגון KSK) ושומר מטא-דאטה ישנה.
      * sefaria_final = שמות ספרי *ספריא* בלבד (מנוקים, אחרי שינויי שם). משמש לבדיקת
                      דליפת-מקור: ספר ספריא הרשום ב-all_metadata.json עם Sourcefolder
                      לא-"sefaria" יידרס ל-Dicta/וכו' בשלב seed-המטא-דאטה.
    ספרי ספריא נוצרים בבנייה (אין להם קובץ מקומי), לכן הם נלקחים מה-API החי + המטא-דאטה.
    book_renames נבדק מול sources; generations/book_moves מול db_final; השאר מול final_canon.
    """
    def clean_titles(raws):
        return {c for c in (sanitize_title(r) for r in raws) if c}

    packaged = tracked_book_basenames()
    print(f"[canonical] {len(packaged)} שמות מקבצי ספרים נארזים (PACKAGED_PREFIXES)")

    meta = read_json(CANONICAL_METADATA)
    sefaria_meta = clean_titles(e.get("title") for e in meta if e.get("Sourcefolder") == "sefaria")
    other_meta = clean_titles(e.get("title") for e in meta if e.get("Sourcefolder") != "sefaria")
    print(f"[canonical] all_metadata: {len(sefaria_meta)} ספריא + {len(other_meta)} אוצריא")

    sefaria = set(sefaria_meta)
    if SEFARIA_FETCH:
        live = fetch_sefaria_titles()
        # A failed fetch must NEVER silently fall back to the local list: the canonical
        # set would be incomplete and real ForDB rows would look like orphans. Since this
        # validator gates ForDB publishing, validating against a partial list is unsafe —
        # fail loud (exit 2, distinct from a validation failure) so the run is retried.
        if live is None:
            print("::error::משיכת השמות מספריא נכשלה ו-SEFARIA_FETCH=1 — לא מאמתים מול רשימה חלקית; הריצו שוב.")
            sys.exit(2)
        before = len(sefaria)
        sefaria |= clean_titles(live)
        print(f"[canonical] נמשכו {len(live)} שמות חיים מספריא; נוספו {len(sefaria) - before} חדשים (union)")
    else:
        print("[canonical] משיכת ספריא מושבתת (SEFARIA_FETCH=0)")

    sources = packaged | sefaria | other_meta
    db = packaged | sefaria  # מה שבאמת ב-DB: קבצים נארזים + ספריא (ללא מטא-דאטה לא-מגובה)
    final_canon = {srename.get(s, s) for s in sources}
    db_final = {srename.get(s, s) for s in db}
    print(f"[canonical] מקור: {len(sources)} | ב-DB: {len(db)} | סופיים: {len(final_canon)}/{len(db_final)} (אחרי שינויי שם)")
    # `sefaria` (מנוקה, כולל שינויי-שם) משמש לבדיקת דליפת-מקור ב-all_metadata.json.
    sefaria_final = {srename.get(s, s) for s in sefaria}
    return sources, final_canon, db_final, sefaria_final


def fetch_sefaria_titles():
    """מושך את עץ התוכן של ספריא ומחזיר set של heTitle *גולמיים*. None בכשל."""
    try:
        req = urllib.request.Request(
            SEFARIA_INDEX_URL,
            headers={"User-Agent": "otzaria-library-ci/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - כל כשל תקשורת/פענוח -> None; המתקשר מפיל (fail-loud, ראו load_canonical)
        print(f"::warning::משיכת השמות מספריא נכשלה ({e}).")
        return None

    titles = set()

    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if "contents" in node:
                walk(node["contents"])
            else:
                he = node.get("heTitle")
                if he:
                    titles.add(he)

    walk(data)
    return titles


# ---------------------------------------------------------------------------
# שינויי השמות (book_renames.csv): שם-מקור (עמודה שמאלית) -> שם-יעד (עמודה ימנית)
# ---------------------------------------------------------------------------
def load_rename_pairs():
    """מחזיר רשימת (line_no, old, new) מתוך book_renames.csv (ללא כותרת)."""
    _, rows = read_csv_rows(BOOK_RENAMES, has_header=False)
    pairs = []
    for i, row in enumerate(rows, start=1):
        if len(row) < 2:
            continue
        pairs.append((i, row[0], row[1]))
    return pairs


def remove_orphans(path, col_name, db_final, srename):
    """מסיר שורות CSV ששם ספרן לא יגיע ל-DB, בלי לשכתב שורות תקינות.

    הקבצים האלה אינם מכילים שדות מרובי-שורות. שומרים את הטקסט המדויק של כל שורה
    שנשארת כדי ש-auto-fix לא ייצור diff מכני גדול של quoting/סדר.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        physical_lines = f.read().splitlines(keepends=True)
    if not physical_lines:
        return []

    header = next(csv.reader([physical_lines[0].rstrip("\r\n")]))
    c_idx = col_index(header, col_name)
    kept = [physical_lines[0]]
    removed = []
    for line_no, physical in enumerate(physical_lines[1:], start=2):
        raw_line = physical.rstrip("\r\n")
        if not raw_line.strip():
            kept.append(physical)
            continue
        row = next(csv.reader([raw_line]))
        raw_name = row[c_idx] if len(row) > c_idx else ""
        clean = sanitize_title(raw_name)
        final = srename.get(clean, clean)
        if raw_name and final not in db_final:
            removed.append((line_no, raw_name))
        else:
            kept.append(physical)

    if removed:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.writelines(kept)
    return removed


# ---------------------------------------------------------------------------
# הבדיקה
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="אימות שמות ForDB מול רשימת הספרים הקנונית.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="הסרת שורות יתומות דטרמיניסטיות מ-generations/book_moves וכפילויות מקור-ספריא",
    )
    args = parser.parse_args()
    if args.fix and not SEFARIA_FETCH:
        print("::error::--fix דורש SEFARIA_FETCH=1; מסרבים למחוק מול רשימת ספריא חלקית.")
        return 2
    if args.fix and os.path.exists(REMOVED_REPORT):
        os.unlink(REMOVED_REPORT)

    rename_pairs = load_rename_pairs()
    srename = build_sanitized_rename(rename_pairs)
    sources, final_canon, db_final, sefaria_final = load_canonical(srename)

    # failures[file] = list of (line/identifier, raw_name, checked_name)
    failures = {}

    def check_db_name(file_label, identifier, raw_name, canon):
        """
        בודק שם 'כפי שיהיה ב-DB': מנקה (sanitize), מחיל את שינוי-השם (srename),
        ומוודא קיום ב-canon (final_canon למטא-דאטה, db_final למה שחייב להתאים ל-book.title).
        """
        if raw_name is None or raw_name == "":
            return
        clean = sanitize_title(raw_name)
        final = srename.get(clean, clean)
        if final not in canon:
            failures.setdefault(file_label, []).append((identifier, raw_name, final))

    # 1) book_renames.csv - נבדק שם ה*מקור* (העמודה השמאלית) מול שמות המקור:
    #    יש לוודא שהספר שאותו משנים אכן קיים (שינוי לא "יתום"). שם היעד אינו נבדק
    #    כאן - הוא ממילא נכלל ב-final_canon כתוצאת השינוי.
    for line_no, old, _new in rename_pairs:
        clean = sanitize_title(old)
        if clean and clean not in sources:
            failures.setdefault("ForDB/book_renames.csv", []).append(
                (f"שורה {line_no} (שם מקור)", old, clean)
            )

    # 2) generations.csv + 4) book_moves.csv - עמודות "שם ספר"/"name". חייבים להתאים
    #    בדיוק ל-book.title שב-DB (db_final); ספר שאינו נארז (כגון שהוזז ל-KSK) ייתפס.
    #    ב--fix שורות יתומות מוסרות; במצב report-only הן מדווחות ומפילות.
    removed = []  # [(file_label, name, reason)]
    for file_label, path, col in (
        ("ForDB/generations.csv", GENERATIONS, "שם ספר"),
        ("ForDB/book_moves.csv", BOOK_MOVES, "name"),
    ):
        if args.fix:
            removed.extend(
                (file_label, name, "orphan")
                for _line_no, name in remove_orphans(path, col, db_final, srename)
            )
            continue
        header, rows = read_csv_rows(path, has_header=True)
        c_idx = col_index(header, col)
        for line_no, row in enumerate(rows, start=2):
            if len(row) > c_idx:
                check_db_name(file_label, f"שורה {line_no}", row[c_idx], db_final)

    # 3) sefaria_metadata_changes.csv - עמודה "title" (מטא-דאטה -> final_canon)
    header, rows = read_csv_rows(SEFARIA_CHANGES, has_header=True)
    t_idx = col_index(header, "title")
    for line_no, row in enumerate(rows, start=2):
        if len(row) > t_idx:
            check_db_name("ForDB/sefaria_metadata_changes.csv", f"שורה {line_no}", row[t_idx], final_canon)

    # 5) ForDB/all_metadata.json - שדה "title" (מטא-דאטה -> final_canon), ובמקביל בדיקת
    #    "דליפת-מקור": רשומה של ספר *ספריא* עם Sourcefolder שאינו "sefaria". שלב
    #    seed-המטא-דאטה (SeedAllMetadataPostProcess) מתאים לפי כותרת וקורא ל-
    #    updateBookMetadata(sourceId=...) שדורס את book.sourceId מ-"Sefaria" ל-Dicta/
    #    MoreBooks/וכו' — ואז "אודות הספר" באפליקציה מציג מקור שגוי. רשומות ספריא אמורות
    #    להיות מסוננות מ-ForDB (Sourcefolder=="sefaria" מסונן ביצירתו); רשומה לא-ספריא
    #    לספר ספריא היא כפילות תקועה — ב--fix מוסרת, ובמצב report-only מדווחת ומפילה.
    fordb_meta = read_json(FORDB_METADATA)
    source_leaks = []  # [(idx, title, sourcefolder)]
    for idx, entry in enumerate(fordb_meta):
        title = entry.get("title")
        check_db_name("ForDB/all_metadata.json", f"רשומה {idx}", title, final_canon)
        sf = entry.get("Sourcefolder")
        if title and sf and sf != "sefaria":
            clean = sanitize_title(title)
            if clean in sefaria_final or srename.get(clean, clean) in sefaria_final:
                source_leaks.append((idx, title, sf))

    # ב--fix מסירים רק את הרשומה הלא-ספריא הכפולה. רשומת ספריא עצמה נשארת מקור האמת.
    if args.fix and source_leaks:
        drop_indices = {idx for idx, _title, _sf in source_leaks}
        kept_metadata = [entry for idx, entry in enumerate(fordb_meta) if idx not in drop_indices]
        with open(FORDB_METADATA, "w", encoding="utf-8") as f:
            json.dump(kept_metadata, f, ensure_ascii=False, indent=2)
            f.write("\n")
        removed.extend(
            ("ForDB/all_metadata.json", title, "sefaria_duplicate")
            for _idx, title, _sf in source_leaks
        )
        source_leaks = []

    # 6) כפילויות שמות בתוך otzaria_latest.zip: שני קבצי ספרים שונים עם אותו שם מנוקה
    #    בתיקיות הנארזות לאותו ZIP יתנגשו ב-DB (book.title זהה). אינו ניתן לתיקון
    #    אוטומטי (אי אפשר להחליט איזה עותק להסיר) ולכן מפיל את הריצה.
    duplicates = find_packaged_duplicates()

    if args.fix and removed:
        with open(REMOVED_REPORT, "w", encoding="utf-8") as f:
            json.dump(
                [{"file": file_label, "name": name, "reason": reason} for file_label, name, reason in removed],
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")
        print(f"\n🧹 הוסרו אוטומטית {len(removed)} רשומות ForDB שלא היו מיושמות בריצה:")
        for file_label, name, reason in removed:
            print(f"     - [{reason}] {file_label}: {name!r}")

    # ----- דוח -----
    total = sum(len(v) for v in failures.values())
    if total == 0 and not duplicates and not source_leaks:
        print("\n✅ כל שמות הספרים ב-ForDB קיימים ברשימת הספרים הקנונית, אין כפילויות שם בתיקיות הנארזות, ואין דליפת-מקור.")
        return 0

    if total:
        print(f"\n❌ נמצאו {total} שמות ספרים ב-ForDB שאינם קיימים ברשימת הספרים הקנונית:\n")
        for file_label in sorted(failures):
            items = failures[file_label]
            print(f"  📄 {file_label} ({len(items)}):")
            for identifier, raw_name, checked in items:
                if checked != raw_name:
                    print(f"     - {identifier}: {raw_name!r} (כפי שב-DB: {checked!r}) — לא נמצא")
                else:
                    print(f"     - {identifier}: {raw_name!r} — לא נמצא")
            print()

    if duplicates:
        print(f"\n❌ נמצאו {len(duplicates)} שמות ספרים כפולים בתיקיות הנארזות ל-otzaria_latest.zip")
        print("   (שני קבצים עם אותו שם מנוקה מתנגשים ב-DB — book.title זהה. יש לאחד או לשנות שם לאחד מהם):\n")
        for name in sorted(duplicates):
            print(f"  🔁 {name!r}:")
            for path in duplicates[name]:
                print(f"     - {path}")
        print()

    if source_leaks:
        print(f"\n❌ נמצאו {len(source_leaks)} רשומות ב-ForDB/all_metadata.json של ספרי *ספריא* עם Sourcefolder שאינו 'sefaria'.")
        print("   שלב seed-המטא-דאטה מתאים לפי כותרת ודורס את מקור הספר מ-'Sefaria' לערך שברשומה")
        print("   (updateBookMetadata → book.sourceId), כך ש'אודות הספר' מציג מקור שגוי (למשל 'דיקטה').")
        print("   ב-PR זו בדיקת report-only; יש להסיר את הרשומה או למזג תיקון שמאפשר ל-main להסירה אוטומטית:\n")
        for idx, title, sf in sorted(source_leaks, key=lambda x: x[1]):
            print(f"     - רשומה {idx}: {title!r}  (Sourcefolder={sf!r} → אמור להיות 'sefaria')")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
