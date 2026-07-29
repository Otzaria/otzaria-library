# Writing directly into seforim.db — schema, direction, and flags

This is condensed, empirically-verified reference material for `scripts/insert_commentary_link.py`.
Everything in this file was confirmed against a real, live `seforim.db` (not inferred from
docs alone) — see "How this was verified" at the bottom if you want to re-check any of it
yourself on a different machine.

## Locating the live DB

The Otzaria desktop app reads its library from whatever path is stored under the
`flutter.key-library-path` key in `%APPDATA%\otzaria\shared_preferences.json`. On the
machine this was built against, that resolved to `C:\ProgramData\otzaria\books\seforim.db`.

Do not hardcode `C:\ProgramData\otzaria\books\seforim.db` as the only possible path — always
read it from `shared_preferences.json` first (the script does this automatically) and only
fall back to the ProgramData default if that file is missing. A different machine, or a user
who moved their library, will have a different path.

Note there can be more than one `seforim.db`-named file on a machine (e.g. a leftover from a
different, unrelated Sefaria-reader app under a `kdroidfilter` folder was found sitting in
`%APPDATA%` during development of this skill). Only the path resolved via
`shared_preferences.json` is the one the actual Otzaria app reads — never guess based on
file size or modification time alone.

## Schema (tables this script touches)

```
book(id, categoryId, sourceId, title, heRef, ..., orderIndex, totalLines, isBaseBook,
     hasTargumConnection, hasReferenceConnection, hasSourceConnection,
     hasCommentaryConnection, hasOtherConnection, hasAltStructures, ...)

line(id, bookId, lineIndex [0-based], content, heRef, tocEntryId, charCount)

link(id, sourceBookId, targetBookId, sourceLineId, targetLineId,
     targetLineIndex [0-based, denormalized copy of the target line's lineIndex],
     targetBookOrderIndex [= the target/citing book's own orderIndex],
     connectionTypeId, isDeclaredBase)

connection_type(id, name)   -- 14 rows, name is UPPER_SNAKE_CASE:
  COMMENTARY, SUPER_COMMENTARY, TARGUM, REFERENCE, SOURCE, MIDRASH, QUOTATION,
  MESORAT_HASHAS, EIN_MISHPAT, DIBUR_HAMATCHIL, PARSHANUT, MISHNAH_IN_TALMUD, RELATED, OTHER

book_has_links(bookId, hasSourceLinks, hasTargetLinks)

link_anchor(linkId, side, charStart, charEnd, label)     -- optional, char-offset anchor
link_range(linkId, side, endLineId, endLineIndex)        -- optional, multi-line range end
link_coverage(lineId, linkId, side)                      -- optional, one row per line in range
```

The JSON's `"Conection Type"` string (misspelling is load-bearing; `"Connection Type"` is
ignored) maps onto `connectionTypeId` as:

| JSON string | id | Notes |
|---|---|---|
| `commentary` | 1 | |
| `super_commentary` | 2 | Intermediate targets (Rashi/Tosafot) via `path_2` |
| `targum` | 3 | |
| `reference` | 4 | |
| `source` | — | **Virtual — never write** |
| `midrash` | 6 | |
| `quotation` | 7 | |
| `mesorat_hashas` | 8 | |
| `ein_mishpat` | 9 | |
| `dibur_hamatchil` | 10 | |
| `parshanut` | 11 | |
| `mishnah_in_talmud` | 12 | also accept typo `mishnah_in_tumud` |
| `related` | 13 | |
| `other` / `linker` / unknown | 14 | `linker` = automated pipeline |

## Optional satellites: anchors, ranges, coverage

