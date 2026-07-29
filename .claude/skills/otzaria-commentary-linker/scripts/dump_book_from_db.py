"""
Fallback helper for otzaria-commentary-linker: look up a book in seforim.db and dump its
lines. Only needed when no physical .txt file for the target book exists in the repo (see
references/query_seforim_db.md for why and how to run this).

This file is meant to be copied (via mcp__Windows-MCP__FileSystem, mode "write") to a real
Windows temp path such as C:\\Users\\<user>\\AppData\\Local\\Temp\\_query_seforim.py, then run
with:

    chcp 65001; python -X utf8 "C:\\Users\\<user>\\AppData\\Local\\Temp\\_query_seforim.py" <mode> <arg>

Modes:
    find <title-substring>   -- list candidate books (id, title, sourceId) matching a LIKE search
    dump <book-id>           -- print full book info + all lines as JSON (lineIndex, heRef, content)

Delete the temp copy with mcp__Windows-MCP__FileSystem (mode "delete") once you're done --
it's scratch, not a deliverable, and should not be left in the project folder.
"""

import json
import sys
import os
import glob

DEFAULT_DB_GLOB = os.path.expandvars(
    r"%APPDATA%\io.github.kdroidfilter.seforimapp\databases\seforim.db"
)


def find_db_path() -> str:
    if os.path.exists(DEFAULT_DB_GLOB):
        return DEFAULT_DB_GLOB
    matches = glob.glob(
        os.path.expandvars(r"%APPDATA%\**\seforim.db"), recursive=True
    )
    if matches:
        return matches[0]
    raise FileNotFoundError(
        "Could not find seforim.db under %APPDATA%. Ask the user for its location."
    )


def main() -> None:
    import sqlite3

    if len(sys.argv) < 3:
        print("Usage: dump_book_from_db.py <find|dump> <title-substring|book-id>")
        sys.exit(1)

    mode, arg = sys.argv[1], sys.argv[2]
    db_path = find_db_path()
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    if mode == "find":
        cur.execute(
            "SELECT id, title, sourceId, totalLines, hasCommentaryConnection "
            "FROM book WHERE title LIKE ? ORDER BY title",
            (f"%{arg}%",),
        )
        rows = [
            {
                "id": r[0],
                "title": r[1],
                "sourceId": r[2],
                "totalLines": r[3],
                "hasCommentaryConnection": r[4],
            }
            for r in cur.fetchall()
        ]
        print(json.dumps(rows, ensure_ascii=False, indent=2))

    elif mode == "dump":
        book_id = int(arg)
        cur.execute(
            "SELECT id, title, heRef, totalLines FROM book WHERE id = ?", (book_id,)
        )
        book_row = cur.fetchone()
        if book_row is None:
            print(json.dumps({"error": f"no book with id {book_id}"}, ensure_ascii=False))
            sys.exit(1)
        cur.execute(
            "SELECT lineIndex, heRef, content FROM line WHERE bookId = ? ORDER BY lineIndex",
            (book_id,),
        )
        lines = [
            {"lineIndex": r[0], "heRef": r[1], "content": r[2]} for r in cur.fetchall()
        ]
        out = {
            "id": book_row[0],
            "title": book_row[1],
            "heRef": book_row[2],
            "totalLines": book_row[3],
            "lines": lines,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))

    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
