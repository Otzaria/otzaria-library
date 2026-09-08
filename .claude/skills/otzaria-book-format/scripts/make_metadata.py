#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""יצירת רשומת מטא-דאטה לספר חדש, בדיקת התנגשות שם, ומיזוג ל-all_metadata.json.

  # יצירת רשומה והדפסתה
  python -X utf8 make_metadata.py --title "שם הספר" --author "שם המחבר" \
      --he-short-desc "תיאור קצר" --era אחרונים --pub-date 1902 --pub-place ירושלים \
      --source-folder MoreBooks

  # בדיקת התנגשות שם מול הקורפוס לפני שמוסיפים
  python -X utf8 make_metadata.py --title "שם הספר" --check-name --repo D:/otzaria-library

  # מיזוג לקובץ (מעדכן רשומה קיימת לפי title, אחרת מוסיף)
  python -X utf8 make_metadata.py --title "…" --author "…" \
      --merge D:/otzaria-library/all_metadata.json

  # שורת דור ל-ForDB/generations.csv
  python -X utf8 make_metadata.py --title "…" --generation אחרונים --print-fordb

השדות והמשמעויות: references/metadata.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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
        "heDesc": a.he_desc or None,
        "heShortDesc": a.he_short_desc or None,
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


def main() -> int:
    ap = argparse.ArgumentParser(description="מטא-דאטה לספר אוצריא")
    ap.add_argument("--title", required=True, help="שם הספר — מפתח ההתאמה")
    ap.add_argument("--author", action="append", default=[], help="מחבר בעברית (חזרתי)")
    ap.add_argument("--en-title")
    ap.add_argument("--he-desc")
    ap.add_argument("--he-short-desc")
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
    ap.add_argument("--generation", help="קבוצת דור ל-ForDB/generations.csv")
    ap.add_argument("--check-name", action="store_true", help="בדיקת התנגשות שם בקורפוס")
    ap.add_argument("--repo", default=".", help="שורש otzaria-library לבדיקת השם")
    ap.add_argument("--merge", help="קובץ all_metadata.json למיזוג")
    ap.add_argument("--print-fordb", action="store_true", help="הדפסת שורות ForDB מוצעות")
    args = ap.parse_args()

    status = 0
    if args.check_name:
        status = check_name(args.title, Path(args.repo))

    record = build_record(args)
    if args.merge:
        merge(record, Path(args.merge))
    else:
        print(json.dumps(record, ensure_ascii=False, indent=2))

    if args.print_fordb:
        print("\n--- ForDB ---")
        if args.generation:
            print(f'generations.csv:  "{args.title}","{args.generation}"')
        print("שם הספר בכל שורת ForDB חייב להתאים תו-בתו לשם הספר במאגר.")

    expected = sanitize_filename(args.title)
    if expected != args.title:
        print(f"\nשם הקובץ המנוקה יהיה: {expected}.txt  (ה-<h1> שומר את הצורה המלאה)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
