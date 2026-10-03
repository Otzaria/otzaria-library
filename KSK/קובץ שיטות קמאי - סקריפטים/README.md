# Kovetz Shitot Kamai - official 2026 edition converters

These scripts produced the 38 per-tractate books now kept under
`KSK/ספרים/אוצריא/תלמוד בבלי/ראשונים/קובץ שיטות קמאי/סדר <seder>/`
(28 from Word 97-2003 `.doc` sources, 10 from HED PRESS PDFs, including
Menachot, which had no earlier edition). `KSK/ספרים/אוצריא` is one of the
`BOOK_ROOTS` in `manual_links_packaging.py`, so these books ship in the library
release (under `אוצריא/תלמוד בבלי/ראשונים/קובץ שיטות קמאי/`) with source `KSK`.
Besides them, the same root holds nine single-rishon books that
`split_rishonim.py` extracts from these tractates (see the last section); they
ship too. Nothing else under `KSK/` is packaged: not this folder (the scripts are
kept for reproducibility only).

Output is deterministic: re-running on the same sources gives byte-identical
books (checked for one `.doc` and one PDF tractate when these files were added).

## Requirements

Python 3.10+ with `olefile` (the `.doc` parser) and `pypdf`, `pymupdf` and
`fonttools` (the PDF decoders). A virtualenv is recommended; none is kept here.

## Inputs and configuration

The scripts read and write everything in a *work directory*, `$KSK_WORK`
(by default this folder; point it somewhere outside the repo):

| file | contents |
| --- | --- |
| `manifest.json` | `{"<idx>": {"path": <absolute source file>, "rel", "type": ".doc"/".pdf", "size"}}` for the 42 files of the official source folder (one file per tractate, with Menachot split over 5 PDF volumes) |
| `mapping.json` | `{"<idx>": {"file", "type", "tractate_he", "filename_stem", "translit", "title_line"}}`; needed only for a PDF tractate with no earlier file (Menachot) |

Neither file is checked in: both hold local absolute paths to the source
folder. Rebuild them from a listing of that folder.

Environment variables (all optional):

- `KSK_WORK`: the work directory above.
- `KSK_REPO`: the otzaria-library checkout (default: two levels above this folder).
- `KSK_OLD_ROOT`: the reference tree for each book's `<h1>` and file name, laid
  out as `<root>/קובץ שיטות קמאי/סדר <seder>/<name>.txt`. The default
  (`$KSK_REPO/KSK/ספרים/אוצריא/תלמוד בבלי/ראשונים`) is the packaged books
  themselves, which replaced the **pre-2026** edition under the same names: the
  `<h1>`/name lookup works, but QA then compares a book with itself. For a real
  comparison, extract the old tree from the last commit that had it:
  `git archive 93c9fa6d KSK | tar -x -C /some/dir` and set
  `KSK_OLD_ROOT=/some/dir/KSK`.
- `KSK_VALIDATOR`: path to `validate_book.py` (default: the repo's
  `.claude/skills/otzaria-book-format/scripts/validate_book.py`).

`convert_doc.py` also reads `replace.csv` from this folder: the label fixes
(cp1255) moved here from the old `KSK/fix and split/` scripts, which were removed.

Every book (the 38 tractates and the nine single-rishon books) has three header
lines: `<h1>title</h1>`, the author line, and the publisher's copyright notice in
small gray print, `<span style="color:Gray;"><small><small>...</small></small></span>`
(the markup other library books use for such notices). The notice text is kept in
`copyright.txt` (one UTF-8 line) and `copyright_line.py` builds the line; all
three generators and both QA scripts import it from there. Line numbers in
`KSK/links/*_links.json` (`line_index_1`) count this line.

## Pipeline and run order

Run every command from `$KSK_WORK`.

`.doc` tractates (indices listed in `convert_doc.DOC_IDX`):

1. `extract.py <idx>`: parses the `.doc` file with `docparse.py` (piece table +
   paragraph/character properties) into `txt/`, `html/` and `paras/<idx>.jsonl`.
   `convert_doc.py` runs this for you when `paras/<idx>.jsonl` is missing.
2. `convert_doc.py [idx ...]`: writes `out/<idx>.txt`, `out/<idx>.stats.json` and
   `out/names.json` (idx -> target book name).
