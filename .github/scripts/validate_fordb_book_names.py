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
        ביניים/ארכיון (extraBooks, docxToOtzaria) אינן נכנסות ל-DB ולכן אינן
        נחשבות. נמנים דרך `git ls-tree` (ללא הורדת תוכן - עובד עם sparse/partial).
     2. שמות ספרי *ספריא*: נמשכים חיים מ-API (רשומות sefaria שב-all_metadata הן בסיס, ה-API
        מתאחד עליהן). ספרי ספריא נוצרים בבנייה ואין להם קובץ מקומי, לכן זה מקורם. כשל
        במשיכה החיה תחת SEFARIA_FETCH=1 מפיל את הבדיקה (exit 2) — אסור לאמת מול רשימה חלקית.
     3. שאר רשומות all_metadata_with_file_paths.json (אוצריא) - לבדיקות מטא-דאטה בלבד.
  A. "db_final" = (1)+(2) אחרי שינויי השמות - מה שבאמת מגיע ל-DB. ספר אוצריא נכנס ל-DB
     רק כקובץ נארז, ולכן שם במטא-דאטה לבדו (בלי קובץ נארז) אינו נכלל. כך נתפס ספר שהוזז
     לתיקייה לא-נארזת (כגון extraBooks) ושומר מטא-דאטה ישנה.
  B. "final_canon" = (1)+(2)+(3) אחרי שינויי השמות - רשימה רחבה לבדיקות המטא-דאטה.
     ("sources" = אותם מרכיבים לפני שינויי השמות; משמש לבדיקת book_renames.)
  שינויי השם (srename) נלקחים מ-book_renames.csv: sanitize(old)->sanitize(new).

אופן הבדיקה:
  * generations / book_info / book_moves: חייבים להתאים בדיוק ל-book.title שב-DB -> נבדקים מול
    db_final.
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
  * איות מדויק (db_title): כל הבדיקות שמעל משוות במרחב ה-*מנוקה*, שבו מרכאות נמחקות.
    הצרכנים בפועל (applyGenerations / renameBookTitle / applyMetadata) משווים ל-
    book.title בהשוואת מחרוזות מדויקת, ו-book.title של ספר אוצריא נגזר מ-
    normalizeHebrewLabel של Generator.kt - הממירה מרכאות לגרשיים ואינה מוחקת אותן.
    לכן 'הגהות הב"ח על מסכת ברכות' עבר את כל הבדיקות ובכל זאת דולג בשקט. כל שם
    ForDB שמזהה קובץ ספר נארז יחיד חייב להיות מאויית בדיוק כמו db_title שלו.
    ForDB/sefaria_metadata_changes.csv מוחרג: שמותיו הם כותרות ספריא שעשויות
    להתנגש במרחב המנוקה עם קובץ אוצריא ולהיות שני ספרים נפרדים ב-DB.
  * שינויי-שם מתים: שורת book_renames שגם המקור וגם היעד שלה אינם book.title קיים,
    בעוד קיים ספר שנבדל מהמקור רק בפיסוק - no-op ודאי שחוזר בכל מחזור.

ללא --fix: יציאה בקוד 1 אם נמצא ולו שם אחד שאינו קיים, כפילות שם בתיקיות הנארזות,
או דליפת-מקור ב-all_metadata.json. במצב --fix מוסרות רק בעיות שהתיקון שלהן
דטרמיניסטי ובטוח: שורות ספר יתומות ב-generations.csv, ב-book_info.csv וב-book_moves.csv, ורשומות
לא-ספריא כפולות של ספרי ספריא ב-all_metadata.json. שינויי rename/category ובעיות
סמנטיות אחרות נשארים report-only ומפילים את הריצה, כי הסרתם תאבד כוונה אנושית.
משיכת ספריא חיה היא תנאי מוקדם ל--fix; כשל API יוצא בקוד 2 לפני כל כתיבה, כדי שכשל
רשת לעולם לא ימחק שורה תקינה.

