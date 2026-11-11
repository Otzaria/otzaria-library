#!/usr/bin/env python3
"""One-shot, exact-input metadata patch for reviewer comment on PR #1054.

Run only against the pinned parent commit. No book texts, filenames, links or
release inputs are changed. This script and its workflow remove themselves
in the final commit. Fail closed on mismatches before writing any file.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "a40f52ea8ad93920a13072f64b196fd10f5a5a6f"
assert os.environ.get("EXPECTED_BASE_SHA") == BASE
EVEN_AUTHOR = "רבי בנימין עוזר הכהן"
AGRA_OLD = "רבי צבי אלימלך שפירא מדינוב"
AGRA_NEW = "רבי צבי אלימלך שפירא מדינוב [בעל ה'בני יששכר']"
OLD_DESC = {
    "אבני מילואים": "שאלות ותשובות בהלכה מאת רבי אריה לייב הכהן הלר [בעל הקצות].",
    "אבני מילואים א - ב": "חיבור 'אבני מילואים' על שולחן ערוך אבן העזר, בשני חלקים, מאת רבי אריה לייב הכהן הלר [בעל הקצות].",
}
NEW_DESC = {
    "אבני מילואים": "שאלות ותשובות בהלכה.",
    "אבני מילואים א - ב": "ביאור על שולחן ערוך אבן העזר, בשני חלקים.",
}
BOOK = "ForDB/book_info.csv"
IDENTITY = "ForDB/book_info_identity.json"
DESCS = "ForDB/sefaria_metadata_changes.csv"
LOCKS = ".github/data/locked_metadata.tsv"
META = "metadata.json"
PATHS = (BOOK, IDENTITY, DESCS, LOCKS, META)
original = {}
updated = {}


def verify(condition, message):
    if not condition:
        raise ValueError(message)


def csv_line(line):
    try:
        rows = list(csv.reader([line], strict=True))
    except csv.Error as error:
        raise ValueError(f"CSV parse failure: {line[:90]!r}") from error
    verify(len(rows) == 1 and len(rows[0]) == 6, f"Unexpected CSV row: {line[:90]!r}")
    verify(emit_csv(rows[0]) == line, f"Noncanonical CSV row: {line[:90]!r}")
    return rows[0]


def emit_csv(row):
    output = io.StringIO(newline="")
    csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(row)
    return output.getvalue()[:-1]


for path in PATHS:
    raw = (ROOT / path).read_bytes()
    verify(b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf"), f"Unexpected encoding: {path}")
    contents = raw.decode("utf-8")
    verify(contents.endswith("\n"), f"Missing LF terminator: {path}")
    original[path] = contents

# Book-info: preserve original chronological and generation values except the
# incorrect 'ראשוני הראשונים' subgeneration on the 1270 Ramban record.
lines = original[BOOK].split("\n")
verify(lines[0] == "bookName,authorName,generationName,subGenerationName,startYear,endYear", "book_info header changed")
even = set()
renames = []
counts = {"even": 0, "agra": 0, "ramban": 0}
for i, line in enumerate(lines[1:], 1):
    if not (line.startswith('"אבן העוזר על ') or
            line.startswith('"אגרא דפרקא",') or
            line.startswith('"דרשת הרמבן (תורת ה')):
        continue
    row = csv_line(line)
    title, author, gen, sub, birth, death = row
    if title.startswith("אבן העוזר על "):
        verify(title not in even and gen == "אחרונים" and sub == "" and birth == "", f"Unexpected Even title/era: {title}")
        even.add(title)
        if author == "":
            verify(death == "", f"Unexpected Even death year: {title}")
            row[1], row[5] = EVEN_AUTHOR, "1710"
            renames.append((title, "", EVEN_AUTHOR))
            counts["even"] += 1
        else:
            verify(author == EVEN_AUTHOR and death == "1710", f"Unexpected prefilled Even row: {title}")
    elif title == "אגרא דפרקא":
        verify((author, gen, sub, birth, death) == (AGRA_OLD, "אחרונים", "", "1783", "1841"), "Agra book-info unexpectedly changed")
        row[1] = AGRA_NEW
        renames.append((title, AGRA_OLD, AGRA_NEW))
        counts["agra"] += 1
    elif title == "דרשת הרמבן (תורת ה' תמימה)":
        verify((gen, sub, birth, death) == ("ראשונים", "ראשוני הראשונים", "1194", "1270"), "Ramban book-info unexpectedly changed")
        row[3] = ""
        counts["ramban"] += 1
    else:
        raise ValueError(f"Unexpected book-info title: {title}")
    lines[i] = emit_csv(row)
verify(len(even) == 17 and counts == {"even": 16, "agra": 1, "ramban": 1}, f"Unexpected book-info counts: {counts}")
updated[BOOK] = "\n".join(lines)
keys = set()
for line in lines[1:]:
    if not line:
        continue
    row = csv_line(line)
    key = (row[0], row[1])
    verify(key not in keys, f"Duplicate book-info identity: {key}")
    keys.add(key)
verify(all((title, EVEN_AUTHOR) in keys for title in even), "Even HaOzer not complete")
verify(("אגרא דפרקא", AGRA_NEW) in keys, "Agra identity missing")

# Description CSV: it contains multi-line quoted fields elsewhere; edit only
# the 19 complete physical lines which exactly match our targeted records.
lines = original[DESCS].split("\n")
verify(lines[0] == '"categoryPath","title","author","heShortDesc","heDesc","heDescNew"', "Description CSV header changed")
sc = {"even_seen": 0, "even_fixed": 0, "agra": 0, "avnei": 0}
for i, line in enumerate(lines[1:], 1):
    category = (
        "even" if line.startswith('"תלמוד בבלי/אחרונים/אבן העוזר","אבן העוזר על ')
        else "avnei" if (line.startswith('"שו״ת/אחרונים","אבני מילואים",') or
                         line.startswith('"הלכה/שולחן ערוך/מפרשים","אבני מילואים א - ב",'))
        else "agra" if line.startswith('"חסידות/ספרי חסידות נוספים","אגרא דפרקא",')
        else None
    )
    if not category:
        continue
    row = csv_line(line)
    if category == "even":
        verify(row[1] in even, f"Unexpected Even description: {row[1]}")
        sc["even_seen"] += 1
        if row[2] != EVEN_AUTHOR:
            verify(row[2] == "בנימין עוזר הכהן", f"Unexpected Even description author: {row[1]}")
            row[2] = EVEN_AUTHOR
            sc["even_fixed"] += 1
    elif category == "agra":
        verify(row[1] == "אגרא דפרקא" and row[2] == AGRA_OLD, "Unexpected Agra description author")
        row[2] = AGRA_NEW
        sc["agra"] += 1
    else:
        verify(row[1] in OLD_DESC and row[3] == OLD_DESC[row[1]] and row[4] == "" and row[5] == OLD_DESC[row[1]], f"Unexpected Avnei description: {row[1]}")
        row[3], row[5] = NEW_DESC[row[1]], NEW_DESC[row[1]]
        sc["avnei"] += 1
    lines[i] = emit_csv(row)
verify(sc == {"even_seen": 17, "even_fixed": 16, "agra": 1, "avnei": 2}, f"Description counts wrong: {sc}")
updated[DESCS] = "\n".join(lines)

# Exact metadata locks must be updated in the same commit as their values.
lines = original[LOCKS].split("\n")
verify(lines[0] == "kind\tkey\tvalue\tnote", "Locked metadata schema changed")
lock_changes = {("author", "אגרא דפרקא"): (AGRA_OLD, AGRA_NEW)}
for title in OLD_DESC:
    for kind in ("sefaria_short", "sefaria_long"):
        lock_changes[(kind, title)] = (OLD_DESC[title], NEW_DESC[title])
found = set()
even_locks = set()
for i, line in enumerate(lines[1:], 1):
    parts = line.split("\t")
    if len(parts) == 4 and parts[0] == "author" and parts[1].startswith("אבן העוזר על "):
        verify(parts[1] in even and parts[2] == EVEN_AUTHOR and parts[1] not in even_locks, f"Even author lock mismatch: {parts[1]}")
        even_locks.add(parts[1])
    if len(parts) < 2:
        continue
    key = (parts[0], parts[1])
    if key in lock_changes:
        verify(len(parts) == 4 and key not in found, f"Duplicate metadata lock: {key}")
        before, after = lock_changes[key]
        verify(parts[2] == before, f"Unexpected metadata lock: {key}")
        parts[2] = after
        lines[i] = "\t".join(parts)
        found.add(key)
verify(len(even_locks) == 17 and found == set(lock_changes), "Required locks missing")
updated[LOCKS] = "\n".join(lines)

# metadata.json is an array of compact one-object-per-line JSON records.
# Changing the single Agra author field propagates to the DB without editing
# the (locked) second line of the packaged text file or any manifest hashes.
lines = original[META].split("\n")
meta_edits = 0
for i, line in enumerate(lines):
    if not line.startswith('{"title":"אגרא דפרקא","author":'):
        continue
    record = json.loads(line[:-1] if line.endswith(",") else line)
    verify(record["title"] == "אגרא דפרקא" and record["author"] == AGRA_OLD, "Unexpected catalog row")
    target = '"author":' + json.dumps(AGRA_OLD, ensure_ascii=False)
    verify(line.count(target) == 1, "Agra metadata author not unique")
    lines[i] = line.replace(target, '"author":' + json.dumps(AGRA_NEW, ensure_ascii=False))
    meta_edits += 1
verify(meta_edits == 1, "Expected one Agra catalog metadata record")
updated[META] = "\n".join(lines)
verify(sum(x.get("title") == "אגרא דפרקא" and x.get("author") == AGRA_NEW
           for x in json.loads(updated[META])) == 1, "Agra catalog JSON validation failed")

# Append exact old->new (book,author) identity renames. The site consumes
# this journal to follow pending edits; never rewrite the existing prefix.
ledger = json.loads(original[IDENTITY])
verify(ledger.get("schemaVersion") == 1 and isinstance(ledger.get("events"), list), "Unexpected identity schema")
verify(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n" == original[IDENTITY], "Identity format changed")
events = ledger["events"]
for i, event in enumerate(events, 1):
    verify(event["id"] == i, "Identity event history not sequential")
prior = len(events)
verify(len(renames) == 17 and prior == 6279, "Unexpected identity event count")
for title, old_author, new_author in renames:
    verify((title, old_author) not in keys and (title, new_author) in keys, f"Identity not reflected in catalog: {title}")
    verify(not any(event["kind"] == "rename" and
                   event["old"] == {"bookName": title, "authorName": old_author} and
                   event["new"] == {"bookName": title, "authorName": new_author} for event in events),
           f"Identity event already recorded: {title}")
    events.append({
        "id": len(events) + 1,
        "kind": "rename",
        "old": {"bookName": title, "authorName": old_author},
        "new": {"bookName": title, "authorName": new_author},
        "commit": BASE,
    })
verify(len(events) == prior + 17 and events[-1]["id"] == 6296, "Identity append mismatch")
updated[IDENTITY] = json.dumps(ledger, ensure_ascii=False, indent=2) + "\n"

# No writes until every precondition and the complete cross-file plan passes.
verify(set(updated) == set(PATHS), "Missing expected file changes")
for path in PATHS:
    verify(updated[path] != original[path] and updated[path].endswith("\n") and "\r" not in updated[path],
           f"Unexpected output encoding/change for {path}")
for path in PATHS:
    (ROOT / path).write_bytes(updated[path].encode("utf-8"))
print("Successfully updated exactly five files: 17 Even HaOzer volumes; Agra with author alias; "
      "two Avnei Miluim descriptions and four locks; Ramban subgeneration; 17 append-only identity events.")
