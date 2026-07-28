# -*- coding: utf-8 -*-
"""
Generic engine for writing a project `_links.json` file into the live Otzaria
`seforim.db`, so a commentary/citing book shows up next to its base text in
the app's side-by-side reading view.

This is the write-to-the-real-database half of the workflow. The other half
(producing/updating the `_links.json` file itself) is a separate skill
(otzaria-commentary-linker) and is not this script's job.

Usage (always via Windows-MCP PowerShell, never bash -- see SKILL.md for why):

    chcp 65001; python -X utf8 "<this file>" "<path to a job config JSON>"

The job config JSON carries all the per-run, book-specific detail (titles,
paths, Hebrew strings). Passing it as a file -- instead of passing titles as
command-line arguments -- sidesteps PowerShell's well-documented mangling of
Hebrew text and embedded quotes. See references/db_write_notes.md for the full
schema this script relies on and the reasoning behind each design choice below
(direction, flag mapping, backup policy, etc.) -- this file intentionally
keeps comments short and points there for the "why".

Job config schema (see references/db_write_notes.md for full detail):
{
  "project_root": "C:\\Users\\User\\Downloads\\otzaria-library-main",
  "citing_title": "<commentary/citing book title, exactly as in the book table>",
  "target_title": "<base/target book title, exactly as in the book table -- this is
                    only the file's DEFAULT/primary target; entries whose own path_2
                    names a different book (e.g. a super_commentary entry pointing at
                    Tosafot/Rashi instead of the Gemara) are resolved independently,
                    per entry -- see "Multi-target files" below and db_write_notes.md>",
  "links_json_path": "C:\\...\\links\\<citing_title>_links.json",
  "seforim_db_path": null,          # optional override; auto-discovered if omitted
  "keep_backups": 3,                 # how many _db_backups/seforim.db.bak_* to retain
  "replace_existing": false,         # true = wipe EVERY existing link row for this citing
                                      # book (targetBookId = citing_id, any source book, any
                                      # type) and re-insert fresh from the current file, after
                                      # the user has confirmed this is an intentional update.
                                      # Deliberately a full wipe, not per-(type, real target)
                                      # deletion -- see module docstring and db_write_notes.md,
                                      # "Re-running / updating", for the orphan-row bug this
                                      # replaced.
  "dry_run": true                    # true = do everything except commit; always run this
                                      # first and read the report before setting it to false
}

Multi-target files -- read this before assuming target_title covers everything:
A single `_links.json` file can contain entries that target DIFFERENT books, not
one fixed base text. The most common real case: a `commentary` entry pointing at
the Gemara alongside a `super_commentary` entry pointing at a different book
entirely (Tosafot, Rashi, ...) -- the sibling otzaria-commentary-linker skill's
"ד"ה" special case, where a citing-book line comments on a commentary rather than
on the base text. This script NEVER resolves an entry's target line using a single
target_title-derived line map; it groups entries by (Conection Type, real target
title derived from that entry's own path_2), and resolves each group's book id and
line map independently. Confirmed bug this fixes: an earlier version used one line
map for every entry regardless of type, which silently wrote every super_commentary
row with sourceBookId set to the Gemara instead of the real target (some numbers
happened to fall in-range by coincidence), with no error -- see db_write_notes.md,
"A _links.json file can target MULTIPLE different books", for the full story.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path(r"C:\ProgramData\otzaria\books\seforim.db")

# Heading lines are skipped when expanding a range into link_coverage, matching
# the official otzariasqlite generator's own behavior.
HEADING_RE = re.compile(r"^\s*<h[1-6]\b", re.I)

# Only these three map onto a book flag column with real confidence -- confirmed
# against live data in this project (see references/db_write_notes.md, "Flag mapping").
# Everything else falls back to hasOtherConnection with a printed warning; verify
# those in the running app rather than trusting the fallback blindly.
FLAG_MAP = {
    "COMMENTARY": "hasCommentaryConnection",
    "TARGUM": "hasTargumConnection",
    "REFERENCE": "hasReferenceConnection",
}
FALLBACK_FLAG = "hasOtherConnection"


def resolve_db_path(cfg: dict) -> Path:
    if cfg.get("seforim_db_path"):
        p = Path(cfg["seforim_db_path"])
        if not p.exists():
            raise FileNotFoundError(f"seforim_db_path given but not found: {p}")
        return p

    import os

    prefs_path = Path(os.environ.get("APPDATA", "")) / "otzaria" / "shared_preferences.json"
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
            lib_path = prefs.get("flutter.key-library-path")
            if lib_path:
                candidate = Path(lib_path) / "seforim.db"
                if candidate.exists():
                    return candidate
        except Exception as e:  # noqa: BLE001
            print(f"WARNING: could not parse {prefs_path}: {e}")

    if DEFAULT_DB_PATH.exists():
        return DEFAULT_DB_PATH

    raise FileNotFoundError(
        "Could not locate seforim.db automatically. Set seforim_db_path explicitly "
        "in the job config, or check %APPDATA%\\otzaria\\shared_preferences.json "
        "for 'flutter.key-library-path'."
    )


def probe_lock(db_path: Path) -> None:
    """Fail fast and clearly if Otzaria (or anything else) has the DB open."""
    probe = sqlite3.connect(str(db_path), timeout=1)
    try:
        probe.execute("BEGIN IMMEDIATE")
        probe.rollback()
    except sqlite3.OperationalError as e:
        raise RuntimeError(
            "Cannot get a write lock on seforim.db -- close the Otzaria app "
            f"completely (not just the window) and retry. Detail: {e}"
        )
    finally:
        probe.close()


def backup_db(db_path: Path, project_root: Path, keep: int) -> Path:
    backup_dir = project_root / "_db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"seforim.db.bak_{stamp}"
    print(f"Backing up {db_path} -> {backup_path} ...")
    shutil.copy2(db_path, backup_path)
    print(f"Backup done ({backup_path.stat().st_size:,} bytes).")

    existing = sorted(
        backup_dir.glob("seforim.db.bak_*"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for stale in existing[keep:]:
        print(f"Pruning old backup: {stale.name}")
        stale.unlink()

    return backup_path


def load_links(links_path: Path) -> list[dict]:
    data = json.loads(links_path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{links_path} did not contain a non-empty JSON array")
    required = {"line_index_1", "line_index_2", "heRef_2", "path_2", "Conection Type"}
    for i, entry in enumerate(data):
        missing = required - entry.keys()
        if missing:
            raise ValueError(f"entry {i} in {links_path} is missing fields: {missing}")
    return data


def target_title_from_path(path2: str) -> str:
    """Resolves the REAL target-book title from a link entry's own path_2 --
    strips any directory prefix (path_2 is sometimes a bare filename, sometimes
    a backslash path) and the .txt extension. Never assume this equals the
    job's nominal target_title; a file can mix targets -- see module docstring
    and db_write_notes.md, "A _links.json file can target MULTIPLE different
    books"."""
    name = path2.replace("\\", "/").split("/")[-1]
    return name[:-4] if name.lower().endswith(".txt") else name