3. `qa.py [idx ...]`: compares each book with the old one and runs the validator;
   writes `out/qa.json`. It prints structure and counts only.

PDF tractates (keys listed in `convert_pdf.BOOKS`):

1. `convert_pdf.py [key ...]`: decodes the PDFs with `kskdec.py` (glyph names to
   cp1255, per-span fonts, two-column reading order), caching decoded pages in
   `work/dec/<idx>.jsonl.gz`. The cache is rebuilt whenever `kskdec.py` changes.
   Writes `out_pdf/<key>.txt`, `out_pdf/names.json` and `out_pdf/report.json`.
2. `qa_pdf.py [key ...]`: structural QA against the old files and the validator;
   writes `out_pdf/qa.json`.

`pdfdecode.py` and `runpdf.py <idx>` are the first, simpler PDF decoder. They
dump raw decoded pages to `pdfdec/` for inspection, and `convert_pdf.py` does not
use them.

## Installing the output

Copy `out/<idx>.txt` / `out_pdf/<key>.txt` to
`KSK/ספרים/אוצריא/תלמוד בבלי/ראשונים/קובץ שיטות קמאי/סדר <seder>/<name>.txt`,
using the name from the matching `names.json` (Menachot is in `סדר קדשים`).
The metadata registries key on that name: `metadata.json` (author),
`ForDB/all_metadata.json` and `all_metadata*.json` (Sourcefolder `KSK`; the
`file_path` in `all_metadata_with_file_paths.json` is library-relative with `\`),
`SourcesBooks.csv` (`אוצריא/...` path, source `KSK`) and `ForDB/book_info.csv`
(`ראשונים`).

## Single-rishon books (`split_rishonim.py`)

Nine books, each holding the passages of one rishon on one tractate, are split
out of the packaged tractates by `split_rishonim.py`, driven by
`split_rishonim_config.json` (one entry per book: `title`, `author`, repo-relative
`source` tractate and `output` path, and the `<h3>` `labels` that belong to it).
They were first produced from the pre-2026 edition by the old `split_2.py` /
`split_3.py` scripts, packaged under `MoreBooks/`, and removed from the library
in June 2026 together with the rest of KSK. The config recreates them with their
old file names and at their old paths (under the KSK root instead of
`MoreBooks/`); the book titles, author names and paths are listed there and not
repeated here.

```
python3 split_rishonim.py                # (re)write the nine books
python3 split_rishonim.py --check        # compare with the files on disk
python3 split_rishonim.py --report       # matched / variant / excluded labels
python3 split_rishonim.py --linemap F    # JSON line map of every output line
```

(`--mask` prints `*` for Hebrew letters.) The rule is the old one: after an
`<h3>` whose label is listed for the book, every line up to the next `<h3>` is
copied, under the `<h2>` of its amud (a passage may continue across an amud
boundary, and an `<h2>` is written only if something is copied under it). The
output keeps the `<h2>` amud headings, drops the `<h3>` labels, and starts with
`<h1>title</h1>`, the author line and the copyright line. Two fixes over the
old scripts: the source author and copyright lines (before the first `<h3>`)
are never copied, and labels are compared
after `normalize_label` (niqqud, quote marks and dashes removed), with a second,
looser key without vav/yod reported as a `variant`, so that spelling variants
are found. Labels that resemble a book's labels but are not listed are reported
as `excluded` (for example the same rishon quoted on another tractate).

Label modes: `primary` copies the passage only; `sublabel` first copies the
label as a plain line (used for a second work of the same author inside one
book, as the old edition of that book did).

The line map is `{title: {"output", "source", "lines": [[out_line, source file
name, source_line, kind], ...]}}`, 1-based, `kind` = `heading` (an `<h2>`, or a
`sublabel` label taken from its `<h3>`) or `content`. Lines 1-3 (title,
author and copyright notice) have no source line and are not listed.

After re-running, update the registries if an output path or line count
changed: `SourcesBooks.csv` (line count), and for a new book also
`metadata.json` (author), `all_metadata*.json`, `ForDB/all_metadata.json` and
`ForDB/book_info.csv`, like the tractates above.
