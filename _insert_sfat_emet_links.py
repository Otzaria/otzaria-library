# -*- coding: utf-8 -*-
"""
Insert all שפת אמת commentary links into Otzaria seforim.db.

Canonical direction for COMMENTARY (like Rashi):
  source = base masechet, target = שפת אמת על ...

JSON format is the opposite (commentary -> base), so we flip.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SEF_DB = Path(r"C:\ProgramData\otzaria\books\seforim.db")
LINKS_DIR = REPO_ROOT / "DictaToOtzaria" / "ערוך" / "links"
BACKUP_DIR = REPO_ROOT / "_db_backups"

PAIRS = [
    ("שפת אמת על ברכות", "ברכות"),
    ("שפת אמת על שבת", "שבת"),
    ("שפת אמת על עירובין", "עירובין"),
    ("שפת אמת על פסחים", "פסחים"),
    ("שפת אמת על זבחים", "זבחים"),
    ("שפת אמת על מנחות", "מנחות"),
    ("שפת אמת על ערכין", "ערכין"),
    ("שפת אמת על תמורה", "תמורה"),
    ("שפת אמת על כריתות", "כריתות"),
    ("שפת אמת על מעילה", "מעילה"),
    # בכורות: book exists, no links file yet
]

CONNECTION_TYPE_IDS = {
    "commentary": 1,
    "super_commentary": 2,
}


def find_links_file(citing: str) -> Path | None:
    candidates = [
        LINKS_DIR / f"{citing}_links.json",
        LINKS_DIR / f"{citing}.links.json",
        LINKS_DIR / f".{citing}links.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def target_title_from_path(path_2: str) -> str:
    """Return the actual target title named by a link entry."""
    name = path_2.replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".txt") else name


def resolve_book(cur: sqlite3.Cursor, title: str) -> tuple[int, int] | None:
    """Resolve a JSON filename title, including the repo's Rashi spellings."""
    variants = [title]
    if title.startswith("רשי "):
        variants.append('רש"י ' + title[4:])
    if title.startswith("רשבם "):
        variants.append('רשב"ם ' + title[5:])
    for variant in variants:
        row = cur.execute(
            "SELECT id, orderIndex FROM book WHERE title=?", (variant,)
        ).fetchone()
        if row:
            return int(row[0]), int(row[1])
    return None


