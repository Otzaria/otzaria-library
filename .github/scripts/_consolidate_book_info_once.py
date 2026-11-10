#!/usr/bin/env python3
"""One-time consolidation of 18 reviewed website book-info PRs.

Run from the repository root. Never rewrite the existing book files or titles.
Updates the canonical catalog, generated mirrors, description overrides and
locks together. The change-set IDs preserve the website's revision provenance.
"""
import csv
import io
import json
import re
from pathlib import Path

CHANGES = [
    (947, "אורחות צדיקים", "אחד מחכמי אשכנז", "ראשונים", "אחרוני הראשונים", "", "", "6af0fd7e83a61cf29bdbad1a"),
    (798, "אגרא דפרקא", "רבי צבי אלימלך שפירא מדינוב", "אחרונים", "", "1783", "1841", "6aeb9e25b29cb6b885e32133"),
    (779, "אגלי טל", "רבי אברהם בורנשטיין מסוכטשוב", "אחרונים", "", "1838", "1910", "6aeb3cebb29cb6b885e2f5dd"),
    (946, "אחיעזר חלק ג", "רבי חיים עוזר גרודזינסקי", "אחרונים", "אחרוני האחרונים", "1863", "1940", "6af0fc4783a61cf29bdbac7b"),
    (956, "בלבבי משכן אבנה - ו", "הרב איתמר שוורץ", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1003e83a61cf29bdbb059"),
    (955, "בלבבי משכן אבנה - ט", "הרב איתמר שוורץ [מהקלטות]", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1002f83a61cf29bdbb058"),
    (954, "בלבבי משכן אבנה - ד", "הרב איתמר שוורץ", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1002083a61cf29bdbb04a"),
    (953, "בלבבי משכן אבנה - ג", "הרב איתמר שוורץ", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1001183a61cf29bdbb036"),
    (950, "בית הלוי חלק ג", "רבי יוסף דוב הלוי סולובייצ'יק מבריסק", "אחרונים", "אחרוני האחרונים", "1820", "1892", "6af0ff3283a61cf29bdbaeac"),
    (949, "בית הלוי חלק ב", "רבי יוסף דוב הלוי סולובייצ'יק מבריסק", "אחרונים", "אחרוני האחרונים", "1820", "1892", "6af0ff2483a61cf29bdbae9f"),
    (948, "בית הלוי חלק א", "רבי יוסף דוב הלוי סולובייצ'יק מבריסק", "אחרונים", "אחרוני האחרונים", "1820", "1892", "6af0fefa83a61cf29bdbae73"),
    (957, "בלבבי משכן אבנה - ב", "הרב איתמר שוורץ", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1004d83a61cf29bdbb068"),
    (952, "בלבבי משכן אבנה - א", "הרב איתמר שוורץ", "מחברי זמננו", "מחברי זמננו", "", "2026", "6af1000083a61cf29bdbb01d"),
    (778, "אבני מילואים א - ב", "רבי אריה לייב הכהן הלר [בעל הקצות]", "אחרונים", "", "1745", "1812", "6aeb3c9bb29cb6b885e2f5cc"),
    (951, "בית הלוי על מצות הביטחון", "רבי יוסף דוב הלוי סולובייצ'יק מבריסק", "אחרונים", "אחרוני האחרונים", "1820", "1892", "6af0ff4283a61cf29bdbaec1"),
    (844, "אבן העוזר על בבא בתרא", "רבי בנימין עוזר הכהן", "אחרונים", "", "", "1710", "6aed920b3cbc08d9e57dd298"),
    (803, "דרשת הרמבן (תורת ה' תמימה)", 'רבנו משה ב"ר נחמן [הרמב"ן]', "ראשונים", "ראשוני הראשונים", "1194", "1270", "6aec37a1b29cb6b885e340c0"),
    (802, "ביאור הגרא על תקוני הזהר", 'רבנו אליהו [הגר"א] ב"ר שלמה זלמן מווילנה', "אחרונים", "", "1720", "1797", "6aec3744b29cb6b885e34018"),
]
assert len(CHANGES) == len({x[1] for x in CHANGES}) == 18
BY_TITLE = {x[1]: x for x in CHANGES}

NEW_AUTHORS = {
    **{"בלבבי משכן אבנה - " + n: "הרב איתמר שוורץ" for n in ("א", "ב", "ג", "ד", "ו")},
    "דרשת הרמבן (תורת ה' תמימה)": 'רבנו משה ב"ר נחמן [הרמב"ן]',
}
DESCRIPTIONS = {
    "אבני מילואים": "שאלות ותשובות בהלכה מאת רבי אריה לייב הכהן הלר [בעל הקצות].",
    "אבני מילואים א - ב": "חיבור 'אבני מילואים' על שולחן ערוך אבן העזר, בשני חלקים, מאת רבי אריה לייב הכהן הלר [בעל הקצות].",
}

def read(path):
    return Path(path).read_text(encoding="utf-8")

def put(path, old, new):
    if new == old:
        raise AssertionError(f"Expected a change in {path}")
    if not new.endswith("\n"):
        raise AssertionError(f"Missing trailing LF: {path}")
    Path(path).write_text(new, encoding="utf-8", newline="\n")
    print(f"Changed {path}: {len(new) - len(old):+d} characters")

def csv_records(text):
    """Split CSV into exact raw records, retaining untouched multiline rows."""
    rows = []
    start = 0
    quoted = False
    i = 0
    while i < len(text):
        if text[i] == '"':
            if quoted and i + 1 < len(text) and text[i + 1] == '"':
                i += 1
            else:
                quoted = not quoted
        elif text[i] == "\n" and not quoted:
            rows.append(text[start:i + 1])
            start = i + 1
        i += 1
    assert not quoted and start == len(text), "Malformed CSV source"
    return rows

def parsed(record):
    rows = list(csv.reader(io.StringIO(record, newline=""), strict=True))
    assert len(rows) == 1
    return rows[0]

def encoded(fields):
    out = io.StringIO(newline="")
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(fields)
    return out.getvalue()

def book_info():
    path = "ForDB/book_info.csv"
    original = read(path)
    count = 0
    result = []
    seen = set()
    for i, raw in enumerate(csv_records(original)):
        if i == 0:
            assert parsed(raw) == ["bookName", "authorName", "generationName", "subGenerationName", "startYear", "endYear"]
            result.append(raw)
            continue
        row = parsed(raw)
        assert len(row) == 6
        proposal = BY_TITLE.get(row[0])
        if proposal:
            assert row[1] == "", ("Unexpected prior author", row)
            row = list(proposal[1:7])
            count += 1
            raw = encoded(row)
        elif row[0] == "אבני מילואים":
            assert row[1] == "רבי אריה לייב הכהן הלר [בעל הקצות]" and row[5] == "1933"
            row[5] = "1812"
            raw = encoded(row)
        assert (row[0], row[1]) not in seen, ("Duplicate book/author", row[0], row[1])
        seen.add((row[0], row[1]))
        assert not (row[4] and row[5] and int(row[4]) > int(row[5]))
        result.append(raw)
    assert count == 18, count
    put(path, original, "".join(result))

def identity_ledger():
    path = "ForDB/book_info_identity.json"
    original = read(path)
    doc = json.loads(original)
    assert doc["schemaVersion"] == 1 and len(doc["events"]) == 6261 and doc["events"][-1]["id"] == 6261
    for number, title, author, _gen, _sub, _birth, _death, change_set in CHANGES:
        doc["events"].append({
            "id": len(doc["events"]) + 1, "kind": "rename",
            "old": {"bookName": title, "authorName": ""},
            "new": {"bookName": title, "authorName": author},
            "commit": None, "changeSetId": change_set,
        })
    assert len(doc["events"]) == 6279
    put(path, original, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

def canonical_metadata():
    path = "metadata.json"
    original = read(path)
    lines = original.split("\n")
    updated = set()
    for i, line in enumerate(lines):
        if not line.startswith("{"):
            continue
        comma = line.endswith(",")
        item = json.loads(line[:-1] if comma else line)
        title = item.get("title")
        if title in NEW_AUTHORS:
            assert item.get("author") in (None, NEW_AUTHORS[title]), (title, item.get("author"))
            item["author"] = NEW_AUTHORS[title]
            lines[i] = json.dumps(item, ensure_ascii=False, separators=(",", ":")) + ("," if comma else "")
            updated.add(title)
    out = "\n".join(lines)
    template = {
        "title": "", "author": "", "pubDate": None, "pubPlace": None,
        "compPlace": None, "compDate": None, "תיאור_חדש": None,
        "heShortDesc": None, "heDesc": None, "Unnamed: 9": None, "order": None,
    }
    extras = [
        json.dumps({**template, "title": title, "author": author}, ensure_ascii=False, separators=(",", ":"))
        for title, author in NEW_AUTHORS.items() if title not in updated
    ]
    if extras:
        index = out.rfind("\n]")
        assert index >= 0 and out[:index].endswith("}")
        out = out[:index] + ",\n" + ",\n".join(extras) + out[index:]
    document = json.loads(out)
    for title, author in NEW_AUTHORS.items():
        hits = [item for item in document if item.get("title") == title]
        assert len(hits) == 1 and hits[0]["author"] == author, title
    assert len(updated) == 1 and len(extras) == 5
    put(path, original, out)

def pretty_he_author_changes(original):
    text = original
    found = []
    for title, author in NEW_AUTHORS.items():
        pos = text.find('    "title": ' + json.dumps(title, ensure_ascii=False))
        if pos < 0:
            continue
        start = text.rfind("\n  {\n", 0, pos)
        end = text.find("\n  }", pos) + 4
        assert start >= 0 and end >= 4, title
        fragment = text[start:end]
        assert json.loads(fragment.strip()).get("title") == title
        replacement = '    "heAuthors": [\n      ' + json.dumps(author, ensure_ascii=False) + '\n    ]'
        fragment, n = re.subn(r'    "heAuthors": \[[\s\S]*?\n    \]', lambda _: replacement, fragment, count=1)
        assert n == 1, title
        text = text[:start] + fragment + text[end:]
        found.append(title)
    data = json.loads(text)
    for item in data:
        if item.get("title") in NEW_AUTHORS:
            assert item["heAuthors"] == [NEW_AUTHORS[item["title"]]], item["title"]
    return text, found

def mirror_metadata():
    for path in ("ForDB/all_metadata.json", "all_metadata.json", "all_metadata_with_file_paths.json"):
        original = read(path)
        if path.startswith("ForDB/"):
            data = json.loads(original)
            found = []
            for item in data:
                if item.get("title") in NEW_AUTHORS:
                    assert isinstance(item.get("heAuthors"), list)
                    item["heAuthors"] = [NEW_AUTHORS[item["title"]]]
                    found.append(item["title"])
            out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        else:
            out, found = pretty_he_author_changes(original)
        assert len(found) >= 5, (path, found)
        put(path, original, out)

def book_descriptions():
    path = "ForDB/sefaria_metadata_changes.csv"
    original = read(path)
    modified = []
    descriptive = set()
    result = []
    for i, raw in enumerate(csv_records(original)):
        if i == 0:
            result.append(raw)
            continue
        row = parsed(raw)
        assert len(row) == 6, (i, row)
        proposal = BY_TITLE.get(row[1])
        desc = DESCRIPTIONS.get(row[1])
        if not proposal and not desc:
            result.append(raw)
            continue
        if proposal:
            row[2] = proposal[2]  # Informational author (not seed input)
        if desc:
            row[3] = row[5] = desc  # Short and long must agree
            descriptive.add(row[1])
        modified.append(row[1])
        result.append(encoded(row))
    assert descriptive == set(DESCRIPTIONS) and len(modified) >= 17, modified
    put(path, original, "".join(result))

def metadata_locks():
    path = ".github/data/locked_metadata.tsv"
    original = read(path)
    lines = original.split("\n")
    new_locks = [("author", title, author) for title, author in NEW_AUTHORS.items()]
    for title, description in DESCRIPTIONS.items():
        new_locks += [("sefaria_short", title, description), ("sefaria_long", title, description)]
    for kind, key, value in new_locks:
        assert not any(x.startswith(kind + "\t" + key + "\t") for x in lines), (kind, key)
        where = next((i for i, ln in enumerate(lines) if i > 2 and ln.startswith(kind + "\t") and ln.split("\t")[1] > key), None)
        if where is None:
            last = [i for i, ln in enumerate(lines) if ln.startswith(kind + "\t")]
            assert last, kind
            where = last[-1] + 1
        lines.insert(where, "\t".join((kind, key, value, "PR consolidation 2026-11-11")))
    assert len(new_locks) == 10
    put(path, original, "\n".join(lines))

def main():
    # Only touch the curated list; no book file rename, source line, or stable old lock.
    book_info()
    identity_ledger()
    canonical_metadata()
    mirror_metadata()
    book_descriptions()
    metadata_locks()
    print("PASS: 18 website revisions consolidated, metadata mirrors and locks updated")

if __name__ == "__main__":
    main()
