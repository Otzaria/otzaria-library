"""Place the built volumes into the otzaria-library tree and register them."""
import argparse
import csv
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".github" / "scripts"))
from book_info_writer import plan_registration, apply_registration
from validate_fordb_book_names import db_title as normalize_book_title

REPO = '/Users/david/Documents/otzaria-books/otzaria-library'
BOOK_DIR = os.path.join(
    REPO, 'MoreBooks/ספרים/אוצריא/הלכה/'
    'שולחן ערוך/מפרשים/אוצר ההלכה')
# the book folder under the packaged root -- the (informational) categoryPath
# column of ForDB/sefaria_metadata_changes.csv
CATEGORY = os.path.relpath(
    BOOK_DIR, os.path.join(REPO, 'MoreBooks/ספרים/אוצריא'))
LINKS_DIR = os.path.join(REPO, 'MoreBooks/links')
AUTHOR = 'מכון "איש מצליח"'
GENERATION = 'מחברי זמננו'
DESC = ('ליקוט מכ-500 ספרי אחרונים על סדר '
        'השולחן ערוך, הלכות שבת, '
        'במהדורת מכון "איש מצליח".')
NOTES_DESC = ('הערות וציונים של מכון "איש מצליח" על אוצר ההלכה, '
              'מקושרות לשורת הערך שקוראת להן.')
NOTES_PREFIX = 'הערות על '


def desc_for(title):
    return NOTES_DESC if title.startswith(NOTES_PREFIX) else DESC


# Descriptions never go into metadata.json: the generator reads it through
# BookMetadata, which has no heDesc field, so they would be silently dropped.
# ForDB/sefaria_metadata_changes.csv is the one path a description takes into
# seforim.db, for every book.
DESC_CSV_HEADER = ['categoryPath', 'title', 'author', 'heShortDesc', 'heDesc',
                   'heDescNew']


def normalize_hebrew_label(raw):
    """Mirror of normalizeHebrewLabel in SeforimLibrary: the book's title in
    seforim.db, and so the key of sefaria_metadata_changes.csv's title column."""
    s = raw.strip()
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('"', '\u05f4').replace("''", '\u05f4')
    s = s.replace('\u05f3\u05f3', '\u05f4').replace('`', '\u05f3')
    return re.sub(r'\s+', ' ', s).strip()


def upsert_description(rows, title, category, author, short_desc, long_desc):
    """Put one book's row into the parsed sefaria_metadata_changes.csv rows.

    The consumer reads by position: title (col 2, exact match), heShortDesc
    (col 4) -> book.heShortDesc, heDescNew (col 6) -> book.heDesc. Col 5 is
    Sefaria's original text and stays empty for our books. An empty cell means
    "keep what is there", so an empty value never overwrites a filled one.
    Returns 'add', 'update', or None when the row already says all of it."""
    hits = [i for i, r in enumerate(rows)
            if i and len(r) > 1 and r[1].strip() == title]
    if not hits:
        rows.append([category or '', title, author or '', short_desc or '', '',
                     long_desc or ''])
        return 'add'
    row = rows[hits[-1]]
    old = list(row)
    row += [''] * (len(DESC_CSV_HEADER) - len(row))
    for idx, val in ((0, category), (2, author), (3, short_desc),
                     (5, long_desc)):
        if val:
            row[idx] = val
    return 'update' if row != old else None


