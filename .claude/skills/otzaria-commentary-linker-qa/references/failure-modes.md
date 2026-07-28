# Failure modes & sampling notes (QA companion)

Read this when doing the **semantic** / **super-attribution** pass after structural checks
(`scripts/validate_links.py` or a batch auditor).

Applies to **any** citing book. Named titles below are examples from past audits.

## Priority sample set

1. Every `line_index_1` the linker flagged as low-confidence.
2. Spread ~20–30 regular entries across the file (random — not only the head).
3. Extra focus on citing lines that start with genre-typical labels, e.g. `שם`, `בד"ה`,
   `בא"ד`, `כו'`, `אר"…`, `ברש"י`, `בתוס'`, or sit right after a new section heading
   (`<h2>`/`<h3>`/`<h4>` — daf, perek, siman, …). Also any other opening that clearly
   continues the previous passage (not a closed word list).
4. **Mandatory full scan** (not a sample) when intermediate attribution may appear:
   - Explicit: `רש"י ד"ה` / `ברש"י ד"ה` / `תוס' ד"ה` / `בתוס' ד"ה` / `ותוס' ד"ה` /
     `תוספות ד"ה` (and close variants, including ד"ה inside `<b>…</b>`), plus any other
     named intermediate book in the same shape.
   - Continuation: line opens with `<b>בד"ה</b>` / `בד"ה`, **or** with **any** connective /
     resumptive opening that links to the prior passage and names no new subject (examples:
     `שם`, `והנה`, `ונלע"ד`, `אמנם`, `עוד שם`, `עוד כתב`, `שוב כתב`, … — judge continuity
     from the wording, do not require a fixed trigger list), directly after an
     intermediate-commentary discussion (F9) — these are **not** optional when that pattern
     exists in the book, and the non-`בד"ה` case is the easier miss since there's no `ד"ה`
     marker to search for.

## Recurring failure modes

| Code | Pattern | What it looks like |
|---|---|---|
| F1 | Section-start fallback | `heRef` is the first letter/line of the section but dibbur quotes a later line |
| F2 | Same section, wrong line | Right daf/perek/siman; target text is a different statement |
| F3 | Broken continuation chain | Several consecutive citing lines share one wrong `line_index_2` after a bad first guess (`שם` / `בא"ד` / …) |
| F4 | Heading-level drift | Citing section heading does not match the linked section (e.g. citing `דף יח.` → linked `דף ב.`) |
| F5 | Label pollution | Match driven by `שם`/`בגמ'`/`אר"ה` instead of the quote after it |
| F6 | Plain `בד"ה` on a **direct** base-text commentary | No prior intermediate-commentary context in the book/block; `בד"ה X` means the primary-text lemma — land on that line, not a random nearby line |
| F7 | Secondary citation | Linked to a work/line mentioned in passing, not the primary subject under the current heading |
| F8 | Explicit super-commentary → primary text | Line opens `רש"י ד"ה X` / `תוס' ד"ה X` (etc.) but `path_2` is the base text and/or type is `commentary`; should be `super_commentary` onto the intermediate lemma line for X |
| **F9** | **Continuation (any link to prior passage) → primary text** | Line continues a prior intermediate-commentary discussion — opens with `<b>בד"ה</b> …`, **or** with any other connective/resumptive phrasing that names no new subject (examples: `עוד כתב`, `שוב כתב`, `עוד שם`, `שם`, `והנה`, `ונלע"ד`, `אמנם`, …) — but is still `commentary`→base text. Continuity is semantic, not a closed trigger list; the non-`בד"ה` case is the easier miss. Inherit the intermediate book from the nearest prior explicit label / prior `super_commentary` target |
| F10 | Partial super-fix | Explicit intermediate+ד"ה converted to `super_commentary`, but later continuations of that run (including non-`בד"ה` openings) left as `commentary`→primary — structural+heRef QA still green |
| F11 | Wrong intermediate book | e.g. should be `תוספות ישנים על …` but linked to regular Tosafot or base text (verify lemma in DB) |
| F12 | Source-file / filename integrity | Citing `.txt` missing/empty/wrong content; or links saved as `*.links.json` instead of `*_links.json` |
| F13 | False "missing coverage" on front-matter | Author byline (any spelling variant) or colophon (`סליק…` / `תם ונשלם…`) flagged as missing — classify as skip/`info`, not blocker |
| F14 | Heuristic false positive | Automated dibbur/overlap checker says miss because of abbreviations, nikud, or continuation sparsity — re-read before filing `major` |
| F15 | Trigger-regex blind spot | The automated super-attribution scanner's own trigger pattern misses a real opener, so the check silently reports 0 problems even though F8/F9 is present — e.g. requiring bare "ד\"ה" right after the name when the source actually writes "בד\"ה" (ב fused onto ד"ה) almost everywhere, or missing a commentator name the book actually uses (רשב"ם, or a print/OCR variant like חוס' for תוס'). A clean `super_wrong_count: 0` from `validate_links.py` only means "no problems among the openers this version's regex can see" — periodically re-derive the trigger list from what the book's own bold openers actually say (see "Deriving the trigger list" below), don't assume the bundled regex already covers every name/spelling this book uses |
| F16 | Forced best candidate | Matcher writes the highest-scoring candidate even though the absolute score is weak, the dibbur has only one informative token, or several candidates are effectively tied. Preserve full final coverage, but route this decision through the QA sidecar/manual-review flow before treating it as production-approved |
| F17 | Regeneration loses hand fixes | Correct targets were edited only in the generated `_links.json`; the next matcher run silently restores the old guesses. Store reviewed choices in the deterministic override input and verify that the run reports them as applied |

## How to confirm a miss

1. Extract the dibbur (strip labels/`שם`/abbreviations).
2. Search that phrase (nikud-insensitive) inside the **current section window** of the
   claimed target book — not the whole work first.
3. If a better line exists in-window, mark `major` and suggest that `line_index_2` + heRef.
4. If the citing heading says section X but the link is section Y → almost always `major` (F4).
5. **F8:** open the intermediate commentary for the same section; find the line headed by
   `<lemma>`. Suggest that `path_2`, `line_index_2`/`heRef_2`, type `super_commentary`.
6. **F9:** same as F8, but first decide **which** intermediate book by scanning upward for
   the last explicit intermediate+ד"ה (or last `super_commentary` `path_2`) before a
   primary-text reset label / new section heading.
7. When DB is available, `LIKE '%lemma%'` on the intermediate book's `line.content` often
   finds the exact row quickly.

## heRef quick check

Confirm convention from DB or an existing `_links.json` with the same `path_2`. For
Talmud-daf targets, Otzaria often stores `"<מסכת> ב., א"` (no word `דף`). If the links file
disagrees with the DB spelling, that is a real `major` even when the line index is right.

Sample **≥15–20 random** entries per book (and force some `super_commentary`); matching only
the first N entries hides drift later in the file.

## Deriving the trigger list (do this before trusting a clean super-scan)

`scripts/validate_links.py`'s `EXPLICIT_SUPER_RE`/`BDH_RE` encode a fixed list of names and
connectives (רש"י, תוספות/תוס', רשב"ם, חוס', with an optional ב before ד"ה). That list was
built by reading real failures across past runs — it is not guaranteed to cover the next
book's own vocabulary. Before relying on `super_wrong_count` as a green light:

1. Extract every distinct opening word/phrase from the citing book's `<b>…</b>` tags (or
   plain-text line openings) — a one-line `grep`/regex frequency count over the whole file.
2. Skim the list for any commentator name or spelling variant not already in
   `EXPLICIT_SUPER_RE` (new names like מהרש"א/רשב"א when they function as an intermediate
   commentary the way רש"י/תוספות do here, unfamiliar abbreviations, OCR-style misspellings).
3. If you find one, treat it the same way רשב"ם and חוס' were added: extend
   `EXPLICIT_SUPER_RE` (and the linker's own equivalent, `NAME_MAP`/`is_super_commentary_trigger`
   in whatever script produced the file) rather than hand-waving the gap away — a name missing
   from the regex means the scan silently can't see that whole class of line (F15).
4. Re-run the scan after extending it. A `super_candidates` count that goes up after a fix is
   expected and good — it means real openers that were invisible before are now being checked,
   not that something broke.

## `linker` entries

Automated Sefaria-citation leftovers use `"Conection Type": "linker"`. They are **out of
scope** for commentary coverage/dupe rules. If the user (or a prior report) gives an expected
count for this book, flag only when it changes unexpectedly. Do not invent expected counts
from another series.

---

## Case study (illustrative) — שפת אמת על תלמוד בבלי

One past audit after initial linking + a late super_commentary pass. **Not** the skill's
scope limit — only a concrete illustration of F8–F14.

### What looked fine

- All 11 citing texts present; sizes sane; Hebrew content real.
- No leftover `*.links.json` names (those had already been fixed for two volumes).
- JSON schema (5 fields), no commentary/super dupe `line_index_1`, full content coverage.
- DB `heRef_2` samples: 100% match across books.
- Pre-existing `linker` counts preserved where expected.
- Several volumes: super-attribution scan clean.
- At least one `תוספות ישנים` target verified by lemma match in DB.

### What failed (import blockers)

| Volume | Super-scan failures | Notes |
|---|---|---|
| שבת | ~169 (mostly F9 `בד"ה` + some F8 explicit) | Hundreds of other `super_commentary` entries OK — fix was partial (F10) |
| זבחים | dozens of F9 | |
| Other volumes | smaller F8/F9 counts | |

### Confirmed semantic majors (pattern)

- Explicit/continuation Rashi–Tosafot lines still pointed at Gemara while the correct
  intermediate lemma existed in DB.
- Same-amud wrong line (F2) on low-confidence continuations.
- Front-matter / colophon false "missing" hits (F13); heuristic false positives (F14).

### Verdict pattern to reuse on any book

> Structural green + heRef green **does not** imply import-ready when the citing book
> uses intermediate attributions / continuations after them. Always run the full F8+F9 scan
> before approving import into `seforim.db`.
