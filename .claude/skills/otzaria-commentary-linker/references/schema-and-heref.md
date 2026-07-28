# Link schema & connection types — condensed reference

Full detail lives in the project's own `docs/קישורים-וכותרות.md`; this is the condensed
version for quick lookup while doing the matching work.

## `_links.json` entry shape

One array per commentary/citing book, at `<source root>/links/<title>_links.json`:

```json
{
  "line_index_1": 39,
  "line_index_2": 1,
  "heRef_2": "רש\"י",
  "path_2": "רש\"י על צלח על פסחים.txt",
  "Conection Type": "commentary"
}
```

- `line_index_1` / `line_index_2` — **1-based** line numbers (line 1 = first line of the file).
- `path_2` — relative filename of the target book; only the filename (minus extension) is used
  to resolve the title against the app's book cache. The file does not strictly need to exist
  in this repo (Sefaria-only books resolve by title alone).
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
commentary       — פירוש/מפרש רגיל (Rashi, Tosafot, קרן אורה, etc. onto Gemara/base text)
super_commentary  — פירוש על פירוש (e.g. a line opening `רש"י ד"ה …` / `תוס' ד"ה …` must
                     target that Rashi/Tosafot book + lemma line, not the Gemara)
targum            — תרגום
reference          — הפניה כללית (this is what the automated linker/ pipeline emits under the
                     hood before to_otzaria_links.py relabels it "linker")
source             — virtual only, never stored — derived at read time by inverting a
                     commentary link. Never write this value yourself.
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

If the user's request doesn't map cleanly to one of these (e.g. they say "מקור" — meaning "link
X as the base text under Y", which is the *reverse* direction and not a type you store — swap
which book is line_index_1/commentary and which is path_2/target instead of trying to write a
"source" type).

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