def sanitize(name):
    name = re.sub('[֑-ׇ]', '', name)
    name = re.sub(r'[\\/:*"״?<>|]', '', name).replace('_', ' ')
    return name.replace("''", '').replace("'", '').strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True,
                    help='the build output directory')
    ap.add_argument('--apply', action='store_true',
                    help='write into the repo (default is a dry run)')
    a = ap.parse_args()

    books = sorted(f for f in os.listdir(a.src) if f.endswith('.txt'))
    titles = [os.path.splitext(f)[0] for f in books]

    # a stale --src is the one mistake that does real damage: it silently
    # overwrites good volumes in the repo with an older build, and half the
    # set goes unregistered.
    if os.path.isdir(BOOK_DIR):
        missing = sorted(set(os.listdir(BOOK_DIR)) - set(books))
        if missing:
            raise SystemExit('%s already holds volumes absent from --src -- '
                             'stale build directory?\n  %s'
                             % (BOOK_DIR, '\n  '.join(missing)))

    meta_path = os.path.join(REPO, 'metadata.json')
    meta = json.load(open(meta_path, encoding='utf-8'))
    have = {m['title'] for m in meta}
    all_path = os.path.join(REPO, 'ForDB/all_metadata.json')
    all_meta = json.load(open(all_path, encoding='utf-8'))
    all_have = {m['title'] for m in all_meta}
    csv_plan = plan_registration(REPO, [[normalize_book_title(t), AUTHOR, GENERATION, '', '', ''] for t in titles])
    gen_titles = {r[0] for r in csv.reader(open(os.path.join(REPO, 'ForDB/book_info.csv'), encoding='utf-8', newline='')) if r}
    desc_path = os.path.join(REPO, 'ForDB/sefaria_metadata_changes.csv')
    with open(desc_path, encoding='utf-8', newline='') as f:
        descs = list(csv.reader(f))
    if not descs or descs[0] != DESC_CSV_HEADER:
        raise SystemExit('%s: unexpected header' % desc_path)

    print('target: %s' % BOOK_DIR)
    for t in titles:
        clash = sanitize(t) != t
        print('  %-52s sanitized-differs=%s  metadata=%s  all_metadata=%s'
              '  book_info=%s'
              % (t, clash, t in have, t in all_have, t in gen_titles))

    new_meta = [{'title': t, 'author': AUTHOR, 'pubDate': None,
                 'pubPlace': None, 'compPlace': None, 'compDate': None,
                 'תיאור_חדש': None, 'heShortDesc': None,
                 'heDesc': None, 'Unnamed: 9': None,
                 'order': None}
                for t in titles if t not in have]
    # the description goes to ForDB/sefaria_metadata_changes.csv instead (see
    # DESC_CSV_HEADER); every volume is upserted, so a re-run updates in place
    desc_changes = [upsert_description(descs, normalize_hebrew_label(t),
                                       CATEGORY, AUTHOR, None, desc_for(t))
                    for t in titles]
    # ForDB/all_metadata.json keeps its own, thinner row per book; the
    # MoreBooks rows there carry nothing but the title, the authors and the
    # source folder.
    new_all = [{'title': t, 'heAuthors': [AUTHOR], 'Sourcefolder': 'MoreBooks'}
               for t in titles if t not in all_have]
    new_gen = list(csv_plan)
    sidecars = [t + '_links.json' for t in titles
                if os.path.isfile(os.path.join(a.src, t + '_links.json'))]
    print('\nmetadata.json rows to add:   %d' % len(new_meta))
    print('all_metadata.json rows to add: %d' % len(new_all))
    print('book_info.csv rows to add: %d' % len(new_gen))
    print('books to write:              %d' % len(books))
    print('link sidecars to add:        %d' % len(sidecars))
    print('desc csv rows add/update:    %d/%d'
          % (desc_changes.count('add'), desc_changes.count('update')))

    if not a.apply:
        print('\ndry run -- nothing written. Re-run with --apply.')
        return

    os.makedirs(BOOK_DIR, exist_ok=True)
    for f in books:
        shutil.copyfile(os.path.join(a.src, f), os.path.join(BOOK_DIR, f))
    # only the main volumes carry a sidecar; it holds both the Shulchan Aruch
    # source records and the footnotes records pointing at the notes volume
    for lk in sidecars:
        shutil.copyfile(os.path.join(a.src, lk), os.path.join(LINKS_DIR, lk))
    # Each of the four registries has its own on-disk shape, and re-encoding
    # one of them differently rewrites every line of a file with thousands of
    # rows. metadata.json is one compact object per line; all_metadata.json is
    # indented by two; book_info.csv is LF, not the csv module's default;
    # sefaria_metadata_changes.csv is LF with every field quoted.
    if new_meta:
        meta.extend(new_meta)
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write('[\n' + ',\n'.join(
                json.dumps(m, ensure_ascii=False, separators=(',', ':'))
                for m in meta) + '\n]\n')
    if new_all:
        all_meta.extend(new_all)
        with open(all_path, 'w', encoding='utf-8') as f:
            json.dump(all_meta, f, ensure_ascii=False, indent=2)
            f.write('\n')
    apply_registration(REPO, csv_plan)
    if any(desc_changes):
        with open(desc_path, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, quoting=csv.QUOTE_ALL,
                       lineterminator='\n').writerows(descs)
    print('\nwrote %d books, %d sidecars, registered %d titles'
          % (len(books), len(sidecars), len(new_meta)))


if __name__ == '__main__':
    main()
