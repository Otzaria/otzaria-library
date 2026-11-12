"""Storage contract shared with the website's complete book-info CSV reader."""
import csv
import io
import re

from fordb_book_renames import _csv_value, csv_records, EditVerificationError

HEADER = ['bookName', 'authorName', 'generationName', 'subGenerationName', 'startYear', 'endYear']
# Book-level fields: every row of the same bookName carries identical values.
EXTENSION = ['topics', 'pubDate', 'pubPlace', 'description', 'proofread']
EXTENDED_HEADER = HEADER + EXTENSION
HEADERS = (HEADER, EXTENDED_HEADER)
GENERATIONS = {'', 'תורה שבכתב', 'חז"ל', 'ראשונים', 'אחרונים', 'מחברי זמננו'}
SUBGENERATIONS = {
    '': set(), 'תורה שבכתב': set(),
    'חז"ל': {'תקופת המקרא', 'חז"ל', 'תנאים', 'אמוראים'},
    'ראשונים': {'גאונים', 'ראשוני הראשונים', 'אחרוני הראשונים'},
    'אחרונים': {'ראשוני האחרונים', 'אחרוני האחרונים', 'ראשי הישיבות'},
    'מחברי זמננו': {'מחברי זמננו'},
}
YEAR = re.compile(r'-?[0-9]+\Z')
MAX_TOPICS = 10
MAX_TOPIC_LENGTH = 60
MAX_PUB_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 4000
PROOFREAD = {'', '1'}


def split_topics(value):
    """Topic values in order: trimmed, empty values dropped, duplicates removed."""
    return list(dict.fromkeys(t.strip() for t in value.split(';') if t.strip()))


def extension_error(fields):
    """Return why the five extension values are invalid, or None."""
    topics, pub_date, pub_place, description, proofread = fields
    if '\n' in topics:
        return 'topics must be a single line'
    values = split_topics(topics)
    if len(values) > MAX_TOPICS:
        return f'topics allows at most {MAX_TOPICS} values'
    if any(len(t) > MAX_TOPIC_LENGTH for t in values):
        return f'a topic exceeds {MAX_TOPIC_LENGTH} characters'
    for name, value in (('pubDate', pub_date), ('pubPlace', pub_place)):
        if '\n' in value or len(value) > MAX_PUB_LENGTH:
            return f'{name} must be a single line of at most {MAX_PUB_LENGTH} characters'
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return f'description exceeds {MAX_DESCRIPTION_LENGTH} characters'
    if proofread not in PROOFREAD:
        return 'proofread must be empty or 1'
    return None


def validate_book_info(data):
    """Return parsed rows after validating the entire source, before any writes.

    The header is the six base columns or the eleven extended ones.
    Quoted LF text is supported; CR (including CRLF), BOM and NUL are refused.
    Years are empty or signed Int32 integers. Identity is the exact book+author.
    """
    text = data.decode('utf-8')
    if '\ufeff' in text or '\r' in text or '\0' in text:
        raise ValueError('book_info.csv requires UTF-8 without BOM, LF, and no CR/NUL')
    try:
        records = csv_records(text)
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except (EditVerificationError, csv.Error) as error:
        raise ValueError(f'book_info.csv: malformed CSV: {error}') from error
    if not rows or rows[0] not in HEADERS:
        raise ValueError('book_info.csv requires the six-column or eleven-column header')
    header = rows[0]
    for _start, _end, fields in records:
        if any(not span[2] and '"' in _csv_value(text, span) for span in fields):
            raise ValueError('book_info.csv: quote in an unquoted field')
    identities = set()
    book_extensions = {}
    for index, row in enumerate(rows[1:], start=2):
        if len(row) != len(header) or not row[0]:
            raise ValueError(f'book_info.csv record {index}: expected {len(header)} fields and nonempty bookName')
        identity = tuple(row[:2])
        if identity in identities:
            raise ValueError(f'book_info.csv record {index}: duplicate book/author identity')
        identities.add(identity)
        if row[2] not in GENERATIONS:
            raise ValueError(f'book_info.csv record {index}: unsupported generation')
        if row[3] and row[3] not in SUBGENERATIONS[row[2]]:
            raise ValueError(f'book_info.csv record {index}: incompatible generation/subgeneration')
        for value in row[4:6]:
            if value and (not YEAR.fullmatch(value) or not -2147483648 <= int(value) <= 2147483647):
                raise ValueError(f'book_info.csv record {index}: year must be a signed Int32 integer or empty')
        if row[4] and row[5] and int(row[4]) > int(row[5]):
            raise ValueError(f'book_info.csv record {index}: startYear exceeds endYear')
        extension = tuple(row[len(HEADER):])
        if extension:
            error = extension_error(extension)
            if error:
                raise ValueError(f'book_info.csv record {index}: {error}')
            if book_extensions.setdefault(row[0], extension) != extension:
                raise ValueError(f'book_info.csv record {index}: extension fields differ between rows of {row[0]!r}')
    return rows