def get_book(cur: sqlite3.Cursor, title: str) -> tuple[int, int]:
    """Returns (id, orderIndex). Raises if not found or ambiguous."""
    rows = cur.execute(
        "SELECT id, orderIndex FROM book WHERE title = ?", (title,)
    ).fetchall()
    if not rows:
        raise ValueError(f'No book titled "{title}" found in seforim.db.')
    if len(rows) > 1:
        raise ValueError(f'Multiple books titled "{title}" found: {rows}. Disambiguate by id.')
    return rows[0]


def line_map(cur: sqlite3.Cursor, book_id: int) -> dict[int, int]:
    return dict(cur.execute("SELECT lineIndex, id FROM line WHERE bookId = ?", (book_id,)))


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    return (
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        is not None
    )


def write_satellites(
    cur: sqlite3.Cursor,
    pending: list[dict],
    *,
    citing_id: int,
    real_target_id: int,
    has_anchor: bool,
    has_range: bool,
    has_coverage: bool,
) -> tuple[int, int]:
    """Writes optional link_anchor / link_range / link_coverage rows for a just-
    inserted group of links, if the entry's JSON carried the extra fields and the
    tables exist in this seforim.db. Convention (matches the JSON-producing
    otzaria-commentary-linker skill and the schema): side=1 is the citing book
    (line_index_1 space, i.e. `start`/`end`/`line_index_1_end`), side=0 is the
    real target/base book (line_index_2 space, i.e. `line_index_2_end`). Returns
    (anchors_written, ranges_written)."""
    anchors = 0
    ranges = 0
    for p in pending:
        entry = p["entry"]
        link_id = p["link_id"]

        if has_anchor and entry.get("start") is not None:
            try:
                char_start = int(entry["start"])
                char_end = int(entry["end"]) if entry.get("end") is not None else None
            except (TypeError, ValueError):
                pass
            else:
                cur.execute(
                    """
                    INSERT OR IGNORE INTO link_anchor (linkId, side, charStart, charEnd, label)
                    VALUES (?, 1, ?, ?, NULL)
                    """,
                    (link_id, char_start, char_end),
                )
                anchors += 1

        if not has_range:
            continue

        for side, end_1based, book_id, start_0based in (
            (1, entry.get("line_index_1_end"), citing_id, p["c_idx"]),
            (0, entry.get("line_index_2_end"), real_target_id, p["t_idx"]),
        ):
            if end_1based is None:
                continue
            try:
                end_0 = int(end_1based) - 1
            except (TypeError, ValueError):
                continue
            if end_0 <= start_0based:
                continue
            end_line = cur.execute(
                "SELECT id FROM line WHERE bookId=? AND lineIndex=?", (book_id, end_0)
            ).fetchone()
            if not end_line:
                continue
            cur.execute(
                """
                INSERT OR REPLACE INTO link_range (linkId, side, endLineId, endLineIndex)
                VALUES (?, ?, ?, ?)
                """,
                (link_id, side, end_line[0], end_0),
            )
            ranges += 1
            if has_coverage:
                for mid in range(start_0based + 1, end_0 + 1):
                    mid_row = cur.execute(
                        "SELECT id, content FROM line WHERE bookId=? AND lineIndex=?",
                        (book_id, mid),
                    ).fetchone()
                    if not mid_row:
                        continue
                    mid_id, content = mid_row
                    if isinstance(content, str) and HEADING_RE.match(content):
                        continue
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO link_coverage (lineId, linkId, side)
                        VALUES (?, ?, ?)
                        """,
                        (mid_id, link_id, side),
                    )
    return anchors, ranges


def resolve_connection_type_id(cur: sqlite3.Cursor, name: str) -> int:
    row = cur.execute(
        "SELECT id FROM connection_type WHERE upper(name) = upper(?)", (name,)
    ).fetchone()
    if not row:
        valid = [r[0] for r in cur.execute("SELECT name FROM connection_type").fetchall()]
        raise ValueError(f'Unrecognized "Conection Type" value {name!r}. Valid: {valid}')
    return row[0]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: insert_commentary_link.py <path to job config JSON>")
        return 1

    try:
        return run(Path(sys.argv[1]))
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        # These are the anticipated, "explain and stop" failure modes (bad path, book not
        # found, DB locked, unrecognized type, ...) -- print cleanly instead of a traceback.
        print(f"ERROR: {e}")
        return 1


def run(config_path: Path) -> int:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    project_root = Path(cfg["project_root"])
    citing_title = cfg["citing_title"]
    target_title = cfg["target_title"]
    links_path = Path(cfg["links_json_path"])
    keep_backups = int(cfg.get("keep_backups", 3))
    replace_existing = bool(cfg.get("replace_existing", False))
    dry_run = bool(cfg.get("dry_run", True))

    print(f"{'DRY RUN -- ' if dry_run else ''}citing={citing_title!r} target={target_title!r}")

    db_path = resolve_db_path(cfg)
    print(f"seforim.db: {db_path}")
    if not links_path.exists():
        raise FileNotFoundError(f"links_json_path not found: {links_path}")

    data = load_links(links_path)
    print(f"links file: {links_path.name} ({len(data)} entries)")

    probe_lock(db_path)

    backup_path = None
    if not dry_run:
        backup_path = backup_db(db_path, project_root, keep_backups)
    else:
        print("(dry run: skipping backup -- no write will happen)")

    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.text_factory = str
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    has_anchor = table_exists(cur, "link_anchor")
    has_range = table_exists(cur, "link_range")
    has_coverage = table_exists(cur, "link_coverage")

    try:
        # target_title is only the file's DEFAULT/primary target (see module docstring).
        # It's still resolved eagerly here so the printed summary below matches the old
        # behavior, and so it's pre-seeded into the per-real-target cache -- the common,
        # single-target case then costs no extra query at all.
        target_id, target_order = get_book(cur, target_title)
        citing_id, citing_order = get_book(cur, citing_title)
        target_lines = line_map(cur, target_id)
        citing_lines = line_map(cur, citing_id)
        print(f"target book: {target_title} id={target_id} orderIndex={target_order}")
        print(f"citing book: {citing_title} id={citing_id} orderIndex={citing_order}")
        print(f"target has {len(target_lines)} lines, citing has {len(citing_lines)} lines")

        target_book_cache: dict[str, tuple[int, int, dict[int, int]]] = {
            target_title: (target_id, target_order, target_lines)
        }

        def resolve_target(title: str) -> tuple[int, int, dict[int, int]]:
            if title not in target_book_cache:
                tid, torder = get_book(cur, title)
                target_book_cache[title] = (tid, torder, line_map(cur, tid))
            return target_book_cache[title]

        # Group entries by (Conection Type, REAL target book from each entry's own
        # path_2) -- NOT by type alone, and NOT assumed to be target_title. A links
        # file can mix targets (commentary -> Gemara, super_commentary -> Tosafot/
        # Rashi, ...); resolving every entry against one fixed line map silently
        # corrupts every entry whose real target differs. See module docstring and
        # db_write_notes.md for the full story.
        groups: dict[tuple[str, str], list[dict]] = {}
        for entry in data:
            real_target_title = target_title_from_path(entry["path_2"])
            groups.setdefault((entry["Conection Type"], real_target_title), []).append(entry)

        next_id = (cur.execute("SELECT MAX(id) FROM link").fetchone()[0] or 0) + 1
        report = {"inserted": {}, "deleted_for_replace": {}, "skipped_existing": {},
                  "skipped_missing_line": 0, "skipped_duplicate": 0,
                  "skipped_target_book_not_found": 0, "anchors": 0, "ranges": 0}

        if replace_existing:
            # Wipe EVERY existing outgoing link for this citing book up front, not just
            # the (type, real target) groups that happen to appear in *this* file. A
            # book's classification can legitimately change between runs (e.g. a line
            # reclassified from commentary->Gemara to super_commentary->Rashi) -- if we
            # only deleted per-group-in-current-file, the old group's rows would never
            # be targeted (it's no longer a group in this run) and would survive as
            # orphans alongside the freshly inserted rows, double-counting that line.
            # Confirmed bug: אבן העוזר על מגילה and אבן העוזר על קידושין both accumulated
            # exactly this kind of orphaned stale row across a re-run where a line's type
            # changed. A single citing book has exactly one _links.json driving all of
            # its outgoing links, so a full wipe-and-reinsert for that citing_id is safe.
            cur.execute(
                """
                SELECT b.title, ct.name, COUNT(*)
                FROM link l
                JOIN book b ON b.id = l.sourceBookId
                JOIN connection_type ct ON ct.id = l.connectionTypeId
                WHERE l.targetBookId=?
                GROUP BY b.title, ct.name
                """,
                (citing_id,),
            )
            pre_existing = cur.fetchall()
            if pre_existing:
                cur.execute("DELETE FROM link WHERE targetBookId=?", (citing_id,))
                for src_title, type_name_existing, cnt in pre_existing:
                    label = f"{type_name_existing} -> {src_title}"
                    report["deleted_for_replace"][label] = cnt
                    print(f'Deleted {cnt} stale "{label}" links before re-inserting (full wipe for this citing book).')

        for (type_name, real_target_title), entries in groups.items():
            type_id = resolve_connection_type_id(cur, type_name)
            type_upper = type_name.upper()
            group_label = f"{type_name} -> {real_target_title}"

            try:
                real_target_id, real_target_order, real_target_lines = resolve_target(
                    real_target_title
                )
            except ValueError as e:
                print(f'SKIPPING {len(entries)} entries for "{group_label}": {e}')
                report["skipped_target_book_not_found"] += len(entries)
                continue

            existing_count = cur.execute(
                "SELECT COUNT(*) FROM link WHERE sourceBookId=? AND targetBookId=? AND connectionTypeId=?",
                (real_target_id, citing_id, type_id),
            ).fetchone()[0]

            if existing_count:
                if not replace_existing:
                    print(
                        f'SKIPPING "{group_label}": {existing_count} matching links already '
                        f"exist. Re-run with replace_existing=true (after confirming with the "
                        f"user) to delete and replace them, or leave as-is if this is intentional."
                    )
                    report["skipped_existing"][group_label] = existing_count
                    continue
                cur.execute(
                    "DELETE FROM link WHERE sourceBookId=? AND targetBookId=? AND connectionTypeId=?",
                    (real_target_id, citing_id, type_id),
                )
                print(f'Deleted {existing_count} stale "{group_label}" links before re-inserting.')
                report["deleted_for_replace"][group_label] = existing_count

            pending = []
            seen = set()
            for entry in entries:
                c_idx = int(entry["line_index_1"]) - 1  # citing book, 0-based
                t_idx = int(entry["line_index_2"]) - 1  # real target book, 0-based
                if c_idx not in citing_lines or t_idx not in real_target_lines:
                    report["skipped_missing_line"] += 1
                    continue
                source_line_id = real_target_lines[t_idx]
                target_line_id = citing_lines[c_idx]
                key = (source_line_id, target_line_id, type_id)
                if key in seen:
                    report["skipped_duplicate"] += 1
                    continue
                seen.add(key)
                link_id = next_id
                next_id += 1
                pending.append(
                    {
                        "link_id": link_id,
                        "tuple": (
                            link_id, real_target_id, citing_id, source_line_id, target_line_id,
                            c_idx, citing_order, type_id, 1,  # isDeclaredBase
                        ),
                        "entry": entry,
                        "c_idx": c_idx,
                        "t_idx": t_idx,
                    }
                )

            if pending:
                cur.executemany(
                    """
                    INSERT INTO link (
                        id, sourceBookId, targetBookId, sourceLineId, targetLineId,
                        targetLineIndex, targetBookOrderIndex, connectionTypeId, isDeclaredBase
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    [p["tuple"] for p in pending],
                )
                report["inserted"][group_label] = len(pending)
                print(f'Inserted {len(pending)} "{group_label}" links.')

                # Optional satellite tables (link_anchor / link_range / link_coverage) —
                # only written if the entries carried the extra fields and the tables
                # exist in this seforim.db. See write_satellites() docstring for the
                # side=1(citing)/side=0(real target) convention.
                anchors, ranges = write_satellites(
                    cur,
                    pending,
                    citing_id=citing_id,
                    real_target_id=real_target_id,
                    has_anchor=has_anchor,
                    has_range=has_range,
                    has_coverage=has_coverage,
                )
                report["anchors"] += anchors
                report["ranges"] += ranges
                if anchors or ranges:
                    print(f'  + {anchors} anchor(s), {ranges} range(s) for "{group_label}".')

                # book_has_links: both sides are now truthfully participating in this role.
                cur.execute(
                    "INSERT INTO book_has_links(bookId, hasSourceLinks, hasTargetLinks) "
                    "VALUES (?, 1, 0) ON CONFLICT(bookId) DO UPDATE SET hasSourceLinks=1",
                    (real_target_id,),
                )
                cur.execute(
                    "INSERT INTO book_has_links(bookId, hasSourceLinks, hasTargetLinks) "
                    "VALUES (?, 0, 1) ON CONFLICT(bookId) DO UPDATE SET hasTargetLinks=1",
                    (citing_id,),
                )

                # Flag column: set on the REAL target book (not the job's nominal
                # target_title), which is the one that now has a real panel of this
                # type to show. See references/db_write_notes.md for why only
                # COMMENTARY/TARGUM/REFERENCE are set with confidence.
                flag_col = FLAG_MAP.get(type_upper)
                if flag_col:
                    cur.execute(f"UPDATE book SET {flag_col}=1 WHERE id=?", (real_target_id,))
                else:
                    cur.execute(f"UPDATE book SET {FALLBACK_FLAG}=1 WHERE id=?", (real_target_id,))
                    print(
                        f'WARNING: "{type_name}" has no confirmed flag mapping; set '
                        f'{FALLBACK_FLAG} on "{real_target_title}" as a fallback. Verify in '
                        f"the running app that the commentary actually appears."
                    )

                # For COMMENTARY specifically, the citing book genuinely gains a real
                # "source" (מקור) reverse view now -- confirmed by live precedent.
                if type_upper == "COMMENTARY":
                    cur.execute(
                        "UPDATE book SET hasSourceConnection=1 WHERE id=?", (citing_id,)
                    )
            else:
                print(f'Nothing to insert for "{group_label}" (all entries skipped).')

        if dry_run:
            conn.rollback()
            print("\nDRY RUN complete -- nothing was written. Report:")
        else:
            conn.commit()
            print("\nCommitted. Report:")

        print(json.dumps(report, ensure_ascii=False, indent=2))

        if not dry_run:
            for group_label in report["inserted"]:
                type_name, real_target_title = group_label.split(" -> ", 1)
                type_id = resolve_connection_type_id(cur, type_name)
                real_target_id = target_book_cache[real_target_title][0]
                verify = cur.execute(
                    "SELECT COUNT(*) FROM link WHERE sourceBookId=? AND targetBookId=? AND connectionTypeId=?",
                    (real_target_id, citing_id, type_id),
                ).fetchone()[0]
                print(f'VERIFY "{group_label}"->{citing_title}: {verify} rows in DB')
            print(f"Backup kept at: {backup_path}")
            print("Close and reopen Otzaria, then open the target book to check the commentary panel.")

        return 0

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
