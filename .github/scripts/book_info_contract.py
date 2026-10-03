"""Storage contract shared with the website's complete book-info CSV reader."""
import csv
import io
import re

from fordb_book_renames import _csv_value, csv_records, EditVerificationError

HEADER = ['bookName', 'authorName', 'generationName', 'subGenerationName', 'startYear', 'endYear']
GENERATIONS = {'', 'תורה שבכתב', 'חז"ל', 'ראשונים', 'אחרונים', 'מחברי זמננו'}
YEAR = re.compile(r'-?[0-9]+\Z')


def validate_book_info(data):
    """Return parsed rows after validating the entire source, before any writes.

    Quoted LF text is supported; CR (including CRLF), BOM and NUL are refused.
    Years are empty or signed Int32 integers. Identity is the exact book+author.
    """
    text = data.decode('utf-8')
    if text.startswith('\ufeff') or '\r' in text or '\0' in text:
        raise ValueError('book_info.csv requires UTF-8 without BOM, LF, and no CR/NUL')
    try:
        records = csv_records(text)
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except (EditVerificationError, csv.Error) as error:
        raise ValueError(f'book_info.csv: malformed CSV: {error}') from error
    if not rows or rows[0] != HEADER:
        raise ValueError('book_info.csv requires the supported six-column header')
    for _start, _end, fields in records:
        if any(not span[2] and '"' in _csv_value(text, span) for span in fields):
            raise ValueError('book_info.csv: quote in an unquoted field')
    identities = set()
    for index, row in enumerate(rows[1:], start=2):
        if not row:
            continue
        if len(row) != len(HEADER) or not row[0]:
            raise ValueError(f'book_info.csv record {index}: expected six fields and nonempty bookName')
        identity = tuple(row[:2])
        if identity in identities:
            raise ValueError(f'book_info.csv record {index}: duplicate book/author identity')
        identities.add(identity)
        if row[2] not in GENERATIONS:
            raise ValueError(f'book_info.csv record {index}: unsupported generation')
        for value in row[4:]:
            if value and (not YEAR.fullmatch(value) or not -2147483648 <= int(value) <= 2147483647):
                raise ValueError(f'book_info.csv record {index}: year must be a signed Int32 integer or empty')
        if row[4] and row[5] and int(row[4]) > int(row[5]):
            raise ValueError(f'book_info.csv record {index}: startYear exceeds endYear')
    return rows
