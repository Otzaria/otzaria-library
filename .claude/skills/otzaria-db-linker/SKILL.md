---
name: otzaria-db-linker
description: >
  Use whenever the user wants a commentary/מפרש that already has a finished
  "title_links.json" file (from the sibling otzaria-commentary-linker skill) to actually
  show up in the Otzaria app — i.e. write those links into the live seforim.db so the מפרש
  appears in the base text's commentary panel, not just sit as a standalone book. Trigger
  for phrases like "תשים את הקישורים בתוכנה", "תעדכן את seforim.db", "תגרום ל-X להופיע
  כמפרש על Y באפליקציה", "עשה import של הקישורים", "למה המפרש לא מופיע ליד המסכת",
  "תכניס ל-DB", "הכנס קישורים", "ingest links", or to patch live library links after
  linker/QA work — or any request to make an already-produced _links.json take effect in
  the running app, even without naming seforim.db or this skill. Also use if "ייבוא דורות
  וקישורים" failed for an official library book (that button targets personal books, not
  this case). This is the single, canonical skill for writing links into the live DB —
  do not create a second one for the same job. Do NOT use for producing/editing the
  _links.json itself — that's otzaria-commentary-linker's job; this skill only consumes
  an already-finished one.
---

# Otzaria DB linker — making a finished `_links.json` take effect

## What this does, and what it doesn't

This is the second half of a two-step workflow. The first half — matching a commentary's
lines to a base text and producing `links/<citing title>_links.json` — is the
**otzaria-commentary-linker** skill. If that file doesn't exist yet, or needs matching work
done on it, that's the skill to reach for, not this one.

This skill takes an already-finished `_links.json` and writes it into the live
`seforim.db` that the Otzaria desktop app actually reads — because for an **official** book
already shipped in the library (as opposed to a personal book the user is importing), the
app's own "ייבוא דורות וקישורים" button writes to a separate `user_books.db` and typically
will not make the commentary show up next to the base text. The only reliable path for an
official book is patching `seforim.db` directly.

## Why this is different from every other file task in this project

Every other skill in this project writes to files inside the mounted project folder — cheap
to redo, cheap to inspect, nothing breaks if a run goes wrong. This skill writes to the
user's real, live, several-gigabyte `seforim.db` — the actual file the desktop app reads on
every launch. There is no "it's just a file, worst case I rewrite it" safety net here: a bad
write is a corrupted library until the user restores a backup. Treat every run accordingly —
slower and more deliberate than the JSON-producing sibling skill, not less.

## Success criteria

1. **The live DB, not the project folder, got updated.** The deliverable of this skill is
   rows in `seforim.db`'s `link` table plus the right `book`/`book_has_links` flags — not a
   file sitting in the repo. If you only edited something under the project folder and
   stopped there, the task isn't done.

2. **A dry run happened before the real write, and you actually read its report.**
   `scripts/insert_commentary_link.py` supports `dry_run: true`, which runs the entire flow
   (book lookup, line-index mapping, grouping by connection type *and* real target book,
   dedup) and rolls back instead of committing. Run it this way first every time, read the
   printed report — book IDs found, how many entries would be inserted vs. skipped and why —
   and only proceed to a real write once that report looks right. This isn't a formality to
   skip when the input looks obviously fine; the dry run is what catches a title typo, a
   stale line count, or a mixed-target file (see criterion 8) before it becomes a real DB
   write.

