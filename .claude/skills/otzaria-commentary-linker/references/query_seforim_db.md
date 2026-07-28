# Querying seforim.db (fallback path only)

Only needed when Step 2 of SKILL.md can't find a physical `.txt` file for the target book in
the repo. `seforim.db` sits on the real Windows filesystem, outside the mounted project folder,
so bash/Read/Write cannot reach it — you must go through the Windows-MCP tools
(`mcp__Windows-MCP__PowerShell` and `mcp__Windows-MCP__FileSystem`), loading them via ToolSearch
first if they're deferred.

## The gotcha: encoding

PowerShell's default console codepage mangles Hebrew text silently (you'll get `????`-style
garbage back with no error). Always do both of these together:

1. Prefix the PowerShell command with `chcp 65001;` (UTF-8 codepage).
2. Run Python with `-X utf8`.

```
chcp 65001; python -X utf8 "<path to script>.py"
```

## The gotcha: quoting

Passing a Python one-liner with `-c "..."` through PowerShell mangles quotes badly (embedded
Hebrew + quote characters make it worse). Don't do that. Instead:

1. Write the query script to a real Windows temp path with `mcp__Windows-MCP__FileSystem`
   (mode `write`), e.g. `C:\Users\User\AppData\Local\Temp\_query_seforim.py` — **not** inside
   the project folder (files written there are treated as permanent deliverables and can't be
   casually deleted).
2. Run it with `mcp__Windows-MCP__PowerShell` as shown above.
3. Delete the temp script afterward with `mcp__Windows-MCP__FileSystem` (mode `delete`) once
   you're done — it's scratch, not a deliverable.

## Ready-made helper

`scripts/dump_book_from_db.py` in this skill does the common lookups (find candidate books by
title substring; dump full line content + heRef for a specific book id). Copy its contents when
writing the temp script rather than rewriting the query from scratch — it already handles the
Hebrew LIKE search and JSON dumping correctly.

The DB path itself, if not otherwise known: `%APPDATA%\io.github.kdroidfilter.seforimapp\databases\seforim.db`
(expand `%APPDATA%` for the actual user, typically
`C:\Users\<user>\AppData\Roaming\io.github.kdroidfilter.seforimapp\databases\seforim.db`).
Check it exists first with `Test-Path` before assuming this fallback path is even available —
not every machine running this skill will have the Otzaria desktop app (and its DB) installed.

## Schema quick-reference (tables relevant to this skill)

- `book(id, categoryId, sourceId, title, heRef, ..., totalLines, isBaseBook, hasCommentaryConnection, ...)`
- `line(id, bookId, lineIndex [0-based], content, heRef, tocEntryId, charCount)`
- `source(id, name)` — e.g. 1=Sefaria, 6=DictaToOtzaria, etc. (varies by build; look it up, don't hardcode)
- `link(id, sourceBookId, targetBookId, sourceLineId, targetLineId, ..., connectionTypeId, ...)`
- `connection_type(id, name)`

Useful sanity checks before you start matching a book:
- `SELECT hasCommentaryConnection FROM book WHERE id=?` — if already 1, this book may already be
  linked in the built DB (though the repo's `_links.json` is the real source of truth for
  what's pending; the DB reflects the last build, which may be stale).
- Check the repo's own `links/<title>_links.json` first (cheap, no DB needed) for any existing
  entries with the `Conection Type` you're about to write — that tells you if this is a fresh
  link job or a re-run/update.