Some `_links.json` entries carry extra fields beyond the base `line_index_1`/`line_index_2`
pair, and `insert_commentary_link.py` writes them when present and when the corresponding
table exists in the target `seforim.db` (older/smaller DBs may not have these tables at all
— the script checks with `table_exists()` and simply skips this step if they're absent):

- `start` / `end` (character offsets, citing side) → one `link_anchor` row, `side=1`.
- `line_index_1_end` (citing side) and `line_index_2_end` (real target side) → one
  `link_range` row per side that has an end value (`side=1` citing, `side=0` target), plus
  — if `link_coverage` exists — one row per line strictly between the start and end line on
  that side, skipping lines whose content starts with an `<h1>`-`<h6>` heading tag (matching
  the official `otzariasqlite` generator's own behavior).

These are genuinely optional: an entry with neither field, or a `seforim.db` without these
three tables, still gets its plain `link` row and flags — a מפרש with no anchor/range data
still shows up correctly, just without word/paragraph-level highlighting.

`link.id` has no uniqueness constraint beyond being the primary key — nothing stops you from
inserting a duplicate row by accident. The official DB generator (`otzariasqlite`, in the
sister repo SeforimLibrary) allocates `id` deterministically from `(sourceLineId, targetLineId,
connectionTypeId)` so repeated builds stay stable for delta updates — that only matters for the
generator's own rebuild-from-scratch pipeline. This script is a direct, one-off patch to the
live DB, not a rebuild, so `MAX(id)+1` is fine; the guard against duplicate inserts instead
comes from checking `COUNT(*)` for the same `(sourceBookId, targetBookId, connectionTypeId)`
triple before writing (see "Re-running / updating" below).

## Direction — confirmed against the real Rashi/Shabbat link

The project's own `_links.json` format (produced by the sibling `otzaria-commentary-linker`
skill) is oriented *commentary → base*: `line_index_1`/the file itself is the citing/commentary
book, `line_index_2`/`path_2`/`heRef_2` describe the base/target book.

The live `link` table stores it the other way around: **`sourceBookId` is always the base/target
text, `targetBookId` is always the citing/commentary book.** Confirmed directly: querying
`link WHERE sourceBookId=<שבת's id> AND targetBookId=<רש"י על שבת's id>` returns 8,839 rows (the
real, already-shipped Rashi-on-Shabbat commentary), while the reverse direction returns only 2
(noise). A sample row: `sourceLineId` resolves to a `שבת` line (`"שבת ק., י"`), `targetLineId`
resolves to the matching Rashi line (`"רש"י על שבת ק., י, א"`). So when writing to the DB, flip
what the JSON calls "line_index_1/line_index_2" into "target/source" — this is exactly what
`insert_commentary_link.py` does; **the JSON's own field names never map 1:1 onto the DB's
column names for this reason and that's expected, not a bug.**

This direction is only *directly confirmed* for `COMMENTARY`. It's very likely the same
base→cited-thing pattern holds for `TARGUM`/`REFERENCE`/others (the schema's own `isDeclaredBase`
column comment talks about "base_text_titles" in general, not commentary specifically), but
if you're writing a non-commentary type for the first time, it's worth spot-checking one
existing precedent pair of that type in the DB the same way this was verified here, rather
than assuming.

## A `_links.json` file can target MULTIPLE different books — never assume one `target_title`

**Confirmed bug, found and fixed after a real run silently corrupted data.** The job config
carries a single `target_title`, and it's tempting to treat that as *the* target for every
entry in the file. That's only safe when every entry's `Conection Type` describes a relation
to the same base text. It breaks the moment a file mixes types — the most common real case is
a `commentary` entry pointing at the Gemara alongside a `super_commentary` entry pointing at a
*different* book entirely, such as Tosafot or Rashi. This is exactly the sibling
otzaria-commentary-linker skill's "ד"ה" special case: when a citing-book line opens with a
label naming a commentary (e.g. `<b>רש"י</b> ד"ה ...` or a continuation of one, like "בא"ד"),
the line is commenting on *that commentary*, not on the base text — so its `path_2` names the
commentary's own book (e.g. `תוספות על שבת.txt`), not the Gemara.

**What went wrong when this wasn't handled:** an earlier version of this script resolved
`line_index_2` for *every* entry against a single line-index map built once from
`target_title` (the Gemara, in the real case this was found in). For `super_commentary`
entries — whose `line_index_2` is actually a line number *within Tosafot*, not the Gemara —
this silently produced a valid-looking but wrong `sourceLineId`: some numbers happened to
fall within the Gemara's own (shorter) line range, so those entries were inserted with
`sourceBookId` set to the Gemara instead of Tosafot, with no error at all. Others were dropped
as `skipped_missing_line` purely because Tosafot's line-numbering runs longer than the
Gemara's. The net effect: every `super_commentary` row for that citing book ended up attached
to the wrong book, so the commentary never appeared in the real target book's (Tosafot's) own
commentary panel — while looking, from the run's own report, like a completely successful
insert. Confirmed and fixed by cross-checking a specific line pair: `sourceBookId` for the
inserted `super_commentary` rows was the Gemara's id (`104`), while the empirically-correct
value (matching the entry's own `path_2`, `תוספות על שבת.txt`) is a completely different id
(`1907`).

**The rule, going forward:** never resolve a `line_index_2` against a line-index map chosen
from `target_title` alone. Instead:

1. Group entries by **`(Conection Type, real target title)`**, where the real target title is
   derived from that entry's *own* `path_2` (strip any directory prefix and the `.txt`
   extension) — not assumed to equal `target_title`.
2. For each distinct real target title found, resolve its own `book.id` and build its own
   `lineIndex → line.id` map independently (cache these per title across the file, since many
   entries typically share the same handful of real targets).
3. Insert with `sourceBookId` = that group's real target book id, not the job's nominal
   `target_title`'s id — `target_title` is only guaranteed correct for the file's
   default/primary type (typically `commentary` against the base text); treat it as a
   convenience default for the simple, single-target case, pre-seed the resolution cache with
   it so the common case costs no extra query, but let every entry's own `path_2` be the
   actual source of truth.
4. If an entry's real target title isn't found as a `book.title` in `seforim.db` at all,
   that's a distinct, reportable failure (`skipped_target_book_not_found`) — not the same
   thing as a missing line index, and not something to fold silently into the Gemara's line
   map just because a number happens to be in range.

This matters most for `super_commentary`, since that's the confirmed real case, but the same
reasoning applies to any type whose `path_2` might legitimately differ from the file's nominal
target — don't assume it's safe just because it hasn't been seen yet for a given type.

## Flag mapping — confirmed, and where it's genuinely ambiguous

Setting the right `book.hasXxxConnection` flag is what makes the app actually show the panel;
the `link` rows alone are not enough. Empirically, isolating books whose *only* outgoing
connection type is a single given type and reading their flags gives a clean signal for three
types:

- `COMMENTARY` → `hasCommentaryConnection` (confirmed: a book whose only outgoing links are
  COMMENTARY has `hasCommentaryConnection=1` and nothing else attributable to it)
- `TARGUM` → `hasTargumConnection`
- `REFERENCE` → `hasReferenceConnection` (confirmed the same way)

The other 11 types could not be cleanly isolated this way on the live data — every book emitting
`MIDRASH`, `QUOTATION`, `MESORAT_HASHAS`, etc. also happened to emit some other type, so it's not
possible to say with confidence which flag (if any) governs them from this data alone. The
script falls back to `hasOtherConnection` for anything outside the three confirmed types and
prints a warning — treat that as a reasonable guess, not a verified fact, and check the app
after running. When a file has multiple real target books (see above), this flag is now set on
each real target book independently, not just once on the job's nominal `target_title`.

Separately, `hasSourceConnection` looks like it means "this book itself has a virtual מקור/base
to show" (i.e. it's set on the *citing* side of a commentary link, enabling the reverse
"source" view the app derives automatically). The script sets this on the citing book
specifically for `COMMENTARY` links, since that's the one case confirmed by a real example
(`רש"י על שבת` has `hasSourceConnection=1`). This is *not* the same thing as writing a `SOURCE`
connection-type row yourself — `SOURCE` is virtual-only and never a row you insert (matches what
the sibling `otzaria-commentary-linker` skill already documents about the JSON format).

