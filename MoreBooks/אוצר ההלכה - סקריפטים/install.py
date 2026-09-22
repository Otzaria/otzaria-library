"""Place the built volumes into the otzaria-library tree and register them."""
import argparse
import csv
import json
import os
import re
import shutil

REPO = '/Users/david/Documents/otzaria-books/otzaria-library'
BOOK_DIR = os.path.join(
    REPO, 'MoreBooks/ספרים/אוצריא/הלכה/'
    'שולחן ערוך/מפרשים/אוצר ההלכה')
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
    gen_path = os.path.join(REPO, 'ForDB/generations.csv')
    with open(gen_path, encoding='utf-8') as f:
        gens = list(csv.reader(f))
    gen_titles = {r[0] for r in gens[1:] if r}

    print('target: %s' % BOOK_DIR)
    for t in titles:
        clash = sanitize(t) != t
        print('  %-52s sanitized-differs=%s  metadata=%s  all_metadata=%s'
              '  generations=%s'
              % (t, clash, t in have, t in all_have, t in gen_titles))

    new_meta = [{'title': t, 'author': AUTHOR, 'pubDate': None,
                 'pubPlace': None, 'compPlace': None, 'compDate': None,
                 'תיאור_חדש': None, 'heShortDesc': None,
                 'heDesc': desc_for(t), 'Unnamed: 9': None,
                 'order': None}
                for t in titles if t not in have]
    # ForDB/all_metadata.json keeps its own, thinner row per book; the
    # MoreBooks rows there carry nothing but the title, the authors and the
    # source folder.
    new_all = [{'title': t, 'heAuthors': [AUTHOR], 'Sourcefolder': 'MoreBooks'}
               for t in titles if t not in all_have]
    new_gen = [[t, GENERATION] for t in titles if t not in gen_titles]
    sidecars = [t + '_links.json' for t in titles
                if os.path.isfile(os.path.join(a.src, t + '_links.json'))]
    print('\nmetadata.json rows to add:   %d' % len(new_meta))
    print('all_metadata.json rows to add: %d' % len(new_all))
    print('generations.csv rows to add: %d' % len(new_gen))
    print('books to write:              %d' % len(books))
    print('link sidecars to add:        %d' % len(sidecars))

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
    # Each of the three registries has its own on-disk shape, and re-encoding
    # one of them differently rewrites every line of a file with thousands of
    # rows. metadata.json is one compact object per line; all_metadata.json is
    # indented by two; generations.csv is LF, not the csv module's default.
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
    if new_gen:
        gens.extend(new_gen)
        with open(gen_path, 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, lineterminator='\n').writerows(gens)
    print('\nwrote %d books, %d sidecars, registered %d titles'
          % (len(books), len(sidecars), len(new_meta)))


if __name__ == '__main__':
    main()
