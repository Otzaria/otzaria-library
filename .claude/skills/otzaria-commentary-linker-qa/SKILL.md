---
name: otzaria-commentary-linker-qa
description: >
  Audits and verifies Otzaria commentary↔source `_links.json` files produced by the
  otzaria-commentary-linker skill — for any citing book (מפרש/תרגום/מדרש/etc.), not a
  specific title. Use whenever the user asks to check, verify, validate, QA, or spot-check
  a links file ("תבדוק את הקישורים", "אמת את קובץ הקישורים", "QA על הלינקים", "בדיקת
  קישורים של X על Y", "ביקורת על הקישורים"), after a linker run reports low-confidence
  lines, for batch audits of many books, or when reviewing whether רש"י/תוס'/בד"ה lines
  are wrongly linked as commentary→base text instead of super_commentary→that intermediate
  book. Not when creating or rewriting the links themselves (that is
  otzaria-commentary-linker).
---

# Otzaria commentary-linker QA

You are the **auditor** of someone else's (or a prior run's) `_links.json`. You do **not**
rewrite the links file unless the user explicitly asks you to fix it after the report.

This skill applies to **any** citing book in the Otzaria library (Talmud commentaries,
Tanakh parshanut, codes, midrashim, etc.). Examples from past runs (e.g. שפת אמת) are
illustrative only — never assume the citing title, author byline, or target genre.

## שפת התגובה

**עברית בלבד** מול המשתמש (שמות שדות/נתיבים/פלט סקריפט מותרים באנגלית).

## Companion docs

