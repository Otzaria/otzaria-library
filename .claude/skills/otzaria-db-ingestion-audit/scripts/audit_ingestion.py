#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit whether a commentary book was correctly ingested into Otzaria seforim.db."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


COMMENTARY_TYPE_ID = 1


def resolve_db(path: str | None) -> Path:
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        return p

    prefs = Path.home() / "AppData/Roaming/otzaria/shared_preferences.json"
    if prefs.exists():
        import re

        text = prefs.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'"flutter\.key-library-path"\s*:\s*"([^"]+)"', text)
        if m:
            lib = Path(m.group(1).replace("\\\\", "\\"))
            cand = lib / "seforim.db"
            if cand.exists():
                return cand

    fallback = Path(r"C:\ProgramData\otzaria\books\seforim.db")
    if fallback.exists():
        return fallback
    raise FileNotFoundError("seforim.db not found; pass --db")


def book_by_title(cur: sqlite3.Cursor, title: str):
    return cur.execute(
        "SELECT id, title, totalLines, orderIndex, hasCommentaryConnection "
        "FROM book WHERE title=?",
        (title,),
    ).fetchone()


def line_count(cur: sqlite3.Cursor, book_id: int) -> int:
    return cur.execute(
        "SELECT COUNT(*) FROM line WHERE bookId=?", (book_id,)
    ).fetchone()[0]