def insert_pair(cur: sqlite3.Cursor, citing: str, target: str, next_id: int) -> tuple[int, int, int]:
    """Returns (next_id, inserted, skipped)."""
    links_path = find_links_file(citing)
    if not links_path:
        print(f"  SKIP {citing}: no links file")
        return next_id, 0, 0

    data = json.loads(links_path.read_text(encoding="utf-8"))
    sfat = cur.execute(
        "SELECT id, title, totalLines, orderIndex FROM book WHERE title=?",
        (citing,),
    ).fetchone()
    base = cur.execute(
        "SELECT id, title, totalLines, orderIndex FROM book WHERE title=?",
        (target,),
    ).fetchone()
    if not sfat or not base:
        print(f"  ERROR missing books citing={sfat} base={base}")
        return next_id, 0, 0

    sfat_id, _, sfat_lines, sfat_order = sfat
    base_id, _, base_lines, _ = base
    print(
        f"  {target} id={base_id} lines={base_lines} | "
        f"{citing} id={sfat_id} lines={sfat_lines} order={sfat_order} | "
        f"json={len(data)} ({links_path.name})"
    )

    sfat_map = {
        li: lid
        for li, lid in cur.execute(
            "SELECT lineIndex, id FROM line WHERE bookId=?", (sfat_id,)
        )
    }
    base_map = {
        li: lid
        for li, lid in cur.execute(
            "SELECT lineIndex, id FROM line WHERE bookId=?", (base_id,)
        )
    }
    # A file may mix Gemara commentary with super-commentary on Rashi/Tosafot.
    # path_2, rather than the pair's default base title, is the source of truth.
    target_maps: dict[str, tuple[int, dict[int, int]]] = {
        target: (base_id, base_map),
    }
    existing = {
        tuple(row)
        for row in cur.execute(
            "SELECT sourceLineId, targetLineId, connectionTypeId FROM link WHERE targetBookId=?",
            (sfat_id,),
        )
    }

    rows = []
    skipped = []
    seen = set()
    touched_book_ids = {base_id}
    for i, item in enumerate(data, start=1):
        c_idx = int(item["line_index_1"]) - 1
        s_idx = int(item["line_index_2"]) - 1
        connection_type = item.get("Conection Type")
        connection_type_id = CONNECTION_TYPE_IDS.get(connection_type)
        if connection_type_id is None:
            skipped.append((i, c_idx, s_idx, f"unsupported type {connection_type!r}"))
            continue

        real_target = target_title_from_path(str(item["path_2"]))
        if real_target not in target_maps:
            resolved = resolve_book(cur, real_target)
            if not resolved:
                skipped.append((i, c_idx, s_idx, f"target book not found: {real_target}"))
                continue
            target_id, _ = resolved
            target_maps[real_target] = (
                target_id,
                {
                    li: lid
                    for li, lid in cur.execute(
                        "SELECT lineIndex, id FROM line WHERE bookId=?", (target_id,)
                    )
                },
            )
        source_book_id, source_map = target_maps[real_target]
        if c_idx not in sfat_map or s_idx not in source_map:
            skipped.append((i, c_idx, s_idx, "missing line"))
            continue
        source_line_id = source_map[s_idx]
        target_line_id = sfat_map[c_idx]
        key = (source_line_id, target_line_id, connection_type_id)
        if key in seen or key in existing:
            skipped.append((i, c_idx, s_idx, "duplicate"))
            continue
        seen.add(key)
        touched_book_ids.add(source_book_id)
        rows.append(
            (
                next_id,
                source_book_id,
                sfat_id,
                source_line_id,
                target_line_id,
                c_idx,
                int(sfat_order),
                connection_type_id,
                1,
            )
        )
        next_id += 1

    print(f"  to insert={len(rows)} skipped={len(skipped)}")
    if skipped[:3]:
        print(f"  skip sample={skipped[:3]}")

    if rows:
        cur.executemany(
            """
            INSERT INTO link (
                id, sourceBookId, targetBookId, sourceLineId, targetLineId,
                targetLineIndex, targetBookOrderIndex, connectionTypeId, isDeclaredBase
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )

    for book_id in touched_book_ids | {sfat_id}:
        cur.execute(
            """
            INSERT INTO book_has_links(bookId, hasSourceLinks, hasTargetLinks)
            VALUES (?, 1, 1)
            ON CONFLICT(bookId) DO UPDATE SET
              hasSourceLinks=1,
              hasTargetLinks=1
            """,
            (book_id,),
        )
    placeholders = ",".join("?" for _ in touched_book_ids | {sfat_id})
    cur.execute(
        f"UPDATE book SET hasCommentaryConnection=1 WHERE id IN ({placeholders})",
        tuple(touched_book_ids | {sfat_id}),
    )

    verify = cur.execute(
        "SELECT COUNT(*) FROM link WHERE targetBookId=? AND connectionTypeId IN (1, 2)",
        (sfat_id,),
    ).fetchone()[0]
    print(f"  VERIFY all commentary/super links to {citing}: {verify}")
    return next_id, len(rows), len(skipped)


def main() -> int:
    if not SEF_DB.exists():
        print("ERROR: seforim.db not found", SEF_DB)
        return 1

    try:
        probe = sqlite3.connect(str(SEF_DB), timeout=1)
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
        probe.close()
    except sqlite3.OperationalError as e:
        print("ERROR: cannot write to seforim.db — close Otzaria completely and retry.")
        print(" detail:", e)
        return 2

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"seforim.db.bak_{stamp}"
    print(f"backing up to {backup} ...")
    shutil.copy2(SEF_DB, backup)
    print(f"backup size {backup.stat().st_size}")

    conn = sqlite3.connect(str(SEF_DB), timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    next_id = (cur.execute("SELECT MAX(id) FROM link").fetchone()[0] or 0) + 1
    print(f"starting link id={next_id}")

    total_ins = total_skip = 0
    for citing, target in PAIRS:
        print(f"\n=== {citing} ===")
        next_id, ins, skip = insert_pair(cur, citing, target, next_id)
        total_ins += ins
        total_skip += skip

    conn.commit()
    conn.close()
    print(f"\nDONE inserted={total_ins} skipped={total_skip}")
    print(f"backup kept at: {backup}")
    print("Restart Otzaria to see the commentators.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
