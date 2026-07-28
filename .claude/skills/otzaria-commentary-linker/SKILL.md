---
name: otzaria-commentary-linker
description: >
  Use this skill whenever the user wants to link a commentary, parshanut, targum, midrash,
  or reference book to its base/source text inside the "otzaria-library" project — i.e.
  produce or update the links folder's "book title"_links.json file that makes a מפרש (commentary) show up
  correctly next to the base text it comments on (e.g. a Gemara/Mishnah/Tanakh tractate) in
  the Otzaria
  app's side-by-side reading view. Trigger this any time the user says things like "תקשר לי
  את הספר X שיהיה מפרש על Y", "תקשר בין X ל-Y", "תעדכן/תוסיף קישורים לספר X", "תמצא את מסכת Y
  ב-DB ותקשר אליה", or generally describes matching a commentary's paragraphs to the
  corresponding lines of a source text, even if they don't spell out every step or mention
  this skill by name. Also use it if the user references seforim.db, the Otzaria SQLite
  database, or asks how to find a source book's line numbers / heRef for linking purposes.
---

# Otzaria commentary ↔ source linker

## What this produces

A `links/<commentary title>_links.json` file (or an update to an existing one) inside the
otzaria-library project — a set of entries that make each line of a citing book (מפרש/
commentary/תרגום/מדרש) show up next to the correct line of its target book in the Otzaria
app's side-by-side view. This is the exact input format the app's DB generator
(`otzariasqlite`, in the sister repo SeforimLibrary) reads to build the `link` table in
`seforim.db`. One entry looks like this:

```json
{
  "line_index_1": 5,
  "line_index_2": 3,
  "heRef_2": "מועד קטן ב., א",
  "path_2": "מועד קטן.txt",
  "Conection Type": "commentary"
}
```

Note the field name is `"Conection Type"` — missing the second "n". That's not a typo to fix;
it mirrors Sefaria's original CSV column name and is exactly what the app's parser expects.
Writing `"Connection Type"` instead silently fails to register the link.

## Terminology used in this doc

To avoid the project's own confusing usage (its docs call the commentary the "ספר־מקור"),
this skill always uses two fixed terms:

- **citing book** = the מפרש/commentary/תרגום/מדרש being linked. This is `line_index_1`.
- **target book** = the base text being commented on (Gemara/Mishnah/Tanakh/etc.). This is
  `line_index_2` / `heRef_2` / `path_2`.

Whenever a user or a project doc says "מקור", check contextually whether they mean the
citing book or the target book — do not assume "מקור" = target.

## Success criteria — what a finished result looks like

Don't treat this as a checklist to run once at the end — treat it as the target you're
solving for the whole time. A finished `_links.json` update is correct only if all of the
following hold:

1. **Full coverage.** Every non-heading, non-front-matter, non-blank line in the citing book
   has exactly one match to a target line. No line is silently skipped because a match felt
   uncertain — low confidence is something you disclose, not something you avoid by omitting
   the line. Headings, blank lines, and genuine front-matter (like an author byline under the
   `<h1>` title with no relation to any passage) are the legitimate exceptions — they still
   count toward the physical line numbering (see criterion 2), but never receive a link entry
   themselves, and any front-matter you skip still gets named in your report.

2. **Correct, complete entries.** Every entry has exactly these five fields: `line_index_1`,
   `line_index_2`, `heRef_2`, `path_2`, and the literal key `"Conection Type"` — spelled
   exactly that way (missing the second "n"). This mirrors Sefaria's original CSV column name
   and is what the app's parser expects; writing `"Connection Type"` instead silently fails to
   register the link. `line_index_1` and `line_index_2` are 1-based physical file line
   numbers — every line in the file counts toward this number, including `<h1>`/`<h2>`
   headings and blank lines, even though headings themselves never become a `line_index`
   value.
   
   **Critical for multiple links to the same line:** If you have multiple citing-book lines
   pointing at the same target line (e.g., several commentary snippets on one source passage),
   they **must appear consecutively in the JSON file** (one after another with the same
   `line_index_2` and `path_2`). The app's `groupConsecutiveLinks()` function relies on this
   ordering to group related links together. Links scattered across the file with unrelated
   targets in between will be treated as separate link groups and may not display correctly
   in the panel.

