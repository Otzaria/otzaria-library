import json
import os
import csv
import re


def sanitize_filename(filename: str) -> str:
    sanitized_filename = re.sub(r'[\\/:*"?<>|]', "", filename)
    sanitized_filename = sanitized_filename.replace("_", " ")
    return sanitized_filename.strip()


# Line 2 of an Otzaria book is the author, but only when the book actually opens with
# the <h1> title line — and even then the author line may simply be absent, leaving the
# book's first content line in its place. Taking content[1] unconditionally is what made
# "(א) מטור" the author of שער הציון (no <h1> at all) and "(א) בפ\"ג מה' ציצית הלכה ז':"
# the author of הערות על שות רבי משולם איגרא (<h1>, no author line).
#
# The job here is only to reject lines that are structurally *content*, not to validate
# author names: plenty of legitimate author lines carry inline markup
# ("<b>רבי יעקב בן יעקב משה לורברבוים מליסא</b>") or a wrapped/BOM-prefixed title above
# them ("<u><h1>משמרות כהונה חלק א</h1></u>"), and those must keep working.
_H1_LINE = re.compile(r"^(?:<[a-zA-Z][^>]*>\s*)*<h1[\s>]", re.IGNORECASE)
# a few books head themselves with <h3> instead of <h1> (פנים מאירות על זבחים); accept
# any heading whose text *is* the book title, which a content heading never is
_ANY_HEADING = re.compile(r"^(?:<[a-zA-Z][^>]*>\s*)*<h[1-6][\s>](.*?)</h[1-6]>",
                          re.IGNORECASE | re.DOTALL)
# a heading, a footnote marker or a line break opens content, never an author
_CONTENT_LINE = re.compile(r"^<(?:h[1-6]|sup|br)\b", re.IGNORECASE)
# "(א) ..." / "1 ..." — the note markers of the הערות-על-X books
_NOTE_MARKER = re.compile(r"^(?:[0-9]|\([^)]{1,4}\))")
_INLINE_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


def _is_title_line(line: str, title: str | None) -> bool:
    """True when line 1 is the book's title line rather than its first content line."""
    if _H1_LINE.match(line):
        return True
    m = _ANY_HEADING.match(line)
    return bool(m and title and _INLINE_TAG.sub("", m.group(1)).strip() == title.strip())


def extract_author(content: list[str], title: str | None = None) -> str | None:
    """content = the file's lines, title = the book's title (used to recognise a
    non-<h1> title line). Returns the author from line 2 with any inline markup
    stripped, or None when the book carries no author line."""
    if len(content) < 2:
        return None
    if not _is_title_line(content[0].lstrip("\ufeff").strip(), title):
        return None
    line = content[1].lstrip("\ufeff").strip()
    if _CONTENT_LINE.match(line) or _NOTE_MARKER.match(line):
        return None
    author = _INLINE_TAG.sub("", line).strip()
    if not author or author.endswith(":") or "\u00a9" in author or _NOTE_MARKER.match(author):
        return None
    return author


def new_sefaria_metadata(list_of_files: list):
    meta_file_path = ""
    root_folder = ""
    list_new = []
    new_data = []
    for _, _, files in os.walk(root_folder):
        list_new.extend([os.path.splitext(file)[0] for file in files if os.path.splitext(file)[1] == ".txt" and os.path.splitext(file)[0] not in list_of_files])
    with open(meta_file_path, "r") as f:
        data = json.load(f)
    for entry in data:
        if sanitize_filename(entry["he_title"]) in list_new:
            new_entry = {"title": sanitize_filename(entry["he_title"]), "authors": entry["authors"], "heShortDesc": entry["he_short_desc"], "heDesc": entry["he_long_desc"]}
            new_data.append(new_entry)
    return new_data


new_files_data = []
file_path = "/home/zevi5/Downloads/otzaria-library/metadata.json"
root_folder = "/home/zevi5/Downloads/otzaria-library/אוצריא"
files_list = {}
folders_list = []
folders = (
    "Ben-YehudaToOtzaria/ספרים/אוצריא",
    "DictaToOtzaria/ספרים/ערוך/אוצריא",
    "OnYourWayToOtzaria/ספרים/אוצריא",
    "OraytaToOtzaria/ספרים/אוצריא",
    "sefariaToOtzaria/ספרים/אוצריא",
    "sefaria and more",
    "MoreBooks"
)
mapping = {
    "Ben-YehudaToOtzaria": "Ben-Yehuda",
    "DictaToOtzaria": "Dicta",
    "OnYourWayToOtzaria": "OnYourWay",
    "OraytaToOtzaria": "Orayta",
    "sefaria and more": "sefaria",
    "sefariaToOtzaria": "sefaria_new",
    "MoreBooks": "MoreBooks"
}
for root, dirs, files in os.walk(root_folder):
    for file in files:
        files_list[os.path.splitext(file)[0]] = os.path.join(root, file)
    folders_list.extend(list(dirs))

with open(file_path, "r") as f:
    data = json.load(f)
all_titles = [entry["title"] for entry in data]
for key, value in files_list.items():
    if key not in all_titles:
        if os.path.splitext(value)[1] != ".txt":
            continue
        new_entry = {"title": key}
        with open(value, "r", encoding="utf-8") as f:
            content = f.read().split("\n")
            if len(content) < 2:
                continue
            new_entry["author"] = extract_author(content, key)
        new_files_data.append(new_entry)
new_folders_data = [folder for folder in folders_list if folder not in all_titles]
with open("new.csv", "w", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["title", "author"])
    writer.writeheader()
    writer.writerows(new_files_data)
    writer.writerows([{"title": folder} for folder in new_folders_data])
