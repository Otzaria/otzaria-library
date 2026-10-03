#!/usr/bin/env python3
"""התקנת הפלט של build.py למאגר ורישום בשלושת המרשמים.

    python3 install.py --src <tmp>/out            # הרצה יבשה
    python3 install.py --src <tmp>/out --apply

- "פירוש הגרא על משלי" → תנך/אחרונים (חדש), "רבינו יונה על משלי" → תנך/ראשונים
  (מחליף את הקובץ החלקי הקיים, אותו שם ונתיב). ספרי ההערות לצד כל ספר.
- קובצי הקישורים → MoreBooks/links.
- metadata.json / ForDB/all_metadata.json / ForDB/book_info.csv: רק שורות חסרות;
  ספרי ההערות ממוזגים בבניית ה-DB ולכן *אין* להם רשומה.
- לפני כתיבה מאומת round-trip זהה בית-בבית של כל מרשם.
"""
import argparse
import csv
import io
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".github" / "scripts"))
from book_info_writer import plan_registration, apply_registration
from validate_fordb_book_names import db_title as normalize_book_title

REPO = '/Users/david/Documents/otzaria-books/otzaria-library'
TANAKH = os.path.join(REPO, 'MoreBooks/ספרים/אוצריא/תנך')
LINKS_DIR = os.path.join(REPO, 'MoreBooks/links')
NOTES_PREFIX = 'הערות על '
BOOKS = {
    'פירוש הגרא על משלי': {'dir': 'אחרונים', 'author': 'אליהו בן שלמה זלמן מווילנה',
                           'generation': 'אחרונים'},
    'רבינו יונה על משלי': {'dir': 'ראשונים', 'author': 'רבינו יונה',
                           'generation': 'ראשונים'},
}


def dump_meta(meta):
    return '[\n' + ',\n'.join(json.dumps(m, ensure_ascii=False, separators=(',', ':'))
                              for m in meta) + '\n]\n'


def dump_all(all_meta):
    return json.dumps(all_meta, ensure_ascii=False, indent=2) + '\n'


def dump_gen(rows):
    f = io.StringIO()
    csv.writer(f, lineterminator='\n').writerows(rows)
    return f.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True, help='תיקיית הפלט של build.py')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    files = []   # (src, dst)
    for t, b in BOOKS.items():
        for name in (t, NOTES_PREFIX + t):
            s = os.path.join(a.src, name + '.txt')
            if name == t and not os.path.isfile(s):
                raise SystemExit('missing in --src: %s' % s)
            if os.path.isfile(s):
                files.append((s, os.path.join(TANAKH, b['dir'], name + '.txt')))
        s = os.path.join(a.src, t + '_links.json')
        if not os.path.isfile(s):
            raise SystemExit('missing in --src: %s' % s)
        files.append((s, os.path.join(LINKS_DIR, t + '_links.json')))

    meta_path = os.path.join(REPO, 'metadata.json')
    all_path = os.path.join(REPO, 'ForDB/all_metadata.json')
    csv_plan = plan_registration(REPO, [[normalize_book_title(t), b['author'], b['generation'], '', '', ''] for t, b in BOOKS.items()])
    gen_have = {r[0] for r in csv.reader(open(os.path.join(REPO, 'ForDB/book_info.csv'), encoding='utf-8', newline='')) if r}
    raw_meta = open(meta_path, encoding='utf-8', newline='').read()
    raw_all = open(all_path, encoding='utf-8', newline='').read()
    meta = json.loads(raw_meta)
    all_meta = json.loads(raw_all)
    rt = {'metadata.json': dump_meta(meta) == raw_meta,
          'all_metadata.json': dump_all(all_meta) == raw_all,
          'book_info.csv': True}  # already validated by shared planner
    print('round-trip byte-identical:', rt)
    if not all(rt.values()):
        raise SystemExit('registry format would change -- refusing')

    have = {m['title'] for m in meta}
    all_have = {m['title'] for m in all_meta}
    for t in BOOKS:
        for n in (NOTES_PREFIX + t,):
            if n in have or n in all_have or n in gen_have:
                raise SystemExit('notes companion must not be registered: %s' % n)
    # תיאור לא נכתב ל־metadata.json (המחולל קורא אותו דרך BookMetadata, שאין בו heDesc) —
    # השדות נשארים None. הדרך היחידה של תיאור ל־DB היא ForDB/sefaria_metadata_changes.csv;
    # לספרים אלה אין כאן טקסט תיאור, ולכן גם לא נוספת שם שורה.
    new_meta = [{'title': t, 'author': b['author'], 'pubDate': None, 'pubPlace': None,
                 'compPlace': None, 'compDate': None, 'תיאור_חדש': None,
                 'heShortDesc': None, 'heDesc': None, 'Unnamed: 9': None, 'order': None}
                for t, b in BOOKS.items() if t not in have]
    new_all = [{'title': t, 'heAuthors': [b['author']], 'Sourcefolder': 'MoreBooks'}
               for t, b in BOOKS.items() if t not in all_have]
    new_gen = list(csv_plan)
    for s, d in files:
        print('  %s %s' % ('replace' if os.path.exists(d) else 'new    ', os.path.relpath(d, REPO)))
    print('metadata.json +%d %s' % (len(new_meta), [m['title'] for m in new_meta]))
    print('all_metadata.json +%d %s' % (len(new_all), [m['title'] for m in new_all]))
    print('book_info.csv +%d %s' % (len(new_gen), new_gen))
    if not a.apply:
        print('dry run -- nothing written. Re-run with --apply.')
        return
    for s, d in files:
        shutil.copyfile(s, d)
    if new_meta:
        with open(meta_path, 'w', encoding='utf-8', newline='') as f:
            f.write(dump_meta(meta + new_meta))
    if new_all:
        with open(all_path, 'w', encoding='utf-8', newline='') as f:
            f.write(dump_all(all_meta + new_all))
    apply_registration(REPO, csv_plan)
    print('written.')


if __name__ == '__main__':
    main()
