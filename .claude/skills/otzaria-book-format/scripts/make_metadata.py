#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""יצירת רשומת מטא-דאטה לספר חדש, בדיקת התנגשות שם, ומיזוג ל-all_metadata.json; שורת תיאור ל-ForDB/sefaria_metadata_changes.csv.

  # יצירת רשומה והדפסתה
  python -X utf8 make_metadata.py --title "שם הספר" --author "שם המחבר" \
      --era אחרונים --pub-date 1902 --pub-place ירושלים \
      --source-folder MoreBooks

  # בדיקת התנגשות שם מול הקורפוס לפני שמוסיפים
  python -X utf8 make_metadata.py --title "שם הספר" --check-name --repo D:/otzaria-library

  # מיזוג לקובץ (מעדכן רשומה קיימת לפי title, אחרת מוסיף)
  python -X utf8 make_metadata.py --title "…" --author "…" \
      --merge D:/otzaria-library/all_metadata.json

  # תיאור → רק ForDB/sefaria_metadata_changes.csv, לא ל-JSON: המחולל (SeforimLibrary) קורא
  # את metadata.json דרך BookMetadata, שאין בה heDesc (נזרק בשקט), ו-ForDB/all_metadata.json
  # בלי שדות תיאור בכלל. ה-CSV הוא הדרך היחידה של תיאור ל-DB, לכל ספר (גם מקורות אוצריא).
  python -X utf8 make_metadata.py --title "…" --author "…" --category-path "…/…" \
      --he-short-desc "…" --he-desc "…" \
      --desc-csv D:/otzaria-library/ForDB/sefaria_metadata_changes.csv

  # שורת דור ל-ForDB/book_info.csv
  python -X utf8 make_metadata.py --title "…" --generation אחרונים --print-fordb

השדות והמשמעויות: references/metadata.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
import io

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".github" / "scripts"))
from book_info_writer import HEADER as BOOK_INFO_HEADER, GENERATIONS, plan_registration, apply_registration, encode_rows

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SANITIZE_STRIP = re.compile(r"[֑-ׇ]")
SANITIZE_ILLEGAL = re.compile(r"[\\/:*\"״?<>|]")

ERAS = {
    "תנאים": "Tannaim", "אמוראים": "Amoraim", "גאונים": "Gaonim",
    "ראשונים": "Rishonim", "אחרונים": "Achronim", "מחברי זמננו": "Contemporary",
}


def sanitize_filename(name: str) -> str:
    s = SANITIZE_STRIP.sub("", name)
    s = SANITIZE_ILLEGAL.sub("", s)
    s = s.replace("_", " ").replace("''", "").replace("'", "")
    return s.strip()


def normalize_hebrew_label(raw: str) -> str:
    """מראה של normalizeHebrewLabel ב-SeforimLibrary (Generator.kt) — כך ייראה ה-title
    ב-seforim.db, ולכן זה מפתח ההתאמה בעמודת title של sefaria_metadata_changes.csv."""
    s = raw.strip()
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace('"', "\u05f4").replace("''", "\u05f4").replace("\u05f3\u05f3", "\u05f4")
    s = s.replace("`", "\u05f3")
    return re.sub(r"\s+", " ", s).strip()


def build_record(a: argparse.Namespace) -> dict:
    he_era = a.era or None
    return {
        "heSeries": a.he_series or None,
        "series": None,
        "series-index": a.series_index,
        "authors": [],
        "heAuthors": list(a.author),
        "title": a.title,
        "enTitle": a.en_title or None,
        "enDesc": None,
        "enShortDesc": None,
        "heDesc": None,       # תיאור → sefaria_metadata_changes.csv (upsert_description)
        "heShortDesc": None,
        "publisher": a.publisher or None,
        "categories": None,
        "heCategories": list(a.he_categories) or None,
        "era": ERAS.get(he_era or "", None),
        "heEra": he_era,
        "language": "he",
        "pubDate": [a.pub_date] if a.pub_date else None,
        "compDate": [a.comp_date] if a.comp_date else None,
        "pubPlace": None,
        "compPlace": None,
        "compDateStringEn": None,
        "compDateStringHe": None,
        "pubDateStringEn": None,
        "pubDateStringHe": None,
        "compPlaceStringEn": None,
        "compPlaceStringHe": a.comp_place or None,
        "pubPlaceStringEn": None,
        "pubPlaceStringHe": a.pub_place or None,
        "extraTitlesHe": list(a.extra_title),
        "extraTitlesEn": [],
        "original_title": None,
        "order": a.order,
        "compDateHeb": [],
        "pubDateHeb": [a.pub_date_heb] if a.pub_date_heb else [],
        "heDescNew": None,
        "Sourcefolder": a.source_folder,
    }


