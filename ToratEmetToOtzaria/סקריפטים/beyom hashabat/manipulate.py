#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert Torat Emet's 410_beyom_hashabat.txt to Otzaria format."""

from __future__ import annotations
import argparse, html, json, re, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BOOK_TITLE = "וביום השבת"
DEFAULT_INPUT = "410_beyom_hashabat.txt"
DEFAULT_MAIN = f"{BOOK_TITLE}.txt"
DEFAULT_NOTES = f"הערות על {BOOK_TITLE}.txt"
DEFAULT_LINKS = f"{BOOK_TITLE}_links.json"

HEADING_MARKERS = {"$": "h1", "@": "h2", "~": "h3"}
XX_GG_RE = re.compile(r"XX(.*?)GG", flags=re.DOTALL)
FOOTNOTE_RE = re.compile(r"\[\[\[\s*(.*?)\s*\]\]\]\s*\{\{(.*?)\}\}", flags=re.DOTALL)
FOOTNOTE_DOUBLE_RE = re.compile(r"\[\[(\*)\]\]\s*\{\{(.*?)\}\}", flags=re.DOTALL)
BOLD_RE = re.compile(r"\[\[(?!\[)(.*?)\]\]", flags=re.DOTALL)
BIG_RE = re.compile(r"\{\{\{(.*?)\}\}\}", flags=re.DOTALL)
BR_RE = re.compile(r"<\s*BR\s*/?\s*>", flags=re.IGNORECASE)

@dataclass(frozen=True)
class Footnote:
    marker: str
    body: str
    base_line: int
    note_line: int

def normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")

def collapse_internal_newlines(text):
    text = normalize_newlines(text)
    return re.sub(r"\s*\n\s*", "<br>", text)

def normalize_marker(marker):
    marker = collapse_internal_newlines(marker).strip()
    marker = re.sub(r"<[^>]+>", "", marker)
    marker = html.unescape(marker).strip()
    if not marker:
        raise ValueError("נמצאה הערה עם סימן הפניה ריק")
    return marker

def convert_lists(text):
    out, pos = [], 0
    for m in re.compile(r"BB(.*?)EE", re.DOTALL).finditer(text):
        out.append(text[pos:m.start()])
        inner = BR_RE.sub("\n", normalize_newlines(m.group(1)))
        items = [x.strip() for x in inner.split("\n") if x.strip()]
        if items:
            out.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)

def sanitize_note_body(body):
    body = normalize_newlines(body)
    body = convert_lists(body)
    body = BR_RE.sub("<br>", body)
    body = collapse_internal_newlines(body).strip()
    body = BIG_RE.sub(lambda m: f"<big>{m.group(1).strip()}</big>", body)
    body = BOLD_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>", body)
    body = re.sub(r"</?\s*i\b[^>]*>", "", body, flags=re.IGNORECASE)
    body = re.sub(r"</?\s*h[1-6]\b[^>]*>", "", body, flags=re.IGNORECASE)
    body = body.replace("RRR", "")
    body = re.sub(r"\s*<br>\s*", "<br>", body)
    return body.strip()

def convert_inline_markup(text):
    text = BR_RE.sub("<br>", text)
    text = BIG_RE.sub(lambda m: f"<big>{m.group(1).strip()}</big>", text)
    text = BOLD_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>", text)
    return text.replace("RRR", "")

def convert_heading(line):
    stripped = line.lstrip()
    leading = line[:len(line)-len(stripped)]
    if not stripped:
        return line
    tag = HEADING_MARKERS.get(stripped[0])
    if not tag:
        return line
    return f"{leading}<{tag}>{stripped[1:].strip()}</{tag}>"

def protect_footnotes(text):
    protected, counter = {}, 0
    def repl(m):
        nonlocal counter
        counter += 1
        token = f"\uFFF0OTZFN{counter}\uFFF1"
        marker = normalize_marker(m.group(1))
        body = sanitize_note_body(m.group(2))
        if not body:
            raise ValueError(f"הערה {marker!r} ריקה")
        protected[token] = (marker, body)
        return token
    text = FOOTNOTE_RE.sub(repl, text)
    text = FOOTNOTE_DOUBLE_RE.sub(repl, text)
    return text, protected

def source_to_logical_lines(text):
    text = normalize_newlines(text)
    text = XX_GG_RE.sub(lambda m: m.group(1), text)
    text, protected = protect_footnotes(text)
    text = convert_lists(text)
    return text.split("\n"), protected

def resolve_note_placeholders(line, protected, base_line_no, note_count_before):
    notes = []
    def repl(m):
        token = m.group(0)
        marker, body = protected[token]
        note_line = note_count_before + len(notes) + 1
        notes.append(Footnote(marker=marker, body=body, base_line=base_line_no, note_line=note_line))
        return f"<sup>{html.escape(marker)}</sup>"
    return re.compile(r"\uFFF0OTZFN(\d+)\uFFF1").sub(repl, line), notes