def line_map(cur: sqlite3.Cursor, book_id: int) -> dict[int, int]:
    return {
        li: lid
        for li, lid in cur.execute(
            "SELECT lineIndex, id FROM line WHERE bookId=?", (book_id,)
        )
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", help="Path to live seforim.db")
    ap.add_argument("--citing", required=True, help="Commentary book title")
    ap.add_argument("--target", required=True, help="Base/tractate book title")
    ap.add_argument("--links", help="Optional path to *_links.json")
    ap.add_argument(
        "--type-id",
        type=int,
        default=COMMENTARY_TYPE_ID,
        help="connectionTypeId (default 1=COMMENTARY)",
    )
    args = ap.parse_args()

    failures: list[str] = []
    notes: list[str] = []

    try:
        db_path = resolve_db(args.db)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as e:
        print(f"ERROR: cannot open DB: {e}", file=sys.stderr)
        return 2

    cur = conn.cursor()
    citing = book_by_title(cur, args.citing)
    target = book_by_title(cur, args.target)

    print("## תוצאת ביקורת הכנסה ל-DB")
    print(f"- DB: {db_path}")

    if not citing:
        failures.append(f'המפרש "{args.citing}" לא נמצא ב-book (כותרת מדויקת)')
        print(f"- מפרש: חסר")
    else:
        c_lines = line_count(cur, citing[0])
        print(
            f"- מפרש: {citing[1]} (id={citing[0]}, totalLines={citing[2]}, "
            f"line_rows={c_lines}, hasCommentaryConnection={citing[4]})"
        )
        if citing[2] <= 0:
            failures.append("למפרש totalLines=0")
        if citing[2] != c_lines:
            failures.append(
                f"אי-התאמה totalLines({citing[2]}) מול COUNT(line)={c_lines}"
            )

    if not target:
        failures.append(f'הבסיס "{args.target}" לא נמצא ב-book (כותרת מדויקת)')
        print(f"- בסיס: חסר")
    else:
        t_lines = line_count(cur, target[0])
        print(
            f"- בסיס: {target[1]} (id={target[0]}, totalLines={target[2]}, "
            f"line_rows={t_lines}, hasCommentaryConnection={target[4]})"
        )
        if target[2] <= 0:
            failures.append("לבסיס totalLines=0")
        if target[2] != t_lines:
            failures.append(
                f"אי-התאמה totalLines({target[2]}) מול COUNT(line)={t_lines} בבסיס"
            )

    base_to_citing = reverse = 0
    if citing and target:
        base_to_citing = cur.execute(
            "SELECT COUNT(*) FROM link WHERE sourceBookId=? AND targetBookId=? "
            "AND connectionTypeId=?",
            (target[0], citing[0], args.type_id),
        ).fetchone()[0]
        reverse = cur.execute(
            "SELECT COUNT(*) FROM link WHERE sourceBookId=? AND targetBookId=? "
            "AND connectionTypeId=?",
            (citing[0], target[0], args.type_id),
        ).fetchone()[0]
        print(f"- קישורים בסיס→מפרש (type={args.type_id}): {base_to_citing}")
        print(f"- קישורים מפרש→בסיס (type={args.type_id}): {reverse}")

        if base_to_citing == 0:
            failures.append(
                "אין קישורים בכיוון הקנוני בסיס→מפרש — המפרש לא יופיע כראוי על המסכת"
            )
        if reverse and not base_to_citing:
            failures.append(
                "נמצאו רק קישורים מפרש→בסיס (כיוון JSON) — צריך היפוך ל-DB"
            )
        elif reverse and base_to_citing:
            notes.append(
                f"קיימים גם {reverse} קישורים הפוכים; בדקו כפילויות/רעש"
            )

        bhl_c = cur.execute(
            "SELECT * FROM book_has_links WHERE bookId=?", (citing[0],)
        ).fetchone()
        bhl_t = cur.execute(
            "SELECT * FROM book_has_links WHERE bookId=?", (target[0],)
        ).fetchone()
        print(f"- book_has_links מפרש: {bhl_c}")
        print(f"- book_has_links בסיס: {bhl_t}")

        if base_to_citing > 0:
            if not bhl_c or (bhl_c[1] == 0 and bhl_c[2] == 0):
                failures.append("book_has_links של המפרש לא מסמן קישורים")
            if target[4] != 1:
                failures.append(
                    "לספר הבסיס hasCommentaryConnection!=1 למרות שיש קישורים"
                )

    # JSON coverage
    if args.links and citing and target:
        links_path = Path(args.links)
        if not links_path.exists():
            failures.append(f"קובץ קישורים לא נמצא: {links_path}")
        else:
            data = json.loads(links_path.read_text(encoding="utf-8"))
            cmap = line_map(cur, citing[0])
            tmap = line_map(cur, target[0])
            missing_lines = 0
            missing_db = 0
            ok = 0
            for item in data:
                c_idx = int(item["line_index_1"]) - 1
                t_idx = int(item["line_index_2"]) - 1
                if c_idx not in cmap or t_idx not in tmap:
                    missing_lines += 1
                    continue
                src_line = tmap[t_idx]
                tgt_line = cmap[c_idx]
                n = cur.execute(
                    "SELECT COUNT(*) FROM link WHERE sourceBookId=? AND "
                    "targetBookId=? AND sourceLineId=? AND targetLineId=? "
                    "AND connectionTypeId=?",
                    (target[0], citing[0], src_line, tgt_line, args.type_id),
                ).fetchone()[0]
                if n:
                    ok += 1
                else:
                    missing_db += 1
            print(
                f"- כיסוי מול JSON ({links_path.name}): "
                f"{ok}/{len(data)} (חסרי-שורה={missing_lines}, חסרי-DB={missing_db})"
            )
            if missing_lines:
                failures.append(f"{missing_lines} רשומות JSON עם אינדקס שורה חסר ב-DB")
            if missing_db:
                failures.append(
                    f"{missing_db}/{len(data)} רשומות JSON חסרות כקישור בסיס→מפרש ב-DB"
                )
            if base_to_citing and abs(base_to_citing - ok) > 0 and missing_db == 0:
                notes.append(
                    f"מספר קישורים ב-DB ({base_to_citing}) שונה מכיסוי JSON המאומת ({ok})"
                )

    conn.close()

    if notes:
        print("- הערות:")
        for n in notes:
            print(f"  - {n}")

    if failures:
        print("- סטטוס: FAIL")
        print("- כשלים:")
        for i, f in enumerate(failures, 1):
            print(f"  {i}. {f}")
        print(
            "- המלצה: אם המשתמש מבקש תיקון — גיבוי DB, סגירת אוצריא, "
            "הכנסת קישורים בכיוון בסיס→מפרש, עדכון דגלים, ואז ביקורת חוזרת."
        )
        return 1

    print("- סטטוס: PASS")
    print("- הכנסת הספר/הקישורים ל-DB נראית תקינה לתצוגת מפרש על הבסיס.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