3. **heRef that matches the target book's own convention, always verified against real
   precedent — never a pasted `<h2>` string.** The general shape for Talmud-daf-style books is
   `"<book title> <section label>, <hebrew numeral>"`, where the numeral is a 1-based running
   count of content lines since the last `<h2>` (standard gematria: ..., יג, יד, טו, טז, יז,
   יח, יט, כ, ... — note טו/טז, not יה/יו). But the `<section label>` is *not* simply the raw
   `<h2>` text copied verbatim — e.g. for a מסכתא קטנה like מסכת גרים, the real heRef used
   throughout the DB is `"מסכת גרים א, ז"`, not `"מסכת גרים פרק א, ז"`, even though the
   heading literally reads `<h2>פרק א</h2>` — the word "פרק" is dropped and only the letter
   survives. Books with a different structure entirely (Tanakh, halachic codes by סימן/סעיף,
   etc.) may label sections in yet other ways. Because of this, never trust a derived formula
   on its own: before writing any `heRef_2` values, find at least one existing `_links.json`
   file that already targets the same target book (search for `"path_2": "<target title>.txt"`
   across `links/*.json`) and copy its exact labeling convention, or confirm directly against
   `seforim.db` (see the DB access route below). This precedent check is mandatory every time,
   not something you only do when a book looks unusual or the pattern seems off.

4. **The right connection type**, resolved to one of the app's stored values — `commentary`
   (פירוש/מפרש רגיל, the default for generic phrasing like "שיהיה מפרש"), `super_commentary`,
   `targum`, `reference`, `midrash`, `quotation`, `mesorat_hashas`, `ein_mishpat`,
   `dibur_hamatchil`, `parshanut`, `mishnah_in_talmud`, `related`, or `other` as a last resort.
   Use `super_commentary` (not `commentary`) whenever the citing line is commenting on an
   intermediate commentary such as Rashi or Tosafot — especially lines that open
   `רש"י ד"ה …` / `תוס' ד"ה …` (see matching rules below); those must target the Rashi/Tosafot
   book itself, not the Gemara. Don't confuse `reference` with `"Conection Type": "linker"` —
   `linker` is the literal
   string the automated Sefaria-citation pipeline (the `linker/` folder) writes into existing
   files; it is not one of the app's recognized values at all, and gets silently stored as
   `OTHER` internally (its word-anchor still works, since that depends on `start`/`end`, not on
   the type being recognized). You never write `linker` by hand — it isn't a type choice
   available to you, only something you preserve untouched when it's already present (see
   criterion 5). `source` is never a correct value to write either — it's virtual-only,
   derived automatically by the app by inverting a commentary link. If the user's request is
   actually the reverse direction ("מקור" meaning "put X as the base text under Y"), the
   correct result is achieved by swapping which book is the citing book and which is the
   target — not by writing a `source` entry.

