---
name: otzaria-db-ingestion-audit
description: >
  Audits whether a book (and its commentary links) were correctly ingested into Otzaria's
  live seforim.db. Use when the user asks to verify DB insertion, check if a מפרש shows up
  on a מסכת, audit "האם הכניסו את הספר כמו שצריך", compare _links.json against seforim.db,
  or diagnose missing commentators after library build / manual DB write. Triggers:
  "תבדוק אם הכניסו ל-DB", "האם הספר ב-DB", "למה המפרש לא מופיע על המסכת", "audit ingestion".
---

# Otzaria DB ingestion audit

## Goal

Verify that whoever ingested a book into the **live** Otzaria library DB did it correctly —
not only that files exist in this repo.

This repo (`otzaria-library`) holds **inputs** (`.txt`, `*_links.json`). The app reads
`seforim.db` (usually `C:\ProgramData\otzaria\books\seforim.db`). Passing file checks here
does **not** prove the app will show the book/links.

## Inputs (ask once if missing)

| Input | Default / how to find |
|---|---|
| Citing book title (מפרש) | e.g. `שפת אמת על שבת` |
| Target book title (מסכת/בסיס) | e.g. `שבת` |
| Optional: path to `*_links.json` | `DictaToOtzaria/ערוך/links/<title>_links.json` |
| Path to live `seforim.db` | `%APPDATA%\otzaria\shared_preferences.json` → `flutter.key-library-path` + `\seforim.db`. Fallback: `C:\ProgramData\otzaria\books\seforim.db` |

**Do not** confuse with Zayit DB:
`%APPDATA%\io.github.kdroidfilter.seforimapp\databases\seforim.db`.

## Run the checker

```bash
python .claude/skills/otzaria-db-ingestion-audit/scripts/audit_ingestion.py \
  --db "C:/ProgramData/otzaria/books/seforim.db" \
  --citing "שפת אמת על שבת" \
  --target "שבת" \
  --links "DictaToOtzaria/ערוך/links/שפת אמת על שבת_links.json"
```

If `--links` is omitted, skip JSON↔DB coverage and only audit DB presence/flags/direction.

Interpret exit codes: `0` = PASS, `1` = FAIL (report lists reasons), `2` = could not open DB.

## What “done correctly” means

Treat these as hard requirements for a commentary that should appear on a base text:

### A. Book row
1. Exact `book.title` match for citing and target (no fuzzy pass).
2. `totalLines > 0` and equals `COUNT(*)` from `line` for that `bookId`.
3. Line indices are contiguous `0 .. totalLines-1`.

### B. Links in `link` (COMMENTARY / dependent text)
Canonical **stored** direction for commentary (like Rashi):

- `sourceBookId` = **target/base** (מסכת)
- `targetBookId` = **citing** (מפרש)
- `connectionTypeId` = `1` (`COMMENTARY`) unless another type was intended
- `targetLineIndex` = 0-based line index **in the citing book**
- `isDeclaredBase` = `1` for normal commentary-on-base

Repo `_links.json` is the **opposite** narrative (citing→base via `line_index_1`/`line_index_2`).
Ingestion must **flip** when writing `link` rows. Finding only citing→base rows (or zero rows)
is a FAIL for “appears as מפרש on the מסכת”.

### C. Coverage vs `_links.json` (when provided)
1. Every JSON entry’s indices exist as lines in both books (`line_index_* - 1`).
2. For each JSON entry, a DB row exists:
   - source line = target book line (`line_index_2 - 1`)
   - target line = citing book line (`line_index_1 - 1`)
   - type COMMENTARY (or the mapped type)
3. Report counts: JSON total, DB base→citing COMMENTARY count, missing, extras.

### D. UI flags
1. `book_has_links` for citing: `hasSourceLinks`/`hasTargetLinks` consistent with reality
   (at least one side set when links exist).
2. `book.hasCommentaryConnection = 1` on the **base** book when COMMENTARY links exist.
3. Prefer also setting it on the citing book if other official commentaries do.

### E. Common false passes (call out explicitly)
- Book exists in repo / as personal book, but not in live `seforim.db`.
- Links only in `user_books.db` / `user_link` — may not show as official מפרש.
- CSV import succeeded but app version only supports personal sources.
- `_links.json` present in repo while `COUNT(link)` for the pair is 0.

## Manual SQL spot-checks (if script unavailable)

```sql
SELECT id, title, totalLines FROM book WHERE title IN (?, ?);
SELECT COUNT(*) FROM line WHERE bookId = ?;
SELECT COUNT(*) FROM link
 WHERE sourceBookId = ? AND targetBookId = ? AND connectionTypeId = 1;
SELECT * FROM book_has_links WHERE bookId IN (?, ?);
SELECT hasCommentaryConnection FROM book WHERE id IN (?, ?);
```

Compare a known-good pair (e.g. `שבת` → `רש"י על שבת`) for direction/flags.

## Report format (Hebrew to user)

```markdown
## תוצאת ביקורת הכנסה ל-DB
- סטטוס: PASS / FAIL
- DB: <path>
- מפרש: <title> (id=…, lines=…)
- בסיס: <title> (id=…, lines=…)
- קישורים בסיס→מפרש (COMMENTARY): N
- כיסוי מול JSON: N/M (חסרים: …)
- דגלים: …
- כשלים:
  1. …
- המלצה: …
```

## Fix guidance (audit only — ask before writing DB)

If FAIL because links missing/wrong direction in live DB:
1. Ask the user before writing.
2. Use `otzaria-db-linker` with the specific `*_links.json` path(s) — it backs up,
   flips direction, maps connection types, and updates flags.
3. Re-run this audit to PASS.

Do **not** write to DB unless the user explicitly asks to fix.

## Related skills
- Creating/updating `_links.json`: `otzaria-commentary-linker`
- Writing named `_links.json` into live DB: `otzaria-db-linker`
- Dicta text QA before ingest: `dicta-book-pipeline`
