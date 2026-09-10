# Link schema & connection types — condensed reference

Full detail lives in the project's own `docs/קישורים-וכותרות.md`; this is the condensed
version for quick lookup while doing the matching work.

## `_links.json` entry shape

One array per commentary/citing book, at `<source root>/links/<title>_links.json`:

```json
{
  "line_index_1": 39,
  "line_index_2": 410,
  "ref_2": "Tosafot on Bava Batra 29a:16:1",
  "heRef_2": "תוספות על בבא בתרא כט., טז, א",
  "path_2": "תוספות על בבא בתרא.txt",
  "Conection Type": "source"
}
```

**Direction.** The file is named after the citing book and `line_index_1` is a line *in* it,
but `seforim.db` stores the pair the other way round: `sourceBookId` = the base text,
`targetBookId` = the מפרש. `"source"` is what makes the generator flip it
(`Generator.kt`: `flip = declaredType == SOURCE` → stored as `COMMENTARY`), so it is the
only correct dependent-text value in a citing-named file. `commentary` /
`super_commentary` here get no flip and store the מפרש as the base — the מפרש then vanishes
from the commentary panel and the base text shows up as a "פירוש" on it. Whether the entry
is a plain פירוש or a super-commentary is expressed by `path_2` alone. See the direction
section in `SKILL.md`.

- `line_index_1` / `line_index_2` — **1-based** line numbers (line 1 = first line of the file).
- `path_2` — relative filename of the target book; only the filename (minus extension) is used
  to resolve the title against the app's book cache. The file does not strictly need to exist
  in this repo (Sefaria-only books resolve by title alone). Because resolution is **by exact
  title**, this string must equal `book.title` in `seforim.db` character for character —
  gershayim included: `רש"י על שבת.txt`, **not** `רשי על שבת.txt`, even though the `.txt` on
  disk may well be spelled the latter way. Which gershayim character a title uses cannot be
  guessed from the book's source: Otzaria-native titles are normalized on import and always
  carry `״` (`הערות על וזה לשונו - שובבי״ם`, never the on-disk `''` form), while Sefaria titles
  keep Sefaria's own spelling — usually ASCII `"`, sometimes `״`. Ask the DB. A `path_2` that
  resolves to nothing is not an error: the generator drops the entry silently.
- `ref_2` — the target line's canonical Sefaria reference, e.g. `"Shabbat 2a:2"`,
  `"Rashi on Shabbat 6a:13:1"`; `heRef_2` is the Hebrew rendering of the same address.
  **Required whenever the target is a Sefaria book** (omit only for Otzaria-native targets,
  which have no Sefaria ref). The weekly sync tool re-resolves `line_index_2` from `ref_2`
  after each Sefaria release; without it the line number silently goes stale and the link ends
  up pointing at the wrong line. The generator itself ignores `ref_2` — it is there for the
  sync tool, which is why omitting it costs nothing today and breaks the link later.
- `heRef_2` — display string shown for the link in the app.
- `Conection Type` — sic, this typo is intentional/load-bearing, matches Sefaria's original CSV
  column name. Unrecognized values silently become `OTHER`.

Two optional extensions (both supported by the Otzaria generator, but the Python `linker/`
pipeline doesn't currently emit them — irrelevant to this skill, just documented for
completeness):
- `start` / `end` — raw character offsets into `line_index_1`'s content, for a word-level anchor
  (e.g. the (א)(ב)(ג) markers in שער הציון). Only ever on the source side.
- `line_index_1_end` / `line_index_2_end` — 1-based inclusive end line, for a link that spans a
  range of lines on either side.

## Connection types (14 total)

```
source             — **the value a citing-named file writes for every dependent-text link**
                     (פירוש, פירוש על פירוש, תרגום, מדרש…). Not stored as-is: the generator
                     flips the pair into canonical base→מפרש order and stores COMMENTARY.
                     `path_2` says which relation it is — the base text, or the intermediate
                     book (רש"י/תוספות) for a super-commentary line.
commentary       — פירוש/מפרש רגיל. Correct **only** in a base-named file, where
                     `line_index_1` is already a line of the base text (MoreBooks/ToratEmet/
                     Ben-Yehuda/tashma/wikiJewishBooks convention). In a citing-named file it
                     is the reversed-direction bug.
super_commentary  — פירוש על פירוש. Same caveat as `commentary`; stored SUPER_COMMENTARY is
                     treated identically to COMMENTARY by every app query, only the Hebrew
                     label differs.
targum            — תרגום (same base-named caveat)
reference          — הפניה כללית, lateral — no flip, written under its own name from either
                     side (this is what the automated linker/ pipeline emits under the
                     hood before to_otzaria_links.py relabels it "linker")
midrash
quotation
mesorat_hashas
ein_mishpat
dibur_hamatchil
parshanut
mishnah_in_talmud
related
other              — fallback for unrecognized/empty strings
```

If the user says "מקור", pin down which book they mean before choosing a form: "מקור" is used
in this project both for the base text and for the citing book. It does *not* by itself decide
the file's direction — a citing-named file with `"source"` entries and a base-named file with
`"commentary"` entries produce the identical row in `seforim.db`.

## Deriving heRef from a physical text file (Talmud-style books)

Confirmed against `מועד קטן.txt` / `seforim.db`, and against the already-completed
`קרן אורה על מועד קטן_links.json` in this repo:

- Line 0 (0-based) is normally `<h1>title</h1>` — no heRef.
- Every `<h2>...</h2>` line starts a new section — no heRef of its own, and resets the letter
  counter to 0 for what follows.
- Every other line gets `heRef = "<book title> <h2 text>, <hebrew numeral>"` where the numeral
  is a 1-based running count of content lines since the last heading, written in standard
  Hebrew gematria (א,ב,ג,ד,ה,ו,ז,ח,ט,י,יא,יב,יג,יד,טו,טז,יז,יח,יט,כ,...) — note טו/טז (not
  יה/יו), the standard convention that avoids spelling God's name.

Example: `<h2>דף ב.</h2>` is followed by content lines 1–13 → heRefs `"מועד קטן ב., א"`
through `"מועד קטן ב., יג"`. The next `<h2>דף ב:</h2>` resets the counter, so its first content
line is `"מועד קטן ב:, א"`.

This convention is specific to Talmud-daf-style books (paged דף/עמוד structure). Books with a
different structure (Tanakh, halachic codes organized by סימן/סעיף, etc.) may label sections
differently — sample a few real `heRef` values (from an already-linked sibling book, or from
`seforim.db` directly) before assuming this pattern applies.