5. **A merge the user approved before it happened.** If `links/<commentary title>_links.json`
   already exists, the pre-existing file is left untouched except for the specific stale
   subset that shares both the same `path_2` and the same `Conection Type` you just produced.
   Before writing anything, show the user exactly which existing entries you're about to drop
   (e.g. "these 40 existing `commentary`→`מועד קטן.txt` entries will be replaced by the new
   set; the 5 `targum`→`תרגום ירושלמי.txt` entries and any `"Conection Type": "linker"`
   entries stay untouched") and get their go-ahead before performing the replacement — don't
   drop-and-replace silently even though the matching rule itself is deterministic. Output is
   written with `indent=2, ensure_ascii=False`, matching the existing files' formatting, at
   `<source root>/links/<commentary title>_links.json`.

6. **Verified before delivery.** Before handing over the finished file, you cross-checked it
   against `seforim.db` directly (Windows-MCP PowerShell route, not bash — see below) —
   confirming derived `heRef` values and spot-checking that target lines you matched against
   actually correspond to real rows in the DB. This is a mandatory final gate for every run,
   not a step reserved for when a result looks doubtful. If the DB is genuinely unreachable —
   wrong path, tool unavailable, permission denied — this gate becomes a disclosed limitation
   instead of a blocker: deliver the file-derived result anyway, but say explicitly in your
   report (criterion 7) that DB verification could not be completed and why.

7. **A report the user can act on.** The user comes away knowing which file was
   written/updated, how many entries were added, what the DB verification in criterion 6
   found, and exactly which specific lines (if any) were low-confidence guesses worth
   spot-checking — plus any front-matter lines you deliberately skipped and why. The JSON file
   is the deliverable; re-importing it into `seforim.db` is a separate, later step — use
    `otzaria-db-linker` when the user asks to write the links into the live DB.

### Automated matcher contract: full coverage without hiding guesses

When a script produces the links, distinguish **coverage** from **approval**:

- The final `_links.json` still has full coverage and only the normal link fields. Do not add
  confidence/debug keys to link entries; the app schema is not a QA metadata channel.
- Write weak, short-anchor, tied, or otherwise uncertain decisions to a separate QA JSON/report
  (`--qa-report` in `linker/dibur_matcher.py`) with the citing line, chosen target, scores,
  evidence class, and reason for review.
- An unresolved content line blocks a final production artifact. Resolve it semantically or
  supply a reviewed override. `--allow-incomplete` is only for an explicitly named intermediate
  review artifact, never for an import-ready file.
- Reviewed manual decisions belong in a deterministic override JSON, not only in generated
  output. The format is an object keyed by citing `line_index_1`; each value is either a complete
  five-field link entry or `null` for a verified legitimate skip. Re-running must reapply and
  report every override.
- A `null` override does not prove that a line is skippable. QA must still confirm it is a
  heading/front-matter/placeholder/colophon under criterion 1.

## What you need to know to get there

This is reference knowledge, not a mandated order of operations — pull from whichever part is
relevant to the specific request in front of you.

**Background docs.** Three docs live inside the otzaria-library repo itself, at the project
root: `docs/README.md` is the doc index — skim it first. It also flags that the DB supports
word-level links, range links, and heading/aliyot entries (`alt_toc/<book>_alt_toc.json`) in
addition to the plain line-to-line links this skill produces — if a request is actually asking
for one of those other mechanisms, that's a different task than what's covered here.
`docs/קישורים-וכותרות.md` is the authoritative doc on link types; `book-database-architecture.md`
is the file-based model the app builds from. Separately, `references/schema-and-heref.md` is
**bundled with this skill itself** (not part of the otzaria-library repo — don't search the
project root for it) and holds a condensed day-to-day version of all three; read it for quick
lookups, and fall back to the full repo docs (or re-read them) whenever you're unsure of a
rule rather than guessing — guessing against these is how silent breakage happens.

**Finding the citing and target books.** Search under any `*/ספרים/אוצריא/**` tree for
`<title>.txt` (`find <repo root> -iname "<title>.txt"`). Sefaria-sourced books typically live
under `extraBooks/SefariaToOtzria/sefaria_export/...`; Otzaria-native books live under the
various `*ToOtzaria/.../ספרים/אוצריא/...` trees. If the physical file exists, you can derive
`line_index` and `heRef` yourself with no DB query needed for the common case (see criterion
3) — just keep the indexing straight: the `_links.json` file always uses **1-based** physical
line numbers (per criterion 2), while the DB's own `lineIndex` column is **0-based**; the
generator converts by subtracting 1 (per `docs/קישורים-וכותרות.md`: "`line_index_1` —
1-based; מומר ל-0-based בגנרטור"). You always write the 1-based version into the JSON —
never do that subtraction yourself. `path_2` in the output is just
`"<target title>.txt"`; it doesn't need to physically exist in this repo, since the app
resolves both sides of a link by title against its own book cache (confirmed by the existing
`קרן אורה על מועד קטן_links.json`, which already targets `מועד קטן.txt` correctly).

**The DB access route — used every run, not just as a fallback.** `seforim.db` is
confirmed to live at
`C:\Users\User\AppData\Roaming\io.github.kdroidfilter.seforimapp\databases\seforim.db`
(i.e. `%APPDATA%\io.github.kdroidfilter.seforimapp\databases\seforim.db` on this user's
machine) — reach it via the Windows-MCP PowerShell tool, not bash, and mind the UTF-8 gotcha
documented in `references/query_seforim_db.md` (also bundled with this skill, not part of the
repo). `scripts/dump_book_from_db.py` finds a book by title and dumps its lines (id,
lineIndex, heRef, content) as JSON. If that exact path doesn't exist (different machine,
different user folder), fall back to `%APPDATA%\...` and ask the user for the real path
rather than guessing. If the database turns out to be genuinely unreachable even after that —
tool unavailable, permission denied, user has no answer — don't block the whole task on it:
finish with the file-derived result and flag clearly in your report that DB verification
(criteria 3 and 6) could not be completed, so the user knows to treat the `heRef` values as
unverified. Two distinct uses:

- When there's no physical target file (rare — a pure Sefaria-only book with no local text),
  this is your only source for the target's lines and `heRef` values.
- Every other time, this is still where you go to satisfy criterion 3 and criterion 6 — pull a
  handful of real rows for the target book and confirm your derived `heRef` values (and,
  ideally, a sample of your line matches) actually agree with what's in the DB before you
  consider the work done.

**Never mix dump sources across sessions or DB copies.** If you dump target-book content
(Gemara/Rashi/Tosafot/etc.) from one `seforim.db` and later write your finished `_links.json`
via `otzaria-db-linker` against a *different* `seforim.db` file — even one that's supposedly
"the same library," e.g. a stale dump left over from an earlier session, or the wrong one of
two `seforim.db`-named files on the machine (see that skill's `db_write_notes.md`) — a given
`lineIndex` is not guaranteed to mean the same physical line in both copies. Confirmed real
case: a dump taken from an old DB copy had a book's `heRef` at `lineIndex` N genuinely differ
from the live DB's `heRef` at that same N (an off-by-a-few-rows shift), which produced a
plausible-looking but wrong `line_index_2`/`heRef_2` that only surfaced later via DB sampling
— the semantic match itself (the actual quoted text) was correct, only the numbering had
drifted. The rule: dump fresh from the exact `seforim.db` path you resolved via
`shared_preferences.json` (see `otzaria-db-linker`'s route) at the start of the session you're
about to write in, and re-dump rather than reuse if meaningful time has passed or you're not
certain it's the same file.

**Matching each citing-book line.** Track the current `<h2>`/`<h1>` section as you read, so
each match stays inside the right window of the target book — and treat every new `<h2>` as a
hard reset: a continuation word at the start of a new heading's block never inherits the
target line from the previous heading's last match, even before anything else in the text has
visibly changed (a citing-book line explicitly quoting somewhere else entirely is a different,
cross-reference situation, not covered here). Find each line's "דיבור המתחיל" — typically the
words right after an inline label like `<b>משנה</b>`, `<b>גמרא</b>`, `<b>רש"י</b>`,
`<b>תוס'</b>` — and match it semantically (nikud, spelling, and wording will differ from the
target's actual text) rather than by exact string comparison. Anchor to the Mishnah/passage
that's the actual subject of the line's discussion, not to every secondary source it cites in
passing while making its point — a line can reference "בריש פרקין" or several other tractates
in the course of its argument and still belong to the one target line it's fundamentally
elaborating on. A line with no independent anchor — a **continuation** of the previous
passage — takes the same target line as the line before it; several consecutive citing-book
lines pointing at one target line is expected, not a bug. Continuity is a **semantic**
judgment, not a closed word list: any opening that signals "still on the previous subject"
(connective / resumptive / elaborative phrasing) counts, whether or not it matches a familiar
label. Common examples include "שם", "והנה", "ונלע"ד", "אמנם", "עוד שם", "עוד כתב", "שוב כתב",
"בא"ד", "ועוד", "וכן" — but an unfamiliar equivalent that clearly continues the prior line is
the same rule. Confirm by checking whether the line actually introduces a **new** citation or
subject before treating it as a continuation. Critically, "the same target line as the line
before it" means the same **book**, not just the same line number: if the previous line was
itself a `super_commentary` onto Rashi/Tosafot, any such continuation — whether it opens with
"בד"ה" or with any other connective that names no new subject — inherits that same
Rashi/Tosafot target, not the Gemara. See "Continuation lines within a super-commentary run"
below for the full rule.

For an explicit cross-reference outside the current section, keep the current-section window
as the default and broaden the search only when the citing wording actually names or clearly
signals the other location. Record that decision for QA. Never turn a failed in-section match
into an unrestricted whole-book search automatically: a generic short dibbur will often find a
plausible but unrelated occurrence elsewhere.

**Ordering for display:** When multiple citing-book lines target the same target line and book
(`line_index_2` + `path_2` identical), **keep them consecutive in the JSON file** (one right
after another). The app's display layer groups consecutive links by target book via the
`groupConsecutiveLinks()` function; if links targeting the same passage are scattered across
the JSON with unrelated targets between them, they may display as separate groups instead of
being unified. Maintaining physical order in the JSON file ensures the panel shows all related
links as a single coherent group.

**Super-commentary lines (רש"י / תוס' ד"ה …).** When a citing line **opens** by naming an
intermediate commentary plus ד"ה — e.g. `רש"י ד"ה אפילו`, `ברש"י ד"ה …`, `תוס' ד"ה …`,
`תוספות בד"ה …` — that line is interpreting **that commentary's own lemma**, not the Gemara
directly. For those lines:

1. Resolve `path_2` to the Rashi or Tosafot book for this masechet (not the Gemara `.txt`).
2. Set `line_index_2` / `heRef_2` to the specific line **in that book** whose opening/dibbur
   matches the lemma after ד"ה (e.g. the Rashi line that starts with `אפילו`).
3. Write `"Conection Type": "super_commentary"`.

Do **not** link such lines as `commentary` onto the Gemara even if the sugya is related.

**Continuation lines within a super-commentary run (critical).** When the citing book is in
the middle of discussing an intermediate commentary (רש"י/תוס'/etc.) — i.e. the immediately
preceding line(s) are `super_commentary` onto that book — the run does not end just because a
later line drops the explicit `ד"ה` / commentator name. **Any** line that continues the
previous passage (no new subject named) stays inside the same intermediate book. This is the
**same** continuation rule as ordinary target-line inheritance above, applied to book as well
as line — not a special case limited to the word `בד"ה`.

Shapes that all stay in the intermediate book (illustrative, not exhaustive):

1. **Explicit lemma continuation:** opens with `<b>בד"ה</b>` / `בד"ה …`.
2. **Any other connective / resumptive opening** that links to the prior line and does not
   name a new subject (Gemara passage, different sefer, different commentator, etc.) —
   e.g. "שם", "והנה", "ונלע"ד", "אמנם", "עוד שם", "עוד כתב", "שוב כתב", "ועוד כתב", "בא"ד",
   "וע"ע מש"כ" when it isn't a fresh citation, or any equivalent phrasing that clearly means
   "still elaborating on what was just said."

In all such cases: treat it like the explicit `ד"ה` case (`super_commentary` into that book;
inherit which one from the nearest prior explicit `בתוס'/ברש"י ד"ה` or prior
`super_commentary` `path_2`), resetting only on a primary-text label like `<b>גמרא</b>` /
`<b>במשנה</b>`, a line that explicitly names a different commentary, or a new section heading.
The trap is treating "no `ד"ה` / no commentator name" as if it meant "back to the Gemara" —
it doesn't; a bare continuation after a Rashi/Tosafot run almost always still means
"[Rashi/Tosafot] wrote further," not "the Gemara says further." Do **not** require the line
to match a fixed trigger list — judge continuity from the wording. A late fix that converts
only explicit intermediate+ד"ה and leaves other continuations as `commentary`→primary text is
incomplete (this is exactly how ~169 lines were mislinked in a past שפת אמת run). Only if the
work never attributes to intermediate commentaries at all should such openings be read as
ordinary primary-text continuations.

A single `_links.json` may therefore mix `commentary`→Gemara entries and
`super_commentary`→Rashi/Tosafot entries; when merging (criterion 5), replace only the stale
subset that shares **both** the same `path_2` **and** the same `Conection Type`. If the user
asked only to link onto the Gemara, still do not mis-target these attribution lines — either
produce the correct `super_commentary` entries (and say so in the report) or leave them out
of the Gemara replacement set and flag them explicitly as needing a separate Rashi/Tosafot
pass. After any super_commentary pass, run the QA skill's full F8+F9 scan
(`.claude/skills/otzaria-commentary-linker-qa`) before calling the work done.

**Pitfalls in extracting the anchor phrase.** These come from debugging a related
automated matching tool, but the same failure modes apply to manual/semantic matching too —
worth checking yourself against every time:

- Don't let leftover label fragments pollute the phrase you're comparing. If a line reads
  `<b>שם</b> ר"א אומר...` or opens with `בגמ'` before the real quote, strip those label words
  out before judging what the line is citing. Matching against "שם ר"א אומר" instead of the
  clean "ר"א אומר" dilutes the comparison and can make you drift away from the correct target
  line — sometimes landing on an unrelated line on a nearby page that happens to share a few
  surface letters with the polluted phrase.
- Don't detect structural boundaries (Mishnah vs. Gemara, or any other section split) by loose
  substring search. Searching for "גמ" to find where "גמרא" starts will also match inside
  unrelated words like "גמליאל" and can close a section early by mistake. Rely on the explicit
  `<h1>`/`<h2>`/`<b>` tags for structure, never on searching for fragments of Hebrew letters
  inside running text.
- Watch for lines that open with an attribution abbreviation before the real quote — e.g.
  `אר"ה כו'` (= אמר רב הונא וכו') — where the actual content you need to match only starts
  after the abbreviation. This doesn't have a clean automatic rule: when you hit one, read past
  the abbreviation for the real quote rather than matching on the opening fragment, and if it's
  still genuinely unclear which target line it points to, that's exactly the kind of line to
  name explicitly in your report (criterion 7) rather than resolve silently.

**Resolving the connection type and reverse-direction requests** — see criterion 4 above;
that's the complete decision procedure, not just a description of the output.

**Merging into an existing links file** — see criterion 5. Compute the stale subset first,
present it to the user in your reply (not buried in a tool call), and only write the merged
file after they confirm. Treat "looks right, go ahead" as confirmation; don't require a
formal sign-off format.