def check_name(title: str, repo: Path) -> int:
    target = sanitize_filename(title)
    hits: list[str] = []

    meta_path = repo / "all_metadata_with_file_paths.json"
    if not meta_path.exists():
        meta_path = repo / "all_metadata.json"
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        for rec in data:
            t = rec.get("title")
            if t and sanitize_filename(t) == target:
                hits.append(f"מטא-דאטה: {t!r} (מקור: {rec.get('Sourcefolder')})")

    for book in repo.rglob("*.txt"):
        parts = book.parts
        if "אוצריא" not in parts:
            continue
        if sanitize_filename(book.stem) == target:
            hits.append(f"קובץ: {book}")

    if hits:
        print(f"התנגשות עבור {target!r} — {len(hits)} התאמות:")
        for h in hits[:20]:
            print(f"  {h}")
        if len(hits) > 20:
            print(f"  … ועוד {len(hits) - 20}")
        return 1
    print(f"אין התנגשות: {target!r} פנוי")
    return 0


def merge(record: dict, path: Path) -> None:
    raw = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    data = json.loads(raw) if raw else []
    if not isinstance(data, list):
        raise SystemExit(f"{path} אינו מערך")
    for i, rec in enumerate(data):
        if rec.get("title") == record["title"]:
            merged = dict(rec)
            merged.update({k: v for k, v in record.items() if v not in (None, [], "")})
            data[i] = merged
            print(f"עודכנה רשומה קיימת: {record['title']!r}")
            break
    else:
        data.append(record)
        print(f"נוספה רשומה: {record['title']!r} (סה\"כ {len(data)})")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


DESC_CSV_HEADER = ["categoryPath", "title", "author", "heShortDesc", "heDesc", "heDescNew"]


