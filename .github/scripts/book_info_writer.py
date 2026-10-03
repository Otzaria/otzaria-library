"""Canonical additive registration for packaged books, shared by every importer.

Existing (bookName, authorName) rows are authoritative, including blank values.
Registration never replaces their generation, subgeneration or years. Missing
book_info is an error: creating an empty source would hide the legacy catalogue.
"""
import csv
import io
import os
import tempfile
from collections import Counter
from pathlib import Path

from fordb_book_renames import _split_bom, _csv_value, csv_records, EditVerificationError
from book_info_contract import HEADER, GENERATIONS, validate_book_info


def encode_rows(rows):
    out = io.StringIO(newline='')
    csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator='\n').writerows(rows)
    return out.getvalue()


def plan_registration(repo, entries, *, legacy_compat=True):
    """Return {relative path: bytes} after validating all CSVs, without writing.

    entries contain all six supported fields. New distinct coauthors are added;
    a blank-author fallback never creates an extra row for an attributed book.
    During PR55 only, existing legacy generations is updated from the canonical
    new source (majority generation, first sorted author tie), never conversely.
    """
    path = Path(repo) / 'ForDB/book_info.csv'
    data = path.read_bytes()
    parsed = validate_book_info(data)
    bom, text = _split_bom(data)
    try:
        tokens = csv_records(text)
    except EditVerificationError as error:
        raise ValueError(str(error)) from error
    if not parsed or parsed[0] != HEADER:
        raise ValueError(f'{path}: expected supported six-column header')
    rows = [r for r in parsed[1:] if r]
    if any(len(r) != len(HEADER) for r in rows):
        raise ValueError(f'{path}: wrong record width')
    if len({tuple(r[:2]) for r in rows}) != len(rows):
        raise ValueError(f'{path}: duplicate book/author identity')
    # Preserve original record bytes, including quoted linebreaks and years.
    original = {tuple(_csv_value(text, f) for f in fields[:2]): text[start:end]
                for start, end, fields in tokens[1:] if len(fields) == len(HEADER)}
    identities = {tuple(r[:2]) for r in rows}
    titles = {r[0] for r in rows}
    requested_titles = set()
    for entry in entries:
        row = list(entry)
        if len(row) != len(HEADER) or not all(isinstance(v, str) for v in row) or not row[0]:
            raise ValueError('Registration requires six string fields and a book title')
        if row[2] not in GENERATIONS:
            raise ValueError(f'Unsupported generation: {row[2]}')
        requested_titles.add(row[0])
        identity = tuple(row[:2])
        if identity in identities or (not row[1] and row[0] in titles):
            continue
        rows.append(row)
        identities.add(identity)
        titles.add(row[0])
    rows.sort(key=lambda r: (r[0], r[1]))
    # A terminal newline is required between records when appending to old files.
    pieces = [bom, text[tokens[0][0]:tokens[0][1]].rstrip('\r\n'), '\n']
    for row in rows:
        token = original.get(tuple(row[:2]), encode_rows([row]))
        pieces.extend([token.rstrip('\r\n'), '\n'])
    writes = {}
    encoded = ''.join(pieces).encode('utf-8')
    validate_book_info(encoded)
    if encoded != data:
        writes['ForDB/book_info.csv'] = encoded
    legacy = Path(repo) / 'ForDB/generations.csv'
    if legacy_compat and legacy.exists():
        old_data = legacy.read_bytes()
        old_bom, old_text = _split_bom(old_data)
        csv_records(old_text)
        generations = list(csv.reader(io.StringIO(old_text, newline=''), strict=True))
        if not generations or generations[0] != ['שם ספר', 'קבוצת דור'] or any(r and len(r) != 2 for r in generations[1:]):
            raise ValueError(f'{legacy}: invalid legacy table')
        grouped = {}
        for row in rows:
            if row[2]:
                grouped.setdefault(row[0], []).append(row[2])
        legacy_by_title = {}
        for row in generations[1:]:
            if row:
                legacy_by_title.setdefault(row[0], []).append(row)
        for title in sorted(requested_titles):
            candidates = grouped.get(title, [])
            if not candidates:
                continue
            counts = Counter(candidates)
            gen = max(candidates, key=counts.get)
            hits = legacy_by_title.get(title, [])
            if hits:
                for row in hits:
                    row[1] = gen
            else:
                generations.append([title, gen])
        out = io.StringIO(newline='')
        csv.writer(out, lineterminator='\n').writerows(generations)
        encoded = (old_bom + out.getvalue()).encode('utf-8')
        if encoded != old_data:
            writes['ForDB/generations.csv'] = encoded
    return writes


def apply_registration(repo, writes):
    """Atomically replace each already validated registry and return touched paths."""
    for relative, data in writes.items():
        destination = Path(repo) / relative
        fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix='.book-info-')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return list(writes)