3. **A fresh backup exists before any real write, and old ones don't pile up forever.** The
   script backs up `seforim.db` to `<project_root>/_db_backups/seforim.db.bak_<timestamp>`
   automatically before committing anything, then prunes that folder down to the 3 most
   recent backups (the file is multiple GB, so keeping every backup from every run
   indefinitely isn't sustainable). Never bypass or hand-roll this step.

4. **Otzaria was confirmed closed before writing, not assumed closed.** The script probes for
   a write lock before backing up or writing anything. If the probe fails, the fix is telling
   the user to close the app completely (not just its window) and retry — there's no safe way
   to force a write through an open lock.

5. **Re-runs and updates don't silently duplicate or silently clobber.** `link.id` has no
   uniqueness constraint, so nothing stops a second run from inserting the same links twice.
   The script checks for existing rows on the same base/commentary/type triple first (per
   *real* target book — see criterion 8, not just per declared type); if any exist, it skips
   that group rather than duplicating, and reports the count. Only pass
   `replace_existing: true` after telling the user how many existing rows would be deleted
   and getting their explicit go-ahead — treat this exactly like the sibling skill's rule for
   overwriting an existing `_links.json`: show what's about to be dropped, wait for
   confirmation, don't drop-and-replace silently.

6. **Verified after writing, not assumed.** After a real (non-dry-run) commit, the script
   re-queries the actual row count for what it just inserted and prints it — that's the
   deliverable's proof, not a log message you take on faith. Report this count, the backup
   path, and remind the user to close/reopen Otzaria and check the commentary panel on the
   target book before considering the task fully done.

7. **A report the user can act on.** Say plainly: how many links were inserted (and for which
   connection type and real target book, if more than one — see criterion 8), how many were
   skipped and why (missing line, already existed, duplicate within the file, target book not
   found), where the backup landed, and — if anything about the flag-mapping fallback fired —
   that it's worth a visual double-check in the running app.

8. **Verified per real target book, not just per declared type.** A single `_links.json`
   file can contain entries that target *different* books, not one fixed base text — most
   commonly a `commentary` entry pointing at the Gemara alongside a `super_commentary` entry
   pointing at a *different* book entirely, like Tosafot or Rashi (the sibling
   otzaria-commentary-linker skill's "ד"ה" special case: a citing-book line that comments on
   a commentary rather than on the base text itself). The job config's `target_title` is only
   guaranteed correct for the file's default/primary type — never assume it covers every
   entry. Confirmed failure mode from a real run: resolving every entry's target line against
   a single `target_title` silently wrote every `super_commentary` row with the *wrong*
   `sourceBookId` (the Gemara instead of the real target from that entry's own `path_2`), with
   no error — some entries were even dropped as "missing line" purely because the true
   target's line-numbering is longer than the Gemara's. The script now groups entries by
   (`Conection Type`, real target book resolved from `path_2`) and resolves each group's own
   book id and line map independently — see `references/db_write_notes.md` for the full story
   and the resolution rule. Before considering a run done, spot-check that a sample of any
   non-default-type entries (e.g. `super_commentary`) landed with `sourceBookId` matching the
   book their own `path_2` actually names.

## How to actually run it

1. **Find the exact book titles.** `citing_title` (the commentary) and `target_title` (the
   file's default/primary base text — see criterion 8 for why this isn't necessarily *every*
   entry's target) both need to match `book.title` in `seforim.db` **exactly** — not the
   `.txt` filename, not a partial name. If unsure, a quick `SELECT title FROM book WHERE title
   LIKE '%...%'` via the same Windows-MCP PowerShell route (see step 3) will confirm it;
   don't guess from the links file's `path_2` field alone, since that's a filename, not
   necessarily an exact title match. Before assuming the whole file targets one book, skim
   the file's distinct `Conection Type` values and their `path_2`s — if `super_commentary` (or
   any other non-default type) appears, expect a mixed-target file and read criterion 8.

2. **Write a job config JSON** (via the `Write` tool, not by typing it into a shell command —
   see "why job config, not CLI args" in `references/db_write_notes.md`) to a Windows temp
   path such as `C:\Users\User\AppData\Local\Temp\_otzaria_link_job.json`:

   ```json
   {
     "project_root": "<repo root, e.g. C:\\Users\\User\\Downloads\\otzaria-library-main>",
     "citing_title": "<commentary title, exact>",
     "target_title": "<base/target title, exact>",
     "links_json_path": "<absolute path to the ...\\links\\<citing_title>_links.json>",
     "keep_backups": 3,
     "replace_existing": false,
     "dry_run": true
   }
   ```

3. **Run the dry run.** Load `mcp__Windows-MCP__PowerShell` (via ToolSearch if deferred) and run:

   ```
   chcp 65001; python -X utf8 "<this skill's scripts/insert_commentary_link.py>" "<job config path>"
   ```

   Read the printed report. It tells you the resolved `seforim.db` path, the citing book's id
   and line count, and — per (connection type, real target book) group found in the file —
   which target book was resolved, how many rows would be inserted, skipped for a missing
   line match, skipped as an in-file duplicate, skipped because matching rows already exist,
   or skipped because the real target book from `path_2` couldn't be found in `seforim.db`.

4. **Resolve anything the dry run flags before going further.** A large "skipped_missing_line"
   count usually means the `_links.json` was built against a different edition/line-count of
   the book than what's actually in `seforim.db` — that's a data problem to take back to
   the otzaria-commentary-linker skill, not something to push through. A nonzero
   "skipped_existing" means this exact base/commentary/type combination is already linked;
   tell the user and ask whether they want a `replace_existing: true` re-run (see criterion 5)
   or to leave it alone. A nonzero "skipped_target_book_not_found" means some entries' `path_2`
   names a book that isn't in `seforim.db` at all — confirm with the user whether that book
   needs to be added first, rather than silently dropping those entries.

5. **Rewrite the job config with `dry_run: false`** (and `replace_existing: true` only if the
   user just confirmed it) and run the exact same command again.

6. **Report the result** per criterion 7, then delete the temp job config file — it's scratch.

7. **Audit the write.** For each (real target book, citing book) pair the run actually
   inserted rows for, run the **otzaria-db-ingestion-audit** skill's script against the
   same `seforim.db` and the same `_links.json`, e.g.:

   ```
   python .claude/skills/otzaria-db-ingestion-audit/scripts/audit_ingestion.py \
     --db "<same seforim.db path>" \
     --citing "<citing title>" \
     --target "<real target title>" \
     --links "<the _links.json path>" \
     --type-id <1 for commentary, 2 for super_commentary, ...>
   ```

   Report PASS/FAIL per pair in Hebrew to the user, and tell them to **restart Otzaria**
   before checking the commentary panel — this is the same audit step
   otzaria-links-db-ingest used to run manually; it's now part of this skill's own
   workflow rather than a separate skill to remember to invoke.

## Optional satellite data (anchors, ranges, coverage)

If a `_links.json` entry carries `start`/`end` (character offsets on the citing side) or
`line_index_1_end`/`line_index_2_end` (a multi-line range on either side), and the live
`seforim.db` has the `link_anchor` / `link_range` / `link_coverage` tables, the script
writes those too — `start`/`end` → `link_anchor` (citing side, `side=1`), the `*_end`
fields → `link_range` (+ `link_coverage` for the lines in between, skipping `<h1-6>`
heading lines the same way the official DB generator does). This is optional: entries
without these fields, or a `seforim.db` without these tables, are unaffected — only the
base `link` row and its flags are required for a מפרש to show up at all.

## Where the technical detail lives

`references/db_write_notes.md` has everything this skill relies on that isn't obvious from
the script itself: the confirmed schema, why the JSON's `line_index_1`/`line_index_2` don't
map 1:1 onto the DB's `sourceBookId`/`targetBookId` (the direction flips), why a file's
entries can't all be resolved against one fixed `target_title` (see criterion 8), which
`book.hasXxxConnection` flags are confirmed vs. best-effort, the backup/lock/dry-run
reasoning, and the exact PowerShell invocation with its encoding gotchas. Read it before your
first run in a conversation, and again any time a result looks surprising — this file exists
specifically so you don't have to re-derive any of this from scratch or guess.

`references/db_write_notes.md` also has the full `"Conection Type"` → `connectionTypeId`
table (14 rows — commentary, super_commentary, targum, reference, source [virtual, never
written], midrash, quotation, mesorat_hashas, ein_mishpat, dibur_hamatchil, parshanut,
mishnah_in_talmud, related, other/linker) if you need to confirm a type id directly.

## Related skills

- Create/update `_links.json`: **otzaria-commentary-linker**
- Audit `_links.json` correctness before writing: **otzaria-commentary-linker-qa**
- Audit the live DB after writing (also invoked as step 7 above): **otzaria-db-ingestion-audit**

## History

This skill absorbed **otzaria-links-db-ingest** (2026-07-12), which did the same job — write
a finished `_links.json` into the live `seforim.db` — under a different name and a
CLI-args interface. The two existed side by side and risked being triggered inconsistently
for the same request. This is now the only skill for that job; the retired one's extra
capabilities (the `link_anchor`/`link_range`/`link_coverage` satellite writes, and the
built-in post-write audit call) were folded in above rather than lost.