שינויי-שם של קבצי ספרים (--rename-base): לפני הסרת היתומים נבדקת ההיסטוריה שטרם
אומתה (מהבסיס עד HEAD). שורה שהתייתמה כי קובץ הספר שלה *שונה בשמו* בטווח הזה אינה
נמחקת — שמה מוחלף לשם החדש בכל קובץ שמזהה ספר לפי שם (fordb_book_renames.py). שינוי-
שם שלא ניתן ליישר בבטחה (עמום, נוגע ב-book_renames, התנגשות קישורים) מפיל את הריצה
ושומר את השורות.
"""

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.request

from book_info_contract import validate_book_info
import fordb_book_renames as book_renames_follow

# ---------------------------------------------------------------------------
# נתיבים
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
FORDB = os.path.join(REPO_ROOT, "ForDB")

CANONICAL_METADATA = os.path.join(REPO_ROOT, "all_metadata_with_file_paths.json")

BOOK_RENAMES = os.path.join(FORDB, "book_renames.csv")
GENERATIONS = os.path.join(FORDB, "generations.csv")
# מידע על ספרים (דור, תת-דור, שנים, מחבר) שנערך באתר אוצריא, PR לכל עריכה. כמה שורות לאותו
# ספר (מחברים שונים) הן תקינות; עמודת השם היא bookName.
BOOK_INFO = os.path.join(FORDB, "book_info.csv")
SEFARIA_CHANGES = os.path.join(FORDB, "sefaria_metadata_changes.csv")
BOOK_MOVES = os.path.join(FORDB, "book_moves.csv")
FORDB_METADATA = os.path.join(FORDB, "all_metadata.json")

# דוח --fix עבור ה-workflow: נכתב רק כאשר הוסר משהו בפועל.
REMOVED_REPORT = os.path.join(REPO_ROOT, "fordb_removed.json")
# שינויי-שם שיושרו (--fix), רשימת הנתיבים שה-workflow מוסיף לקומיט (NUL), והודעת הקומיט.
RENAMED_REPORT = os.path.join(REPO_ROOT, "fordb_renamed.json")
TOUCHED_LIST = os.path.join(REPO_ROOT, "fordb_touched.txt")
COMMIT_MESSAGE = os.path.join(REPO_ROOT, "fordb_commit_message.txt")
FIX_OUTPUTS = (REMOVED_REPORT, RENAMED_REPORT, TOUCHED_LIST, COMMIT_MESSAGE)
LINKS_SYNC_CONFIG = "manual_links_sync.json"

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
        text = f.read()
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
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
# כך למשל 'גליון הש"ס' הופך ל'גליון השס' - כך *שם הקובץ* נבנה.
#
# שימו לב: זו התאמה חסרת-רגישות למרכאות, ולכן היא *אינה* שם הספר ב-DB. שם הספר
# ב-DB נגזר מ-normalizeHebrewLabel של Generator.kt (ראו db_title למטה), הממירה
# מרכאות לגרשיים במקום להסיר אותן. sanitize_title משמש כאן כמפתח *התאמה* בלבד
# ("איזה קובץ ספר מדובר"), ו-db_title קובע את *האיות המדויק* הנדרש.
#
# המפתח חייב להיות יציב תחת db_title: sanitize_title(db_title(x)) == sanitize_title(x).
# אחרת שם קובץ עם מרכאות מסולסלות (”), גרש כפול (׳׳), backtick או רווח כפול מקבל מפתח
# שונה מהשורה שנכתבה באיות ה-DB שלו, והשורה נראית יתומה. כך נמחקו ב-3d96022b השורות
# של 'הגהות הב”ח' ו'השמטות הריטב”א' אחרי ששם הקובץ קיבל ” בלבד. לכן מקפלים קודם את
# אותן צורות שמקפלת db_title, ורק אז מסירים.
# ---------------------------------------------------------------------------
def sanitize_title(name):
    if name is None:
        return None
    s = re.sub("[֑-ׇ]", "", name)            # טעמים וניקוד
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # backtick לפני הגרש הכפול: '``' הוא ׳׳ אחרי db_title, וקיפול חוזר הופך אותו ל-״.
    s = s.replace("`", GERESH).replace(GERESH + GERESH, GERSHAYIM)
    s = re.sub("[\\\\/:*\"״?<>|]", "", s)          # \ / : * " ״ ? < > |
    s = s.replace("_", " ").replace("''", "").replace("'", "")
    return ASCII_WHITESPACE_RUN.sub(" ", s).strip()


# ---------------------------------------------------------------------------
# איות שם הספר *כפי שהוא נכתב ל-book.title* - העתק מדויק של
# Generator.normalizeHebrewLabel + normalizeBookTitle
# (generator/otzariasqlite/.../Generator.kt), שהן שממירות שם קובץ אוצריא לכותרת:
#   'הגהות הב"ח על מסכת ברכות'  -> 'הגהות הב״ח על מסכת ברכות'
#   "חידושי ופירושי מהרי''ק"    -> 'חידושי ופירושי מהרי״ק'
# הצרכנים (applyGenerations, renameBookTitle, applyMetadata) משווים ל-book.title
# בהשוואת מחרוזות *מדויקת*, ולכן ForDB חייב לאיית בדיוק כך.
# ---------------------------------------------------------------------------
GERESH = "׳"
GERSHAYIM = "״"
# הצמצום ב-Kotlin הוא "\\s+".toRegex() - java.util.regex ללא UNICODE_CHARACTER_CLASS,
# כלומר [ \t\n\x0B\f\r] בלבד. ל-re של פייתון \s מודע-יוניקוד וגם בולע NBSP (U+00A0)
# ורווחים יוניקודיים אחרים; לכן שם קובץ המכיל NBSP היה מקבל כאן db_title ש-Generator.kt
# לעולם לא מייצר, ו-find_spelling_drift היה דורש איות שה-DB אינו יכול להחזיק.
ASCII_WHITESPACE_RUN = re.compile(r"[ \t\n\x0b\f\r]+")


def db_title(name):
    """שם הספר ב-DB עבור קובץ ספר אוצריא ששמו (ללא סיומת) הוא name."""
    if name is None:
        return None
    s = name.strip()
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("‘", "'").replace("’", "'")
    s = s.replace('"', GERSHAYIM)
    s = s.replace("''", GERSHAYIM)
    s = s.replace(GERESH + GERESH, GERSHAYIM)
    s = s.replace("`", GERESH)
    s = ASCII_WHITESPACE_RUN.sub(" ", s).strip()
    # normalizeBookTitle: 'תנך' / 'תנ"ך' -> 'תנ״ך' (המרכאות כבר הומרו מעל)
    if s == "תנך":
        s = "תנ" + GERSHAYIM + "ך"
    return s


# ---------------------------------------------------------------------------
# מקור האמת: קבצי הספרים בפועל הנארזים ל-release/DB.
# הנתיבים תואמים *בדיוק* לאלו שנארזים ב-.github/workflows/update-library.yml
# (שלבי "Create otzaria Release Archive" + "Create dicta Release Archive").
# חשוב: לא כל תיקייה שבה רכיב 'אוצריא' נכנסת ל-DB - תיקיות ביניים/ארכיון כמו
# extraBooks ו-docxToOtzaria *אינן* נארזות, ולכן אינן נחשבות.
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
    "KSK/ספרים/אוצריא/",
    "wikiJewishBooksToOtzaria/ספרים/אוצריא/",
    "wikisourceToOtzaria/ספרים/אוצריא/",
    "ToratEmetToOtzaria/ספרים/אוצריא/",
    "pninimToOtzaria/ספרים/אוצריא/",
    "National-LibraryToOtzaria/ספרים/אוצריא/",
    "yam-HaHachmaToOtzaria/ספרים/אוצריא/",
)

# תיקיות הנארזות יחד ל-otzaria_latest.zip (בדיקת כפילויות שמות בתוך אותו ZIP).
# שני קבצים עם אותו שם מנוקה בקבוצה זו מתנגשים ב-DB (book.title זהה) ולכן נחשבים
# כפילות. הערה: DictaToOtzaria/לא ערוך נארז ל-ZIP נפרד (otzaria_dicta_latest.zip)
# ולכן אינו משתתף בבדיקה זו - הוא מודר מהקבוצה.
SAME_ZIP_PREFIXES = tuple(
    p for p in PACKAGED_PREFIXES if not p.startswith("DictaToOtzaria/לא ערוך/")
)

# התיקיות שספריהן באמת מגיעות ל-DB: אלה הנארזות ל-otzaria_latest.zip - הנכס
# היחיד ש-manual-generate-release מוריד ומחלץ ל-otzaria-extract. חייב להישאר
# זהה ל-manual_links_packaging.BOOK_ROOTS (נאכף ב-test_validate_fordb_book_names).
# otzaria_dicta_latest.zip (DictaToOtzaria/לא ערוך) הוא נכס נפרד שהבנייה אינה
# צורכת, ולכן אינו כאן. הרשימה משוכפלת ולא מיובאת בכוונה: ה-workflow עושה
# sparse-checkout של /ForDB/ ו-/.github/scripts/ בלבד, כך ש-manual_links_packaging.py
# אינו קיים בעץ העבודה בזמן הריצה.
DB_BOOK_PREFIXES = tuple(p for p in SAME_ZIP_PREFIXES)

# רק .txt הופך לספר ב-DB (createAndProcessBook); PDF/DOCX נארזים אך אינם ספרים.
DB_BOOK_EXTS = (".txt",)


def packaged_db_titles():
    """
    ממפה מפתח-התאמה (sanitize_title של שם הקובץ) -> קבוצת שמות ה-DB (db_title)
    של קבצי הספרים הנארזים ל-otzaria_latest.zip. מפתח עם יותר משם DB אחד הוא
    דו-משמעי ואינו נבדק (הכפילות עצמה נתפסת ב-find_packaged_duplicates).
    """
    titles = {}
    for p in list_tracked_paths():
        if not p:
            continue
        norm = p.replace("\\", "/")
        if not any(norm.startswith(prefix) for prefix in DB_BOOK_PREFIXES):
            continue
        base, ext = os.path.splitext(norm.rsplit("/", 1)[-1])
        if ext.lower() not in DB_BOOK_EXTS:
            continue
        key = sanitize_title(base)
        if key:
            titles.setdefault(key, set()).add(db_title(base))
    return titles


def find_spelling_drift(entries, packaged):
    """
    מאתר שמות ForDB שמזהים קובץ ספר נארז אך *מאויתים אחרת* ממה שייכתב ל-book.title.
    זו בדיוק תקלת DROP-2: 'הגהות הב"ח על מסכת ברכות' (מרכאה ASCII) מול
    'הגהות הב״ח על מסכת ברכות' (גרשיים) - sanitize_title מזהה התאמה, אך
    applyGenerations משווה מחרוזות מדויקות ולכן מדלג על השורה בשקט.

    entries = איטרטור של (מזהה, שם גולמי). מחזיר [(מזהה, גולמי, נדרש)].
    """
    drift = []
    for identifier, raw in entries:
        if not raw:
            continue
        candidates = packaged.get(sanitize_title(raw))
        if not candidates or len(candidates) != 1:
            continue
        expected = next(iter(candidates))
        if raw != expected:
            drift.append((identifier, raw, expected))
    return drift


def find_dead_renames(rename_pairs, db_raw_titles):
    """
    מאתר שורות ב-book_renames.csv שהן no-op *ודאי*: לא שם המקור ולא שם היעד קיימים
    כמחרוזת מדויקת ב-book.title, אך קיים שם אחד בדיוק שנבדל מהם רק בפיסוק. אז ידוע
    בוודאות שהספר קיים תחת איות אחר, והשורה לעולם לא תתפוס
    (renameBookTitle: "Book rename: 'X' not found; no rows changed").

    הבדיקה נופלת רק כשאפשר *לנקוב* באיות הנכון, ולכן רשימת שמות חלקית (למשל
    SEFARIA_FETCH=0, שאז db_raw_titles מכיל רק ספרי אוצריא) גורמת לדילוג ולא
    להאשמת-שווא. מחזיר [(line_no, old, new, actual)].
    """
    by_key = {}
    for title in db_raw_titles:
        key = sanitize_title(title)
        if key:
            by_key.setdefault(key, set()).add(title)
    dead = []
    for line_no, old, new in rename_pairs:
        if not old or old in db_raw_titles or new in db_raw_titles:
            continue
        variants = by_key.get(sanitize_title(old), set())
        if len(variants) == 1:
            dead.append((line_no, old, new, next(iter(variants))))
    return dead


# העץ שממנו נמנים הספרים הנארזים. ברירת המחדל HEAD; `--tree <commit>` מאפשר לאמת
# commit זמני (git commit-tree על ה-index, ר' ADDING_BOOKS §7) בלי להעתיק את הסקריפט.
TREE_REF = "HEAD"


def list_tracked_paths():
    """
    מחזיר את רשימת הנתיבים העקובים ב-TREE_REF (ברירת מחדל HEAD) דרך `git ls-tree -r` (קורא את עץ
    הקומיט בלבד - אין צורך בהורדת תוכן הקבצים; עובד עם partial-clone + sparse).
    אם git אינו זמין, נופל ל-os.walk על עץ העבודה.
    """
    try:
        result = subprocess.run(
            ["git", "-C", REPO_ROOT, "ls-tree", "-r", TREE_REF, "--name-only", "-z"],
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
                      לתיקייה לא-נארזת (כגון extraBooks) ושומר מטא-דאטה ישנה.
      * sefaria_final = שמות ספרי *ספריא* בלבד (מנוקים, אחרי שינויי שם). משמש לבדיקת
                      דליפת-מקור: ספר ספריא הרשום ב-all_metadata.json עם Sourcefolder
                      לא-"sefaria" יידרס ל-Dicta/וכו' בשלב seed-המטא-דאטה.
    ספרי ספריא נוצרים בבנייה (אין להם קובץ מקומי), לכן הם נלקחים מה-API החי + המטא-דאטה.
    book_renames נבדק מול sources; generations/book_info/book_moves מול db_final; השאר מול final_canon.
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
        live = sefaria_live_titles()
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


_SEFARIA_LIVE = []  # cache בן איבר אחד: [set] אחרי משיכה, [] לפני


def sefaria_live_titles():
    """fetch_sefaria_titles ממוזערת לקריאה אחת בלבד (נצרכת גם ע"י בדיקת ה-renames)."""
    if not _SEFARIA_LIVE:
        _SEFARIA_LIVE.append(fetch_sefaria_titles())
    return _SEFARIA_LIVE[0]


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


def remove_orphans(path, col_name, db_final, srename, protected=frozenset()):
    """Remove logical CSV records while preserving every retained byte (including BOM)."""
    with open(path, "rb") as f:
        data = f.read()
    _bom, text = book_renames_follow._split_bom(data)
    records = book_renames_follow.csv_records(text)
    if not records:
        return []
    header = [book_renames_follow._csv_value(text, f) for f in records[0][2]]
    c_idx = col_index(header, col_name)
    removed, drop = [], []
    for idx, (start, _end, fields) in enumerate(records[1:], start=1):
        if len(fields) == 1 and book_renames_follow._csv_value(text, fields[0]) == "":
            continue
        if len(fields) != len(header):
            raise ValueError(f"{path}: record {idx + 1}: expected {len(header)} columns")
        raw_name = book_renames_follow._csv_value(text, fields[c_idx])
        clean = sanitize_title(raw_name)
        final = srename.get(clean, clean)
        if raw_name and final not in db_final and clean not in protected:
            removed.append((idx + 1, raw_name))
            drop.append(idx)
    if removed:
        result = book_renames_follow.edit_csv(data, {}, drop)
        with open(path, "wb") as f:
            f.write(result)
    return removed


IDENTITY_PATH = "ForDB/book_info_identity.json"


def validate_identity_ledger(ledger):
    if (not isinstance(ledger, dict) or set(ledger) != {"schemaVersion", "events"}
            or type(ledger["schemaVersion"]) is not int or ledger["schemaVersion"] != 1
            or not isinstance(ledger["events"], list)):
        raise ValueError("Invalid book_info identity ledger")
    for idx, event in enumerate(ledger["events"], start=1):
        if (not isinstance(event, dict) or type(event.get("id")) is not int
                or event["id"] != idx or event.get("kind") not in ("rename", "remove")):
            raise ValueError("Invalid identity event/order")
        required = {"id", "kind", "old", "commit", "new" if event["kind"] == "rename" else "reason"}
        if not required <= set(event) or set(event) - required - {"changeSetId"}:
            raise ValueError("Invalid identity event field set")
        for field in (["old", "new"] if event["kind"] == "rename" else ["old"]):
            value = event[field]
            if (not isinstance(value, dict) or set(value) != {"bookName", "authorName"}
                    or not all(isinstance(v, str) and not any(c in v for c in "\r\0\ufeff") for v in value.values())
                    or not value["bookName"]):
                raise ValueError("Invalid identity key")
        change_set = event.get("changeSetId")
        if change_set is not None and (not isinstance(change_set, str) or not change_set):
            raise ValueError("Invalid identity changeSetId")
        commit = event["commit"]
        if commit is None:
            if not change_set:
                raise ValueError("Identity event needs commit or changeSetId provenance")
        elif not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid identity commit provenance")
        if event["kind"] == "remove" and (not isinstance(event["reason"], str) or not event["reason"]):
            raise ValueError("Invalid identity removal reason")
    return ledger


def read_identity_ledger(rename_bases=()):
    path = os.path.join(REPO_ROOT, IDENTITY_PATH)
    ledger = (read_json(path) if os.path.exists(path) else {"schemaVersion": 1, "events": []})
    validate_identity_ledger(ledger)
    # Preserve every event from the worktree base, parent and last validated head.
    # The workflow supplies its last successful commit as the first rename base.
    refs = ["HEAD", "HEAD^"]
    base = book_renames_follow.pick_rename_base(REPO_ROOT, rename_bases)
    if base:
        refs.append(base)
    for ref in refs:
        previous = book_renames_follow._git(REPO_ROOT, "show", f"{ref}:{IDENTITY_PATH}", check=False)
        if previous.returncode:
            continue  # Initial introduction/first commit has no previous ledger.
        trusted = validate_identity_ledger(json.loads(previous.stdout.decode("utf-8")))
        events = trusted["events"]
        if ledger["events"][:len(events)] != events:
            raise ValueError(f"Identity ledger is append-only: historical prefix from {ref} changed")
    return ledger


def book_info_identities():
    if not os.path.exists(BOOK_INFO):
        return set()
    _header, rows = read_csv_rows(BOOK_INFO, True)
    return {(r[0], r[1]) for r in rows if r}


def record_identity_changes(before, ledger, resolution, removed, plan):
    """Append exact per-author rename/removal events for the same autofix commit.

    IDs are monotonic revisions. Consumers replay events AFTER the proposal's
    base revision; historical mappings must never redirect a newly reused key.
    """
    after = book_info_identities()
    matcher = book_renames_follow._Matcher(resolution.renames, sanitize_title, db_title)
    orphan_titles = {name for path, name, reason in removed if path == "ForDB/book_info.csv" and reason == "orphan"}
    source_head = book_renames_follow._git(REPO_ROOT, "rev-parse", "HEAD").stdout.decode().strip()
    changed = False
    for title, author in sorted(before - after):
        old = {"bookName": title, "authorName": author}
        hit = matcher.find(title)
        if hit and (db_title(hit[1].new_title), author) in after:
            event = {"kind": "rename", "old": old,
                     "new": {"bookName": db_title(hit[1].new_title), "authorName": author},
                     "commit": hit[1].commit if re.fullmatch(r"[0-9a-f]{40}", hit[1].commit) else source_head}
        elif title in orphan_titles:
            event = {"kind": "remove", "old": old, "reason": "orphan", "commit": source_head}
        else:
            continue
        event = {"id": len(ledger["events"]) + 1, **event}
        ledger["events"].append(event)
        changed = True
    if changed:
        validate_identity_ledger(ledger)
        data = (json.dumps(ledger, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with open(os.path.join(REPO_ROOT, IDENTITY_PATH), "wb") as f:
            f.write(data)
        plan.writes[IDENTITY_PATH] = data


def preflight_csv_inputs():
    """Validate all editable tables before the first rename/prune write."""
    for target in book_renames_follow.CSV_TARGETS:
        path = os.path.join(REPO_ROOT, target.path)
        if not os.path.exists(path):
            if path == BOOK_INFO:
                continue  # PR55 transition; mandatory in PR56.
            raise FileNotFoundError(path)
        if path == BOOK_INFO:
            with open(path, "rb") as handle:
                validate_book_info(handle.read())
        header, rows = read_csv_rows(path, True)
        col_index(header, target.column)
        if path == BOOK_INFO and header != ["bookName", "authorName", "generationName",
                                           "subGenerationName", "startYear", "endYear"]:
            raise ValueError("book_info.csv must have the supported six-column header")
        for idx, row in enumerate(rows, start=2):
            if row and len(row) != len(header):
                raise ValueError(f"{path}: record {idx}: expected {len(header)} columns")


# ---------------------------------------------------------------------------
# מעקב שינויי-שם של קבצי ספרים
# ---------------------------------------------------------------------------
def links_roots_at_head():
    """שורשי ה-links הנארזים (expected_state=present). נקרא מ-HEAD, כי
    manual_links_sync.json אינו ב-sparse-checkout של ה-workflow."""
    result = subprocess.run(
        ["git", "-C", REPO_ROOT, "show", f"HEAD:{LINKS_SYNC_CONFIG}"], capture_output=True
    )
    if result.returncode != 0:
        # אין הגדרת שורשים => אין קישורים נארזים שאפשר ליישר; שאר הקבצים עדיין נעקבים.
        print(f"::warning::{LINKS_SYNC_CONFIG} אינו ב-HEAD; שינויי-שם לא יושרו בקבצי הקישורים.")
        return []
    config = json.loads(result.stdout.decode("utf-8"))
    return [r["path"] for r in config.get("links_roots", []) if r.get("expected_state") == "present"]


def follow_book_renames(bases, db_final, srename, apply):
    """מזהה שינויי-שם בטווח שטרם אומת ומתכנן (ובמצב apply גם כותב) את יישורם.

    מחזיר (resolution, plan, base, held_referenced). held_referenced = שמות ששונו אך לא
    ניתן ליישרם בבטחה *והם מוזכרים* בקובץ יעד — אלה מפילים את הריצה. בלי בסיס זמין לא
    נעקב דבר, וההתנהגות זהה לזו שלפני המעקב (יתומים מוסרים)."""
    resolution = book_renames_follow.RenameResolution()
    plan = book_renames_follow.RenamePlan()
    if not bases:
        return resolution, plan, None, set()
    base = book_renames_follow.pick_rename_base(REPO_ROOT, bases)
    if base is None:
        print("::warning::אין בסיס זמין למעקב אחרי שינויי-שם; שורות יתומות יוסרו בלי לבדוק אם הספר רק שינה שם.")
        return resolution, plan, None, set()

    head_paths = {p for p in list_tracked_paths() if p}

    def is_db_path(path):
        return path.startswith(DB_BOOK_PREFIXES) and path.lower().endswith(DB_BOOK_EXTS)

    def is_live_key(key):
        return srename.get(key, key) in db_final

    rename_keys = set(srename) | set(srename.values())

    # respell (שינוי איות בלבד) דורש לדעת שהאיות הישן אינו כותרת של ספר חי — כולל
    # ספריא. בלי הקטלוג החי אין ודאות, ולכן respell כבוי ובדיקת האיות מדווחת כרגיל.
    is_live_spelling = None
    live_titles = sefaria_live_titles() if SEFARIA_FETCH else None
    if live_titles is not None:
        live_spellings = set(live_titles) | {db_title(t) for t in live_titles}
        for candidates in packaged_db_titles().values():
            live_spellings |= candidates

        def is_live_spelling(spelling):
            return spelling in live_spellings

    events = book_renames_follow.read_path_events(REPO_ROOT, base)
    resolution = book_renames_follow.resolve_renames(
        events,
        lambda: book_renames_follow.read_net_renames(REPO_ROOT, base),
        head_paths,
        is_db_path,
        sanitize_title,
        is_live_key,
        rename_keys,
        db_title=db_title,
        is_live_spelling=is_live_spelling,
    )
    print(
        f"[renames] בסיס {base[:12]}..HEAD: {len(events)} שינויי קבצי .txt, "
        f"{len(resolution.renames)} שינויי-שם ליישור, {len(resolution.held_keys)} שלא ניתן ליישר"
    )

    roots = []
    if resolution.renames or resolution.held_keys:
        roots = links_roots_at_head()
        book_renames_follow.ensure_in_worktree(
            REPO_ROOT, [t.path for t in book_renames_follow.JSON_TARGETS] + roots
        )
    if resolution.renames:
        plan = book_renames_follow.plan_renames(
            REPO_ROOT, resolution.renames, db_title, sanitize_title, DB_BOOK_PREFIXES, roots
        )
        for key, reason in plan.blocked.items():
            rename = resolution.renames.pop(key)
            if rename.respell:
                # תיקון איות שלא ניתן להחיל נשאר בידי בדיקת האיות (report-only, מפיל).
                print(f"[renames] תיקון האיות {rename.old_title!r} → {rename.new_title!r} לא הוחל: {reason}")
            else:
                resolution.blocked[key] = reason
    held_referenced = set()
    if resolution.held_keys:
        held_referenced = book_renames_follow.find_references(
            REPO_ROOT, resolution.held_keys, sanitize_title, roots
        )
    if apply:
        book_renames_follow.apply_plan(REPO_ROOT, plan)
    return resolution, plan, base, held_referenced


def pending_rename_map(resolution, applied):
    """שם ישן (מנוקה) -> שם חדש (מנוקה) לשינויי-שם שעוד לא הוחלו.

    ב-PR השורות עדיין נושאות את השם הישן, וה-auto-fix ב-main יחליף אותן — לכן
    בודקים אותן בשם החדש, כמו שיהיו אחרי המיזוג. ב--fix הן כבר הוחלפו."""
    if applied:
        return {}
    return {
        sanitize_title(spelling): sanitize_title(db_title(r.new_title))
        for r in resolution.renames.values()
        for spelling in (r.old_title, db_title(r.old_title))
    }


def print_rename_report(resolution, plan, applied):
    if not resolution.renames and not resolution.held_keys:
        return
    verb = "יושרו" if applied else "ייושרו אוטומטית במיזוג ל-main"
    if resolution.renames:
        print(f"\n🔁 {len(resolution.renames)} ספרים ששמם שונה — הרשומות שלהם {verb} לשם החדש:")
        for key in sorted(resolution.renames):
            r = resolution.renames[key]
            note = "  [איות בלבד]" if r.respell else ""
            print(f"     - {r.old_title!r} → {r.new_title!r}  ({r.commit[:10]}){note}")
            for change in plan.changes:
                if change.rename_key == key:
                    print(f"         · {change.path}: {change.kind} {change.detail}")
    for key in sorted(resolution.ambiguous):
        print(f"\n⚠️  השם {key!r} שונה ליותר מיעד אחד: {resolution.ambiguous[key]}")
    for key in sorted(resolution.blocked):
        print(f"\n⚠️  השם {key!r} שונה, אך לא יושר: {resolution.blocked[key]}")


def write_fix_outputs(removed, resolution, plan):
    """דוחות --fix ל-workflow. דבר לא נכתב כשלא השתנה דבר."""
    touched = set(plan.touched) | {file_label for file_label, _name, _reason in removed}
    if not touched:
        return
    changed_keys = {c.rename_key for c in plan.changes}
    if removed:
        with open(REMOVED_REPORT, "w", encoding="utf-8") as f:
            json.dump(
                [{"file": file_label, "name": name, "reason": reason} for file_label, name, reason in removed],
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")
    if plan.changes:
        with open(RENAMED_REPORT, "w", encoding="utf-8") as f:
            json.dump(
                [
                    {
                        "old": r.old_title,
                        "new": r.new_title,
                        "commit": r.commit,
                        "changes": [
                            {"file": c.path, "kind": c.kind, "detail": c.detail}
                            for c in plan.changes
                            if c.rename_key == key
                        ],
                    }
                    for key, r in sorted(resolution.renames.items())
                    if key in changed_keys
                ],
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")
    with open(TOUCHED_LIST, "w", encoding="utf-8") as f:
        f.write("".join(path + "\0" for path in sorted(touched)))

    if plan.changes and removed:
        subject = "ci(fordb): follow book renames and remove inputs that cannot be applied"
    elif plan.changes:
        subject = "ci(fordb): follow book renames"
    else:
        subject = "ci(fordb): remove inputs that cannot be applied"
    body = []
    for key, r in sorted(resolution.renames.items()):
        if key not in changed_keys:
            continue
        body.append(f"- {r.old_title} → {r.new_title} (renamed in {r.commit[:10]})")
    for file_label, name, reason in removed:
        body.append(f"- removed [{reason}] {file_label}: {name}")
    with open(COMMIT_MESSAGE, "w", encoding="utf-8") as f:
        f.write(subject + "\n\n" + "\n".join(body) + "\n")


# ---------------------------------------------------------------------------
# הבדיקה
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="אימות שמות ForDB מול רשימת הספרים הקנונית.")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="הסרת שורות יתומות דטרמיניסטיות מ-generations/book_info/book_moves וכפילויות מקור-ספריא",
    )
    parser.add_argument(
        "--rename-base",
        action="append",
        default=[],
        metavar="COMMIT",
        help="קומיט שממנו ואילך ההיסטוריה טרם אומתה (ניתן לחזור; הראשון שהוא אב של HEAD נבחר). "
        "שינויי-שם של קבצי ספרים בטווח מיושרים במקום שהשורות יימחקו כיתומות.",
    )
    parser.add_argument(
        "--tree",
        default="HEAD",
        metavar="COMMIT",
        help="העץ שממנו נמנים קבצי הספרים הנארזים (ברירת מחדל HEAD). מיועד לאימות commit זמני "
        "שנבנה מה-index; לא משולב עם --fix.",
    )
    args = parser.parse_args()
    global TREE_REF
    TREE_REF = args.tree
    if args.fix and args.tree != "HEAD":
        print("::error::--fix פועל רק על HEAD.")
        return 2
    if args.fix and not SEFARIA_FETCH:
        print("::error::--fix דורש SEFARIA_FETCH=1; מסרבים למחוק מול רשימת ספריא חלקית.")
        return 2
    if args.fix:
        for stale in FIX_OUTPUTS:
            if os.path.exists(stale):
                os.unlink(stale)

    preflight_csv_inputs()
    identity_ledger = read_identity_ledger(args.rename_base)
    identities_before = book_info_identities()
    rename_pairs = load_rename_pairs()
    srename = build_sanitized_rename(rename_pairs)
    sources, final_canon, db_final, sefaria_final = load_canonical(srename)

    # 0) שינויי-שם של קבצי ספרים בטווח שטרם אומת. חייב לרוץ לפני הסרת היתומים:
    #    שורה שהתייתמה רק כי הקובץ שונה בשמו מקבלת את השם החדש, בכל הקבצים.
    #    ב-report-only (PR) רק מדווחים; דבר לא נכתב.
    resolution, rename_plan, _rename_base, held_referenced = follow_book_renames(
        args.rename_base, db_final, srename, apply=args.fix
    )

    # failures[file] = list of (line/identifier, raw_name, checked_name)
    failures = {}

    pending_renames = pending_rename_map(resolution, applied=args.fix)

    def check_db_name(file_label, identifier, raw_name, canon):
        """
        בודק שם 'כפי שיהיה ב-DB': מנקה (sanitize), מחיל את שינוי-השם (srename),
        ומוודא קיום ב-canon (final_canon למטא-דאטה, db_final למה שחייב להתאים ל-book.title).
        """
        if raw_name is None or raw_name == "":
            return
        clean = sanitize_title(raw_name)
        clean = pending_renames.get(clean, clean)
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

    # 2) generations.csv + book_info.csv + 4) book_moves.csv - עמודות "שם ספר"/"bookName"/"name". חייבים להתאים
    #    בדיוק ל-book.title שב-DB (db_final); ספר שאינו נארז (כגון שהוזז ל-extraBooks) ייתפס.
    #    ב--fix שורות יתומות מוסרות; במצב report-only הן מדווחות ומפילות.
    removed = []  # [(file_label, name, reason)]
    for file_label, path, col in (
        ("ForDB/generations.csv", GENERATIONS, "שם ספר"),
        ("ForDB/book_info.csv", BOOK_INFO, "bookName"),
        ("ForDB/book_moves.csv", BOOK_MOVES, "name"),
    ):
        if path == BOOK_INFO and not os.path.exists(path):
            continue
        if args.fix:
            removed.extend(
                (file_label, name, "orphan")
                for _line_no, name in remove_orphans(
                    path, col, db_final, srename, protected=resolution.held_keys
                )
            )
        # ב--fix נשארו כאן רק שורות מוגנות (שינוי-שם שלא יושר) — והן מדווחות ומפילות.
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

    # 7) איות מדויק מול קבצי הספרים הנארזים. הבדיקות 1-5 מתבצעות במרחב ה-*מנוקה*
    #    (sanitize_title מסיר מרכאות), ולכן שם שנכתב "הגהות הב"ח..." עובר אותן אף
    #    שהספר נשמר ב-DB כ-"הגהות הב״ח...". הצרכנים משווים מחרוזות מדויקות, אז
    #    השורה נופלת בשקט (SeedGenerations: "unmatched book title(s) (skipped)").
    #    נבדק רק כשקיים קובץ ספר נארז יחיד עם אותו מפתח מנוקה - אז האיות הנדרש ידוע.
    #    ForDB/sefaria_metadata_changes.csv מוחרג בכוונה: שמותיו הם כותרות *ספריא*
    #    שעשויות להתנגש במרחב המנוקה עם קובץ אוצריא ולהיות שתיהן ב-DB. דוגמה חיה:
    #    'תשובות הריטב"א' (ספריא) מול 'תשובות הריטב״א' (MoreBooks) - שני ספרים שונים.
    packaged_titles = packaged_db_titles()
    spelling = {}

    def collect_spelling(file_label, entries):
        drift = find_spelling_drift(entries, packaged_titles)
        if drift:
            spelling[file_label] = drift

    collect_spelling(
        "ForDB/book_renames.csv",
        [(f"שורה {line_no} (שם מקור)", old) for line_no, old, _new in load_rename_pairs()]
        + [(f"שורה {line_no} (שם יעד)", new) for line_no, _old, new in load_rename_pairs()],
    )
    for file_label, path, col in (
        ("ForDB/generations.csv", GENERATIONS, "שם ספר"),
        ("ForDB/book_info.csv", BOOK_INFO, "bookName"),
        ("ForDB/book_moves.csv", BOOK_MOVES, "name"),
    ):
        if path == BOOK_INFO and not os.path.exists(path):
            continue
        header, rows = read_csv_rows(path, has_header=True)
        c_idx = col_index(header, col)
        collect_spelling(
            file_label,
            [(f"שורה {line_no}", row[c_idx]) for line_no, row in enumerate(rows, start=2) if len(row) > c_idx],
        )
    collect_spelling(
        "ForDB/all_metadata.json",
        [(f"רשומה {idx}", entry.get("title")) for idx, entry in enumerate(read_json(FORDB_METADATA))],
    )

    # 8) שינויי-שם מתים: המקור אינו book.title קיים, אך קיים ספר שנבדל ממנו רק
    #    בפיסוק. זהו בדיוק המצב של 'רדק על דברי הימים א׳' מול 'רד"ק על דברי הימים א׳'
    #    שנשאר no-op בכל מחזור. בדיקה 1 עובדת במרחב המנוקה ולכן אינה רואה זאת.
    db_raw_titles = set()
    for candidates in packaged_titles.values():
        db_raw_titles |= candidates
    live_titles = sefaria_live_titles() if SEFARIA_FETCH else None
    if live_titles:
        db_raw_titles |= set(live_titles)
    dead_renames = find_dead_renames(rename_pairs, db_raw_titles)

    print_rename_report(resolution, rename_plan, applied=args.fix)
    if args.fix:
        record_identity_changes(identities_before, identity_ledger, resolution, removed, rename_plan)
        write_fix_outputs(removed, resolution, rename_plan)
    if args.fix and removed:
        print(f"\n🧹 הוסרו אוטומטית {len(removed)} רשומות ForDB שלא היו מיושמות בריצה:")
        for file_label, name, reason in removed:
            print(f"     - [{reason}] {file_label}: {name!r}")

    # ----- דוח -----
    total = sum(len(v) for v in failures.values())
    if (
        total == 0
        and not duplicates
        and not source_leaks
        and not spelling
        and not dead_renames
        and not held_referenced
    ):
        print(
            "\n✅ כל שמות הספרים ב-ForDB קיימים ברשימת הספרים הקנונית, מאויתים כפי שייכתבו "
            "ל-book.title, אין כפילויות שם בתיקיות הנארזות, ואין דליפת-מקור."
        )
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

    if spelling:
        drift_total = sum(len(v) for v in spelling.values())
        print(f"\n❌ נמצאו {drift_total} שמות ב-ForDB שמזהים קובץ ספר נארז אך מאויתים אחרת מ-book.title.")
        print("   הצרכנים (applyGenerations / renameBookTitle / applyMetadata) משווים מחרוזות *מדויקות*,")
        print("   ולכן שורות אלה נופלות בשקט. יש להעתיק את האיות הנדרש כלשונו:\n")
        for file_label in sorted(spelling):
            print(f"  📄 {file_label} ({len(spelling[file_label])}):")
            for identifier, raw_name, expected in spelling[file_label]:
                print(f"     - {identifier}: {raw_name!r} → נדרש {expected!r}")
            print()

    if dead_renames:
        print(f"\n❌ נמצאו {len(dead_renames)} שורות ב-ForDB/book_renames.csv שהן no-op ודאי:")
        print("   שם המקור אינו book.title קיים, והספר קיים תחת איות שנבדל רק בפיסוק.")
        print("   יש לתקן את שם המקור לאיות האמיתי, או להסיר את השורה אם השינוי כבר לא רצוי:\n")
        for line_no, old, new, actual in dead_renames:
            print(f"     - שורה {line_no}: {old!r} -> {new!r};  הכותרת בפועל: {actual!r}")
        print()

    if held_referenced:
        print(f"\n❌ {len(held_referenced)} ספרים שונו בשמם, והרשומות שלהם לא יושרו אוטומטית ולא נמחקו:")
        print("   יש ליישר ידנית את השם בקבצי ForDB, ב-metadata.json ובקבצי הקישורים:\n")
        for key in sorted(held_referenced):
            reason = resolution.blocked.get(key) or f"כמה יעדים: {resolution.ambiguous.get(key)}"
            print(f"     - {key!r}: {reason}")
        print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