def upsert_description(path: Path, title: str, category_path: str, author: str,
                       short: str | None, long: str | None) -> None:
    """שורת תיאור ב-ForDB/sefaria_metadata_changes.csv.

    הצרכן (SeedAllMetadataPostProcess.kt) קורא לפי מיקום: עמ' 2 title (התאמה מדויקת),
    עמ' 4 heShortDesc → book.heShortDesc, עמ' 6 heDescNew → book.heDesc. עמ' 5 (heDesc
    המקורי של ספריא) נשארת ריקה בספרים שלנו; categoryPath ו-author לקורא האנושי בלבד.
    תא ריק = "השאר את הקיים" — לכן ערך ריק לא דורס. שם כפול: האחרונה גוברת.
    פורמט: UTF-8 בלי BOM, LF, QUOTE_ALL — כתיבה מחדש עושה round-trip זהה בית-בבית.
    """
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != DESC_CSV_HEADER:
        raise SystemExit(f"{path}: שורת כותרת לא צפויה (מצופה {','.join(DESC_CSV_HEADER)})")
    hits = [i for i, r in enumerate(rows) if i and len(r) > 1 and r[1].strip() == title]
    if hits:
        row = rows[hits[-1]]
        row += [""] * (len(DESC_CSV_HEADER) - len(row))
        for idx, val in ((0, category_path), (2, author), (3, short), (5, long)):
            if val:
                row[idx] = val
        dup = f" (אזהרה: {len(hits)} שורות באותו שם)" if len(hits) > 1 else ""
        print(f"עודכנה שורת תיאור: {title!r}{dup}")
    else:
        rows.append([category_path or "", title, author or "", short or "", "", long or ""])
        print(f"נוספה שורת תיאור: {title!r}")
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n").writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="מטא-דאטה לספר אוצריא")
    ap.add_argument("--title", required=True, help="שם הספר — מפתח ההתאמה")
    ap.add_argument("--author", action="append", default=[], help="מחבר בעברית (חזרתי)")
    ap.add_argument("--en-title")
    ap.add_argument("--he-desc", help="תיאור ארוך → עמודת heDescNew ב-CSV (דורש --desc-csv)")
    ap.add_argument("--he-short-desc", help="תיאור קצר → עמודת heShortDesc ב-CSV (דורש --desc-csv)")
    ap.add_argument("--desc-csv", help="ForDB/sefaria_metadata_changes.csv — היעד היחיד לתיאור")
    ap.add_argument("--category-path", default="", help="נתיב הקטגוריה תחת אוצריא/ (לעמודה האינפורמטיבית)")
    ap.add_argument("--he-categories", action="append", default=[])
    ap.add_argument("--era", choices=list(ERAS), help="תקופה")
    ap.add_argument("--pub-date", type=int, help="שנת דפוס (מספר)")
    ap.add_argument("--pub-date-heb", help="שנת דפוס בעברית, למשל ה׳תרס״ב")
    ap.add_argument("--comp-date", type=int)
    ap.add_argument("--pub-place", help="מקום דפוס בעברית")
    ap.add_argument("--comp-place", help="מקום חיבור בעברית")
    ap.add_argument("--publisher")
    ap.add_argument("--he-series")
    ap.add_argument("--series-index", type=int)
    ap.add_argument("--extra-title", action="append", default=[], help="שם נוסף (חזרתי)")
    ap.add_argument("--order", type=int, help="סדר בקטגוריה (ריק = 999)")
    ap.add_argument("--source-folder", default="MoreBooks", help="תיקיית המקור")
    ap.add_argument("--generation", choices=sorted(GENERATIONS - {""}), help="קבוצת דור ל-ForDB/book_info.csv")
    ap.add_argument("--sub-generation", default="")
    ap.add_argument("--start-year", default="")
    ap.add_argument("--end-year", default="")
    ap.add_argument("--book-info-csv", help="רישום מחברים במקור הקנוני בלי לדרוס מידע קיים")
    ap.add_argument("--check-name", action="store_true", help="בדיקת התנגשות שם בקורפוס")
    ap.add_argument("--repo", default=".", help="שורש otzaria-library לבדיקת השם")
    ap.add_argument("--merge", help="קובץ all_metadata.json למיזוג")
    ap.add_argument("--print-fordb", action="store_true", help="הדפסת שורות ForDB מוצעות")
    args = ap.parse_args()

    info_rows = [[normalize_hebrew_label(sanitize_filename(args.title)), author,
                  args.generation or "", args.sub_generation, args.start_year, args.end_year]
                 for author in args.author or [""]]
    info_plan = None
    if args.book_info_csv:
        target = Path(args.book_info_csv).resolve()
        if target.name != "book_info.csv" or target.parent.name != "ForDB":
            ap.error("--book-info-csv must point to ForDB/book_info.csv")
        info_plan = plan_registration(target.parent.parent, info_rows)
    status = 0
    if args.check_name:
        status = check_name(args.title, Path(args.repo))

    record = build_record(args)
    if args.merge:
        merge(record, Path(args.merge))
    elif not args.desc_csv:
        print(json.dumps(record, ensure_ascii=False, indent=2))

    if args.he_desc or args.he_short_desc:
        desc_title = normalize_hebrew_label(sanitize_filename(args.title))
        if args.desc_csv:
            upsert_description(Path(args.desc_csv), desc_title, args.category_path,
                               ", ".join(args.author), args.he_short_desc, args.he_desc)
            print("ה-title בשורה חייב להיות שם קובץ ה-.txt בלי סיומת (אחרי normalizeHebrewLabel).")
        else:
            print("\nתיאור לא נכתב: הוא לא נכנס לרשומת ה-JSON — הוסיפו --desc-csv "
                  "ForDB/sefaria_metadata_changes.csv", file=sys.stderr)
            status = status or 2

    if info_plan is not None:
        apply_registration(Path(args.book_info_csv).resolve().parent.parent, info_plan)

    if args.print_fordb:
        print("\n--- ForDB ---")
        if args.generation:
            print("book_info.csv:")
            print(encode_rows(info_rows), end="")
        print("שם הספר בכל שורת ForDB חייב להתאים תו-בתו לשם הספר במאגר.")

    expected = sanitize_filename(args.title)
    if expected != args.title:
        print(f"\nשם הקובץ המנוקה יהיה: {expected}.txt  (ה-<h1> שומר את הצורה המלאה)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
