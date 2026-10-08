#!/usr/bin/env python3
"""colon_breaks.py - איחוד שורות שנשברו אחרי ": " שאינו סוף עניין, בספרי דיקטה הערוכים.

רקע: הממיר הישן (all in one.py) וכלי "נקודותיים ורווח" הישן החליפו כל ": " בירידת שורה,
גם בתוך סוגריים ("(שבת קיט:" / "ד"ה ..."), אחרי מבוא לציטוט (וז"ל:) ובתוך מודגש פתוח.
הכלל הנכון הוא dicta_edit_core.colon_ends_matter (אותו כלל שמשמש את colon_newline ואת
dicta_convert). שורה שמסתיימת ב-":" שלפי הכלל אינה סוף עניין מאוחדת עם השורה שאחריה -
רק כשהעד מראה את שני הקצוות באותה פסקה. פסקת דיקטה מכילה לעתים כמה ד"ה וציטוטים,
ולכן העד לבדו אינו מספיק: ד"ה, מודגש וסמן סעיף בתחילת השורה הבאה - פסקה חדשה (בספק לא מאחדים).

העד: הגולמי שבמאגר (extraBooks/דיקטה, לא ערוך) נוצר באותו ממיר ישן ושובר באותם מקומות,
ולכן אינו עד לבאג הזה. העד הוא ה-zip המקורי של דיקטה, מומר ב-dicta_convert בלי פיצול
נקודותיים (שורה = פסקה של דיקטה). `witness` מוריד ומכין אותו לכל ספר שיש בו שורות חשודות.

שימוש:
  colon_breaks.py witness --zip-cache DIR --witness-dir DIR
  colon_breaks.py scan --witness-dir DIR [--out report.json]
  colon_breaks.py fix  --witness-dir DIR [--out report.json]    (כותב לקבצים ומזיז קבצי links)
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbs_breaks as D  # noqa: E402

SCRIPTS = os.path.join(D.REPO, 'DictaToOtzaria', 'סקריפטים')
sys.path.insert(0, os.path.join(SCRIPTS, 'עריכת ספרים'))
sys.path.insert(0, SCRIPTS)
from dicta_edit_core import colon_ends_matter  # noqa: E402

END_COLON = re.compile(r':\s*$')
NOTE_START = re.compile(r'\s*<sup\b')
HEADER_LINES = 2  # <h1> ושורת המחבר


def process(path, ri, apply, pinned=frozenset(), block_merge=False):
    full = os.path.join(D.REPO, path)
    L = open(full, encoding='utf-8', newline='').read().split('\n')
    st = collections.Counter()
    ex = collections.defaultdict(list)

    def note(kind, i, a, b):
        st[kind] += 1
        if len(ex[kind]) < 4:
            ex[kind].append([i + 1, D.plain(a)[-25:] + ' || ' + D.plain(b)[:25]])

    out, linemap = [], []
    i = 0
    while i < len(L):
        start = i
        cur = L[i]
        cur_pinned = i in pinned
        linemap.append(len(out))
        i += 1
        while start >= HEADER_LINES and D.is_body(cur) and i < len(L) and D.is_body(L[i]):
            nxt = L[i]
            if not END_COLON.search(cur) or colon_ends_matter(END_COLON.sub('', cur), nxt):
                break
            if NOTE_START.match(nxt):
                break  # שורה שמתחילה בסמן הערה היא הערה נפרדת (ספר "הערות על ...")
            j = ri.joined(D.toks(cur), D.toks(nxt)) if ri else 'noraw'
            blocked = block_merge or (cur_pinned and i in pinned)
            if j == 'join' and not blocked:
                note('c_joined', i - 1, cur, nxt)
                cur = cur.rstrip() + ' ' + nxt.lstrip()
                cur_pinned = cur_pinned or i in pinned
                linemap.append(len(out))
                i += 1
                continue
            if j == 'join':
                note('c_blocked_links', i - 1, cur, nxt)
            elif j == 'break':
                note('c_raw_also_breaks', i - 1, cur, nxt)
            else:
                note('c_no_evidence', i - 1, cur, nxt)
            break
        out.append(cur)
    merged = st['c_joined']
    if apply and merged:
        open(full, 'w', encoding='utf-8', newline='').write('\n'.join(out))
    return {'lines': len(L), 'merged': merged, 'stats': dict(st), 'examples': dict(ex)}, linemap


def suspects(path):
    """כמה שורות בספר מסתיימות ב-":" שאינו סוף עניין וממשיכות בשורת גוף."""
    L = open(os.path.join(D.REPO, path), encoding='utf-8').read().split('\n')
    return sum(1 for i in range(HEADER_LINES, len(L) - 1)
               if D.is_body(L[i]) and D.is_body(L[i + 1]) and END_COLON.search(L[i])
               and not colon_ends_matter(END_COLON.sub('', L[i]), L[i + 1]))


def edited_to_dicta():
    """נתיב ספר ערוך -> (fileName, OCRDataURL) לפי dicta_state.json."""
    st = json.load(open(os.path.join(SCRIPTS, 'dicta_state.json'), encoding='utf-8'))
    out = {}
    for fn, v in st['books'].items():
        for p in v.get('repo', {}).get('edited', []):
            out[p] = (fn, v['dicta']['OCRDataURL'])
    return out


def build_witness(books, zip_cache, witness_dir):
    import dicta_convert as DC
    os.makedirs(zip_cache, exist_ok=True)
    os.makedirs(witness_dir, exist_ok=True)
    m = edited_to_dicta()
    done = missing = 0
    for p in books:
        if p not in m:
            missing += 1
            continue
        fn, url = m[p]
        out = os.path.join(witness_dir, fn + '.txt')
        if os.path.exists(out):
            done += 1
            continue
        z = os.path.join(zip_cache, fn + '.zip')
        if not os.path.exists(z):
            for attempt in range(3):
                # curl כמו dicta_sync: השרת דוחה (403) את ה-User-Agent של urllib
                r = subprocess.run(['curl', '-sfL', '--max-time', '300', '-o', z + '.part', url])
                if r.returncode == 0:
                    os.replace(z + '.part', z)
                    break
                print('download failed (%d) %s: curl rc=%d' % (attempt + 1, fn, r.returncode), file=sys.stderr)
                time.sleep(5)
            else:
                missing += 1
                continue
        text = DC.convert_zip(z, options=DC.ConvertOptions(split_colon=False)).text
        open(out, 'w', encoding='utf-8', newline='').write(text)
        done += 1
    print('witness ready: %d, without zip: %d' % (done, missing))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['witness', 'scan', 'fix'])
    ap.add_argument('--out', default='colon_breaks_report.json')
    ap.add_argument('--witness-dir', required=True)
    ap.add_argument('--zip-cache')
    a = ap.parse_args()
    apply = a.mode == 'fix'
    books = [p for p in D.git('ls-files', '--', D.EDITED_PREFIX).split('\n')
             if p.endswith('.txt') and suspects(p)]
    if a.mode == 'witness':
        if not a.zip_cache:
            ap.error('witness requires --zip-cache')
        build_witness(books, a.zip_cache, a.witness_dir)
        return
    m = edited_to_dicta()
    lidx = D.links_index()
    titles = D.packaged_title_counts()
    report = {}
    for p in books:
        b = os.path.basename(p)
        title = b[:-4]
        rp = os.path.join(a.witness_dir, m[p][0] + '.txt') if p in m else None
        ri = D.RawIndex(rp) if rp and os.path.exists(rp) else None
        if ri is None:
            rp = None
        files = lidx.get(title, [])
        r, linemap = process(p, ri, apply, D.pinned_lines(title),
                             block_merge=bool(files) and titles[title] > 1)
        r['raw'] = os.path.basename(rp) if rp else None
        r['links_files'] = files
        r['links_shifted'] = D.shift_links(title, files, linemap) if apply and r['merged'] else {}
        report[p] = r
    json.dump(report, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    tot = collections.Counter()
    for r in report.values():
        tot.update(r['stats'])
        tot['links_values_shifted'] += sum(r['links_shifted'].values())
    print('books scanned: %d, without raw: %d, changed: %d' % (
        len(report), sum(1 for r in report.values() if not r['raw']),
        sum(1 for r in report.values() if r['merged'])))
    for k, v in sorted(tot.items()):
        print('%-28s %d' % (k, v))


if __name__ == '__main__':
    main()