## Re-running / updating an existing link

There's no DB constraint stopping a second run from inserting duplicate rows for the same
book pair, so the script checks `COUNT(*)` for the `(sourceBookId, targetBookId,
connectionTypeId)` triple before writing anything — now per *real* target book (see above),
not per declared type alone:

- If matching rows already exist and `replace_existing` is false (the default), that group is
  **skipped**, not silently duplicated — the report will show it under `skipped_existing`.
- Only set `replace_existing: true` after telling the user how many existing rows will be
  deleted and getting their go-ahead — mirrors the same "show what's about to be dropped, wait
  for confirmation" rule the JSON-producing sibling skill uses for merging `_links.json` files.
- If a previous run mis-attributed rows to the wrong `sourceBookId` (the bug described above),
  those stale rows will **not** be caught by a `(real target, citing, type)` existing-count
  check, since their `sourceBookId` doesn't match the real target at all. Recovering from that
  specific situation means deleting `WHERE targetBookId=<citing id> AND connectionTypeId=<type
  id>` (i.e. by citing book and type only, regardless of the — wrong — `sourceBookId` it
  currently holds) before re-inserting correctly; treat this as a one-off cleanup for data
  written by the old, buggy behavior, not the normal `replace_existing` path.

**Confirmed second bug, since fixed: `replace_existing` deleting per-group instead of per-citing-book.**
An earlier version of this script's `replace_existing` path deleted only the `(real target,
citing, type)` groups that appear *in the current run's file*, then inserted those same
groups fresh. That silently leaves orphaned rows behind whenever a line's classification
changes between runs — e.g. a line that used to be `commentary`→Gemara and is now correctly
`super_commentary`→Rashi: the new file has no `commentary`→Gemara group at all, so that old
group is never even considered for deletion, and its rows survive alongside the freshly
inserted `super_commentary` rows. The citing book ends up with duplicate/orphaned links and
the app's live count differs from the `_links.json` count with no error printed anywhere.
Confirmed on real data: אבן העוזר על מגילה and אבן העוזר על קידושין both accumulated exactly
this kind of orphan (2 and 1 stale `COMMENTARY` rows respectively) across a re-run whose
super-commentary-detection fix reclassified those lines. Caught by comparing `SELECT
COUNT(*) FROM link WHERE targetBookId=<citing id>` against the `_links.json` entry count for
every citing book — a cheap, worthwhile sanity check after any batch of `replace_existing`
writes, since the per-group `VERIFY` line the script prints only checks the groups *it just
wrote*, not the citing book's total.

**The fix, now in place:** when `replace_existing` is true, the script deletes **every**
existing row where `targetBookId = citing_id` (any source book, any connection type) once,
up front, before the per-group insert loop — not scoped to the groups found in the current
file. A single citing book has exactly one `_links.json` driving all of its outgoing links,
so a full wipe-and-reinsert for that citing_id is safe and is now the only `replace_existing`
behavior; there is no remaining per-group-only deletion path to opt into.

## Safety: locking, backups, dry runs

- **Lock probe.** `seforim.db` is a single file the live Otzaria app may have open. The script
  does a `BEGIN IMMEDIATE`/rollback probe before touching anything; if that fails, the fix is
  closing Otzaria completely (not just its window) — there is no safe way to write around an
  open lock.
- **Backup before every real write.** Copied to `<project_root>/_db_backups/seforim.db.bak_<timestamp>`
  before any commit. The file is large (several GB) — after backing up, the script prunes
  `_db_backups/` down to the most recent `keep_backups` (default 3), oldest first, so disk usage
  stays bounded instead of growing forever.
- **Always dry-run first.** `dry_run: true` (the default if omitted) runs the entire flow —
  book/line lookups, grouping, dedup, the full report — and then rolls back instead of
  committing, and skips the backup step entirely (nothing is written, so there's nothing to
  protect against yet). Read the printed report before flipping to `dry_run: false`.

## Access route — Windows-MCP PowerShell, not bash

`seforim.db` lives on the real Windows filesystem outside any folder mounted for
bash/Read/Write, so it has to be reached via `mcp__Windows-MCP__PowerShell` (load via
ToolSearch first if deferred). Two encoding gotchas, both required together:

1. Prefix the command with `chcp 65001;` (UTF-8 console codepage) — otherwise Hebrew text in
   the script's own printed output comes back as `????`-style garbage with no error.
2. Run Python with `-X utf8`.

```
chcp 65001; python -X utf8 "<path to insert_commentary_link.py>" "<path to job config json>"
```

Never pass Hebrew titles as command-line arguments through PowerShell — quoting and encoding
both mangle it unpredictably. That's the reason the script takes a **job config JSON file
path** as its only argument instead of `--citing-title`/`--target-title` flags: write the
config with the `Write` file tool (which handles UTF-8 correctly), and the only thing that
ever crosses the PowerShell command line is an ASCII file path.

## Job config example

```json
{
  "project_root": "C:\\Users\\User\\Downloads\\otzaria-library-main",
  "citing_title": "שפת אמת על שבת",
  "target_title": "שבת",
  "links_json_path": "C:\\Users\\User\\Downloads\\otzaria-library-main\\DictaToOtzaria\\ערוך\\links\\שפת אמת על שבת_links.json",
  "keep_backups": 3,
  "replace_existing": false,
  "dry_run": true
}
```

Note `target_title` here (`"שבת"`) is only the file's *default* target — this particular file
also contains `super_commentary` entries whose real target (per their own `path_2`) is
`תוספות על שבת` or `רש"י על שבת`. The script resolves those independently; `target_title` is
still required in the config (used for the printed summary and as a pre-seeded cache entry),
but it no longer needs to be — and normally won't be — every entry's actual target.