def convert_book(text):
    logical_lines, protected = source_to_logical_lines(text)
    main_lines, all_notes = [], []
    for src_line in logical_lines:
        line = convert_heading(src_line)
        base_line_no = len(main_lines) + 1
        line, notes = resolve_note_placeholders(line, protected, base_line_no, len(all_notes))
        all_notes.extend(notes)
        line = convert_inline_markup(line)
        line = collapse_internal_newlines(line)
        main_lines.append(line.rstrip())
    while main_lines and main_lines[-1] == "":
        main_lines.pop()
    return main_lines, all_notes

def build_links(notes, notes_filename):
    return [{"line_index_1": n.base_line, "heRef_2": "הערות", "path_2": notes_filename,
             "line_index_2": n.note_line, "Conection Type": "footnotes"} for n in notes]

def validate_main(lines):
    errors = []
    if not lines: return ["קובץ הספר ריק"]
    if not re.fullmatch(r"\s*<h1>.+?</h1>\s*", lines[0]):
        errors.append("שורה 1 אינה <h1>")
    for i, line in enumerate(lines, 1):
        if "RRR" in line: errors.append(f"שורה {i}: נשאר RRR")
        if "BB" in line or "EE" in line: errors.append(f"שורה {i}: נשאר BB/EE")
        if re.search(r"\[\[\[|\]\]\]|\{\{\{|\}\}\}", line): errors.append(f"שורה {i}: נשאר סימון מקור")
        if re.match(r"\s*<h[1-6]\b", line, re.I):
            if not re.fullmatch(r"\s*<h([1-6])\b[^>]*>.*?</h\1>\s*", line, re.I):
                errors.append(f"שורה {i}: כותרת לא תקינה")
    return errors

def validate_notes(notes):
    errors = []
    for n in notes:
        if re.search(r"</?\s*i\b", n.body, re.I): errors.append(f"הערה {n.note_line}: מכילה <i>")
        if re.match(r"\s*<h[1-6]\b", n.body, re.I): errors.append(f"הערה {n.note_line}: היא כותרת")
        if not n.body.strip(): errors.append(f"הערה {n.note_line}: ריקה")
    return errors

def validate_links(links, main_lines, notes):
    errors = []
    if len(links) != len(notes): errors.append("מספר קישורים != מספר הערות")
    for idx, link in enumerate(links, 1):
        if not (1 <= link["line_index_1"] <= len(main_lines)): errors.append(f"קישור {idx}: line_index_1 מחוץ לטווח")
        if not (1 <= link["line_index_2"] <= len(notes)): errors.append(f"קישור {idx}: line_index_2 מחוץ לטווח")
        if "ref_2" in link: errors.append(f"קישור {idx}: ref_2 אסור")
    return errors

def find_suspicious_source_leftovers(lines):
    warnings = []
    for i, line in enumerate(lines, 1):
        for pat, label in [(r"\[\[\[", "[[["), (r"\]\]\]", "]]]"),
                           (r"(?<!\w)XX(?!\w)", "XX"), (r"(?<!\w)GG(?!\w)", "GG"), (r"\bRRR\b", "RRR")]:
            if re.search(pat, line): warnings.append(f"שורה {i}: נשאר {label}")
    return warnings

def write_utf8_lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT)
    parser.add_argument("--books-dir", default=".")
    parser.add_argument("--links-dir", default=".")
    parser.add_argument("--strict-source", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"ERROR: not found: {input_path}", file=sys.stderr)
        return 2

    raw = input_path.read_text(encoding="utf-8-sig")
    main_lines, notes = convert_book(raw)
    links = build_links(notes, DEFAULT_NOTES)

    errors = []
    errors.extend(validate_main(main_lines))
    errors.extend(validate_notes(notes))
    errors.extend(validate_links(links, main_lines, notes))
    warnings = find_suspicious_source_leftovers(main_lines)

    if args.strict_source and warnings:
        errors.extend("STRICT: " + w for w in warnings)

    if errors:
        print("FAILED")
        for e in errors: print("  -", e)
        return 1

    if not args.check_only:
        write_utf8_lf(Path(args.books_dir) / DEFAULT_MAIN, "\n".join(main_lines) + "\n")
        write_utf8_lf(Path(args.books_dir) / DEFAULT_NOTES, "\n".join(n.body for n in notes) + ("\n" if notes else ""))
        write_utf8_lf(Path(args.links_dir) / DEFAULT_LINKS, json.dumps(links, ensure_ascii=False, indent=2) + "\n")
        print("OK")
        print(f"  base:  {len(main_lines):,} lines")
        print(f"  notes: {len(notes):,}")
        print(f"  links: {len(links):,}")
    else:
        print("OK (check-only)")
        print(f"  base lines: {len(main_lines):,}")
        print(f"  notes: {len(notes):,}")

    if warnings:
        print("WARNINGS")
        for w in warnings[:20]: print("  -", w)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