- Creation rules (must re-read before QA): `.claude/skills/otzaria-commentary-linker/SKILL.md`
  — especially criterion 4 (super_commentary via ד"ה).
- Condensed schema/heRef: `../otzaria-commentary-linker/references/schema-and-heref.md`
- DB access: `../otzaria-commentary-linker/references/query_seforim_db.md`
- Failure modes + optional case study: `references/failure-modes.md` (this skill)

## Inputs (resolve before checking)

From the user request (or the linker run's report), pin down:

1. **links file** — usually `…/links/<citing title>_links.json`
2. **citing book** `.txt` (the מפרש / תרגום / …; `line_index_1`)
3. **primary target book** `.txt` (base text the work mainly comments on; default `path_2`)
4. Optional: **intermediate targets** (רש"י / תוספות / other named commentaries on the same
   base text) when the citing book does פירוש-על-פירוש
5. Optional: **low-confidence `line_index_1` list** — mandatory semantic sample
6. Optional: expected **skipped front-matter** / colophon lines (author-specific)
7. Optional: expected leftover `"Conection Type": "linker"` counts (preserve; do not
   merge into commentary coverage)

If any of 1–3 is missing, search under `*/ספרים/אוצריא/**` and `*/links/*_links.json`
before asking. Terminology: **citing** = הספר שמקשרים ממנו, **target** = הספר שאליו
מצביעים (`path_2`).

For a **batch** (many volumes of one series, or many unrelated books), resolve a table of
`(title, citing.txt, links.json, primary target, expected linker count)` first, then run
the same checklist per book and one summary table at the end.

## What "correct" means

A links file passes only if all of these hold:

| # | Check | Severity if broken |
|---|---|---|
| 0 | **Source integrity** — citing `.txt` exists, size > 0, opens with expected `<h1>` (the citing title), real Hebrew content; links filename is `*_links.json` (not `*.links.json`) | `blocker` |
| 1 | **Completeness** — every non-heading, non-blank, non-front-matter, non-colophon citing line has **exactly one** commentary/super_commentary entry | `blocker` |
| 2 | **No duplicates** — no `line_index_1` more than once among commentary+super_commentary (`linker` duplicates allowed) | `blocker` |
| 3 | **Schema** — commentary/super_commentary entries have exactly the five keys `line_index_1`, `line_index_2`, `heRef_2`, `path_2`, `"Conection Type"` (missing second `n`); `linker` may keep extra `start`/`end` | `blocker` / `major` |
| 4 | **heRef** — `heRef_2` matches `seforim.db` for `path_2` at `line_index_2 - 1` (0-based DB) | `major` |
| 5 | **Semantic match** — citing content discusses the chosen target line, not merely the same section/daf/perek | `major` / `minor` / `info` |
| 6 | **Super-commentary attribution** — when applicable: lines that open by naming an intermediate commentary + ד"ה (or any continuation of that run — `בד"ה`, or any other connective/resumptive opening that links to the previous passage and names no new subject) must be `super_commentary` into that book, **not** `commentary`→primary base text | `major` |
| 7 | **Preserve `linker`** — pre-existing `"Conection Type": "linker"` entries stay untouched; do not count them toward commentary coverage | `major` if stripped/altered |

Indexing: `line_index_*` are **1-based physical** file lines. DB `line.lineIndex` is
**0-based** → compare with `line_index_2 - 1`.

### Front-matter / skip rules (do not demand a link)

Skip (still count toward physical line numbers):

- `<h1>`…`<h6>` headings
- blank lines
- **Author byline** under the title — whatever form this book uses (short line with the
  author's name right after `<h1>`; may appear in spelling variants across volumes of the
  same series). Discover from the file; do not hardcode one author's name as the only rule.
- missing-page markers like `@@@חסר עמוד מקורי@@@` (or project-equivalent placeholders)
- end colophons (`סליק מסכת …`, `תם ונשלם …`, etc.) — report as `info` if unlinked

A "missing coverage" hit that is only a byline/colophon is **not** a blocker — classify as
front-matter and move on.

---

## Workflow

Copy and track (single book or per book in a batch):

```
QA Progress:
- [ ] 0. Source integrity (txt + links filename)
- [ ] 1. Resolve paths + load JSON/texts
- [ ] 2. Run deterministic script / structural pass
- [ ] 3. Verify heRef vs seforim.db (sample ≥15–20, not only start of file)
- [ ] 4. Super-commentary attribution FULL SCAN (if the citing book uses it)
- [ ] 5. Semantic sample (regular + all low-conf + flagged supers)
- [ ] 6. Deliver Hebrew report (no silent rewrite)
```

### 0. Source integrity (do this first)

Before trusting any links file:

1. Citing `.txt` exists and `st_size > 0`.
2. First line is (or contains) `<h1>…<citing title>…</h1>` matching the book under review.
3. File has substantial Hebrew letters (not empty/garbage/wrong book pasted in).
4. Links path is `links/<title>_links.json` — flag leftover `*.links.json` as `blocker`
   until renamed (this class of typo has appeared in real runs).
5. In a batch: confirm **every** listed citing file is present (accidental deletes have
   happened — catch that here).

### 1. Deterministic / structural checks

Prefer the bundled script; for batch / multi-`path_2` work you may wrap it or extend with a
temp auditor:

```bash
chcp 65001
python -X utf8 .claude/skills/otzaria-commentary-linker-qa/scripts/validate_links.py \
  --links "<links.json>" \
  --citing "<citing.txt>" \
  --target "<primary-target.txt>" \
  --skip-line <n> \
  --db "%APPDATA%/io.github.kdroidfilter.seforimapp/databases/seforim.db"
```

On Windows PowerShell: **always** `chcp 65001` + `python -X utf8`, and prefer a real
`.py` file under `%TEMP%` over `python -c` with Hebrew (quoting breaks).

Structural rules the auditor must enforce:

- JSON loads; root is an array.
- Split entries by `"Conection Type"`:
  - `commentary` / `super_commentary` → coverage + duplicate checks; prefer exactly 5 keys.
  - `linker` → preserve; optional count vs expected; **exclude** from coverage/dupe rules.
- Coverage = every linkable citing line has one commentary **or** super_commentary entry.
- Do **not** stop at green structural output — steps 3–5 are mandatory.

### 2. heRef / DB gate

Default DB:
`%APPDATA%\io.github.kdroidfilter.seforimapp\databases\seforim.db`

For **each distinct `path_2` title** used in the file (primary target **and** any
intermediate books):

1. `SELECT id, title, totalLines, isBaseBook FROM book WHERE title = ?`
2. Sample **≥15–20 random** commentary/super_commentary entries (not only the head of the
   file); force-include some `super_commentary` if present.
3. For each sample: `line` where `bookId=? AND lineIndex=line_index_2-1`; require
   `heRef == heRef_2` exactly.
4. If DB unreachable: continue, mark DB gate as **limitation** (not a silent pass).

heRef shape depends on the target genre. For Talmud-daf books it is usually
`"<title> <label>, <gematria>"` (often **without** `דף`). For Tanakh / codes / other
structures, copy the convention from DB or from an existing `_links.json` with the same
`path_2`. Prefer precedent over inventing a formula.

### 3. Super-commentary attribution — FULL SCAN (check 6)

Run this whenever the citing book (or the links under review) may comment on an intermediate
commentary. If the work is a pure direct commentary with no רש"י/תוס'/similar labels, the
scan should find zero candidates — still run it; a clean zero is a useful result.

Scan **every** citing content line, not a sample.

#### Trigger patterns (after stripping outer whitespace; allow `<b>…</b>`)

**Explicit** (always expect `super_commentary` → intermediate book):

- `רש"י ד"ה` / `ברש"י ד"ה` / `רש"י בד"ה` / `ורש"י ד"ה`
- `תוס' ד"ה` / `בתוס' ד"ה` / `ותוס' ד"ה` / `תוספות ד"ה` / `בתוספות ד"ה`
- Same with ד"ה **inside** the bold tag: `<b>תוס' ד"ה …</b>`
- Any other named intermediate book in the same shape (e.g. `תוספות ישנים`, מהרש"א, …)
  when the line is clearly commenting on that book's lemma

**Continuation (any link to the previous passage) after a super_commentary run:**

- Line opens with `<b>בד"ה</b>` / `בד"ה …`, **or** with **any** connective / resumptive /
  elaborative opening that clearly continues the prior line and names no new subject.
  Continuity is semantic, not a closed trigger list. Familiar examples include `שם`, `והנה`,
  `ונלע"ד`, `אמנם`, `עוד שם`, `עוד כתב`, `שוב כתב`, `בא"ד`, `ועוד` — but an unfamiliar
  equivalent that still means "still on what was just said" is the same rule. Applies when
  the line immediately follows a line already linked `super_commentary`.
- When the surrounding block is discussing an intermediate commentary, this is an **implied
  continuation** of that commentator — **not** a primary-text lemma, and **not** a plain
  Gemara continuation either, even though the line carries no `ד"ה` / commentator name.
- Expect `super_commentary` into that intermediate book (inherit which one from the nearest
  prior explicit label / prior `super_commentary` `path_2`; reset on a primary-text label
  like `<b>גמרא</b>` / `<b>במשנה</b>` / `<b>פסוק</b>` / a line naming a different commentary /
  new section heading, as appropriate to the genre).
- Fail as `major` if type is `commentary` and `path_2` is the primary base text — this
  includes any such continuation lines, not just explicit `בד"ה` lines. Do **not** require a
  match against a fixed word list before flagging.
- Only if the citing book never attributes to intermediate commentaries should bare `בד"ה` or
  other continuations be read as a primary-text lemma (see F6).

**What must be true for triggered lines:**

1. `"Conection Type"` = `super_commentary`
2. `path_2` = the intermediate book (e.g. `תוספות על <מסכת>.txt`, `רש"י על <מסכת>.txt`) —
   **not** the primary base text
3. `line_index_2` / `heRef_2` point at the lemma line whose דיבור matches the words after ד"ה

**Fail `major` if** any of: primary-text `path_2`; type `commentary`; wrong lemma/section in
the intermediate book.

When you can resolve the correct intermediate line in DB (LIKE search on the lemma,
nikud-insensitive), put it in the report as the suggested fix.

#### Partial-fix trap

A pass that converts only **explicit** `בתוס'/ברש"י ד"ה` to `super_commentary` but leaves
continuation lines (`בד"ה` **or** any other connective that continues the prior passage) as
`commentary`→primary text will look green on structure + heRef and still fail check 6.
**Never treat "explicit-only" super fixes as done without a full continuation scan** when the
citing book uses that pattern — and do not limit that scan to the word `בד"ה`.

### 4. Semantic sampling

**Always** sample:

- ~20–30 **regular** entries spread through the file (random, not only the start)
- **Every** low-confidence `line_index_1` from the linker report
- **Every** line flagged by the super-attribution scan
- Continuations — any line whose opening links to the previous passage rather than naming a
  new subject (genre-typical examples for Talmudic אחרונים: `שם`, `והנה`, `ונלע"ד`, `אמנם`,
  `עוד שם`, `עוד כתב`, `שוב כתב`, `בא"ד`, and equivalents) — should usually inherit the
  previous target **book**, not just the previous line number, unless a new quote appears. If
  the previous target was itself `super_commentary`, the inherited target stays in that same
  intermediate book — this is the same trap as check 6/F9, so cross-reference that scan when
  sampling these lines. Judge continuity from the wording; do not require a fixed trigger list.

After a matcher/parser/scoring change, add a **change-sensitive stratified sample** in addition
to the regular random sample:

- Sample at least 20–30 lines from every textual pattern whose routing or extraction logic
  changed (for example `שם` + a second `<b>` span, or bare `<b>בד"ה</b>`).
- Compare old target versus new target for every changed entry; do not inspect only the lines
  named in the bug report that motivated the code change.
- Review every new low-confidence item, every resolved/unresolved status change, and every
  manual override. A decrease in `unresolved` is not automatically an improvement if guesses
  were merely forced into the output.
- Import-ready requires zero semantic `major` findings in these changed-pattern samples. Report
  the observed accuracy percentage per pattern; do not merge it into the ordinary random sample.

For each sample: read citing line + target line (+ nearby DB lines). Judge dibbur/subject
overlap.

#### How to confirm a miss

1. Extract dibbur (strip labels / `שם` / abbreviations).
2. Search nikud-insensitive inside the **current section window** of the claimed target book
   (daf / perek / siman — whatever the target uses).
3. If a better line exists → `major` + suggested `path_2` / `line_index_2` / `heRef_2` / type.
4. Citing heading says section X but link is section Y → almost always `major`.
5. For F8/F9: open the intermediate commentary for that section and find the lemma line.

#### Automated overlap caveats

Word-overlap / "dibur not in target" heuristics produce **many false positives** when:

- the citing text uses abbreviations (`כו'`, `ק"ו`, …)
- target has nikud and citing does not
- continuation lines inherit a correct target but share few surface tokens

Use heuristics only to **prioritize** human/LLM reading. High overlap + matching lemma =
likely OK even if a naive dibbur matcher says false. Zero overlap on a low-conf line =
investigate with nearby lines (classic off-by-one on the same section).

### 5. What you must not do

- Do **not** rewrite `_links.json` as part of QA unless the user asks to fix after the report.
- Do **not** "fix" `"Conection Type"` → `"Connection Type"`.
- Do **not** treat file-derived heRef alone as enough when DB is available.
- Do **not** mark semantic QA passed on "same section/daf" only.
- Do **not** accept intermediate-attribution / continuation lines (after a super run) as
  `commentary`→primary text when check 6 applies — including openings that are not `בד"ה`.
- Do **not** demand links for author bylines / missing-page markers / colophons.
- Do **not** drop or "clean up" `"Conection Type": "linker"` entries during QA.
- Do **not** hardcode one series' author names, paths, or masechet list as if they were the
  skill's only scope.

---

## Report format

### Single book

```markdown
# בדיקת קישורים — <citing title> → <primary target>

**סטטוס**: ✅ תקין / ⚠️ דורש תיקונים / ❌ חוסם

## סיכום
- רשומות: N (commentary=…, super_commentary=…, linker=…)
- שורות תוכן צפויות: M | חסרות: … | עודפות: …
- מקור txt: תקין / … | שם קובץ links: תקין / …
- heRef מול DB: ok/n (או: DB לא זמין — …)
- ייחוס ביניים (super_commentary): A מועמדים | B שגויים (type/path)
- סמנטי: X major, Y minor (מתוך … שנדגמו / כל ה-low-conf)

## חוסמים (blocker)
…

## גדולים (major)
| line_index_1 | נוכחי | מומלץ | הערה |
|---|---|---|---|
| … | `path` `li2` heRef / type | `path` `li2` heRef / type | … |

## קטנים (minor) / info
…

## דגימה תקינה
- …

## המלצה
לתקן לפני ייבוא ל-seforim.db / מוכן לייבוא / …
```

### Batch (many books)

Add a top summary table:

| ספר | מבני | מקור txt | DB heRef | super-scan שגויים | סמנטי major | סטטוס |
|---|---|---|---|---|---|---|
| … | עבר/נכשל | … | ok/n | N | N | … |

Then list concrete errors with `ספר` + `line_index_1`. End with an explicit import verdict:
**כשיר לייבוא** / **לא כשיר** + blockers.

Severity:

- `blocker` — missing/dupe coverage (real content), invalid JSON/schema, missing source file,
  wrong `*.links.json` name
- `major` — wrong target/heRef/path/type; intermediate attribution / continuation after a
  super run as `commentary`→primary text
- `minor` — weak but plausible; off-by-one inside same section
- `info` — byline/colophon confirmed skipped; DB skipped; linker count note

---

## Illustrative case study (not scope)

Past independent QA on **שפת אמת על בבלי** (11 volumes) is summarized in
`references/failure-modes.md` under "Case study". Use it to recognize failure patterns
(especially F9/F10), not as a limit on which books this skill covers.

**Reusable verdict pattern:** structural green + heRef green does **not** imply import-ready
when the citing book heavily uses intermediate attributions / continuations after them.
Always run the full F8+F9 scan before approving import into `seforim.db`.

## Companion skill

Creation/update of links: `.claude/skills/otzaria-commentary-linker/SKILL.md`.  
This QA skill audits that output; it does not replace it.