Write this to a Windows temp path (e.g. `C:\Users\User\AppData\Local\Temp\_otzaria_link_job.json`)
with the `Write` tool, run the script once with `dry_run: true`, read the report, then write the
same file again with `dry_run: false` (and `replace_existing: true` only if the user confirmed
an intentional re-run) before running for real. Delete the temp config file afterward — it's
scratch, not a deliverable.

## How this was verified

Everything above was checked directly against a live `seforim.db` via `mcp__Windows-MCP__PowerShell`
+ `sqlite3`/Python during development of this skill: table schemas via `PRAGMA table_info`,
the direction via a real Rashi-on-Shabbat pair (`שבת` id vs `רש"י על שבת` id), the flag
mapping via isolating books whose only outgoing connection type was a single given type and
reading their `book` row, and the multi-target bug via a real שפת אמת-על-שבת run: comparing
the `sourceBookId` an inserted `super_commentary` row actually had (`104`, the Gemara) against
the id its own `path_2` (`תוספות על שבת.txt`) should have resolved to (`1907`), then confirming
the corrected grouping-by-`(type, real target)` logic produces rows whose `sourceBookId`
matches `path_2` for every entry, with `skipped_missing_line` dropping from double digits to
zero. If you're running this on a different machine/library and something here doesn't match
(different `orderIndex` behavior, a flag that doesn't seem to do anything), trust a fresh
spot-check over this document — re-run the same kind of query rather than assuming the numbers
transfer exactly.
