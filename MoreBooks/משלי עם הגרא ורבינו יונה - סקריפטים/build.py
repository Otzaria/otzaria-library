#!/usr/bin/env python3
"""בניית "פירוש הגרא על משלי" ו"רבינו יונה על משלי" מתוך __משלי.docx.

    python3 parse_docx.py ~/Downloads/__משלי.docx <tmp>/parsed.json
    python3 build.py --parsed <tmp>/parsed.json --docx ~/Downloads/__משלי.docx \
        --db <seforim.db> --out <tmp>/out

לכל ספר נוצרים: הספר, `הערות על <ספר>` (רק אם יש לו הערות), `<ספר>_links.json`
ו-`<ספר>_linemap.json` (שורה → רשימת פסוקים, לבדיקה בלבד; לא מותקן).

מבנה הספר: <h1>, שורת מחבר, <h2>פרק X</h2>, <h3>פסוק Y</h3>, שורה לכל פסקה.
טקסט הפסוק עצמו אינו נכלל (הוא ספר הבסיס, משלי של ספריא).

קישורים: כל שורת פירוש (כולל פסקאות המשך) → הפסוק שלה, `source` + `ref_2`.
שורה שהעורך או המפרש מציינים שהיא מתייחסת לכמה פסוקים מקבלת רשומה נפרדת לכל
פסוק בטווח (ר' PARA / BLOCK / FIRST למטה). כותרות אינן מקושרות (כמו בכל התקדימים במאגר).
הערות שוליים → `footnotes` אל ספר ההערות, בלי ref_2.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import zipfile

from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_docx import W, esc, run_props, to_html  # noqa: E402

BOOKS = {
    'gra': {'title': 'פירוש הגרא על משלי',
            'h1': 'פירוש הגר"א על משלי',          # כמו "פירוש הגר"א על שיר השירים"
            'author': 'רבנו אליהו מווילנא זצללה"ה'},  # שורה 2 כמו בשיר השירים
    'ry': {'title': 'רבינו יונה על משלי',
           'h1': 'רבינו יונה על משלי',
           'author': 'רבינו יונה'},               # כמו בקובץ הקיים
}
NOTES_PREFIX = 'הערות על '
PATH_2 = 'אוצריא\\תנך\\כתובים\\משלי.txt'
REF = 'Proverbs'
HE = 'משלי'

LET = {'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5, 'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9,
       'י': 10, 'כ': 20, 'ל': 30, 'מ': 40}


def gem(s):
    return sum(LET[c] for c in s)


def R(a, b):
    return list(range(a, b + 1))


# ---------------------------------------------------------------------------
# שורות שמתייחסות ליותר מפסוק אחד. נמצאו בסריקת regex (qa.py --scan מדפיס
# את כל המועמדים) ונבחרו ידנית: רק היכן שהטקסט אומר במפורש מהו הטווח.
# הפניה צולבת ("כמו שאמר בפסוק הקודם", "לעיל פסוק ז") אינה טווח ואינה כאן.
#
# PARA: (מפרש, מספר פסקה ב-docx) → פסוקים (בפרק של השורה)
PARA = {
    ('gra', 38): R(7, 8),      # 1:8  "אלו השני פסוקים (ז,ח)"
    ('gra', 197): R(16, 19),   # 2:19 "(א.ה. פסוק טז על ..., פסוק יז על ...)"
    ('gra', 198): R(16, 19),   # 2:19 "(א.ה. פסוקים טז-יט על ...)"
    ('gra', 326): R(19, 20),   # 3:20 "(א.ה. בשני הפסוקים יט,כ)"
    ('gra', 444): R(7, 9),     # 4:9  "(ג.פ: פסוקים ז-ט)"
    ('gra', 447): R(10, 12),   # 4:10 "עכשיו אומר ג' פסוקים" (= ג.פ שבפס' יב)
    ('gra', 455): R(10, 12),   # 4:12 "(ג.פ: פסוקים י-יב)"
    ('gra', 477): R(1, 19),    # 4:19 "(א.ה. הפסוקים מתחלת הפרק עד כאן ...)"
    ('gra', 530): R(9, 10),    # 5:10 "(ג.פ המשך פירושו מהפסוק הקודם)"
    ('gra', 532): R(9, 11),    # 5:11 "(ג.פ המשך פירושו מפסוקים ט-י)"
    ('gra', 612): R(12, 14),   # 6:14 "ואלו הג' פסוקים (יב-יד)"
    ('gra', 664): R(27, 29),   # 6:29 "(פסוקים כז-כח במדות, כט במצות ותורה)"
    ('gra', 688): R(1, 4),     # 7:1  "(ג.פ: פסוק א כנגד פשט, ב דרש, ג רמז, ד סוד)"
    ('gra', 781): R(1, 36),    # 8:5  חלוקת כל פרק ח ("ג.פ כוונתו שכל פרק ח מתחלק")
    ('gra', 783): R(6, 11),    # 8:6  "ואמר כאן ששה פסוקים"
    ('gra', 915): R(1, 4),     # 10:1 "הר"ת של הד' פסוקים הראשונים"
    ('gra', 1569): R(16, 19),  # 15:19 "(א.ה. ארבעת הפסוקים האחרונים) טוב מעט..."
    ('gra', 1630): R(1, 4),    # 16:4 "סוד הענין של הד' פסוקים"
    ('gra', 1718): R(27, 29),  # 16:29 "ובשלושה פסוקים אלו אמר שלוש פעמים איש"
    ('gra', 2399): R(1, 8),    # 23:1 "(א.ה. הגר"א מבאר כן את הפסוקים א-ח)"
    ('gra', 2821): R(18, 19),  # 27:18 "(וראה המשך בפ' הבא)"
    ('gra', 2873): R(15, 16),  # 28:15 "(המשך בפסוק הבא)"
    ('gra', 2875): R(15, 16),  # 28:16 "(המשך מהפסוק הקודם)"
    ('gra', 2886): R(20, 21),  # 28:20 "(וראה בפסוק הבא)"
    ('gra', 2966): R(1, 14),   # 30 מבוא: "הגר"א קושר את כל הפסוקים עד פסוק יד"
    ('gra', 3100): R(29, 31),  # 31:29 "בכל הג' פסוקים עד סוף"
    ('ry', 446): R(10, 11),    # 4:10 "(זה והפסוק הבא מבוארים בפסוק הבא)"
    ('ry', 600): R(12, 13),    # 6:12 "(פירוש הפסוק תמצא בפסוק הבא)"
    ('ry', 1011): R(24, 25),   # 10:24 "(המשך בר"י בפסוק הבא)"
    ('ry', 1036): R(29, 30),   # 10:29 "(ג.פ המשך ביאור בפסוק הבא)"
    ('ry', 1449): R(20, 21),   # 14:20 "(המשך בפסוק הבא)"
    ('ry', 1646): R(8, 9),     # 16:9 "ראה בפסוק הקודם."
    ('ry', 2411): R(4, 5),     # 23:5 "ונסמכו שני הפסוקים האלה"
    ('ry', 2533): R(3, 4),     # 24:4 "(א.ה. הפסוק הקודם והנכחי)"
    # גשר: השורה מסתיימת בהבאת הפסוק הבא ("על כן סמך אחריו (הפסוק הבא):")
    ('ry', 1556): R(15, 16),   # 15:15
    ('ry', 1604): R(30, 31),   # 15:30
    ('ry', 1801): R(16, 17),   # 17:16
    ('ry', 2064): R(6, 7),     # 20:6
    ('ry', 2255): R(30, 31),   # 21:30
    ('ry', 2414): R(6, 8),     # 23:6 "יפרש בפסוקים הבאים אחריו:" (ו-ח יחידה אחת)
    ('ry', 2436): R(13, 14),   # 23:13
}
# BLOCK: (מפרש, פרק, פסוק) → כל שורות המפרש בפסוק הזה מתייחסות לטווח
BLOCK = {
    ('ry', 4, 11): R(10, 11),   # הפירוש המשותף שהוזכר בפס' י
    ('ry', 6, 13): R(12, 13),   # "(פירוש הפסוק תמצא בפסוק הבא)" בפס' יב
    ('ry', 10, 15): R(15, 16),  # "(א.ה. פירוש פסוק זה והבא אחריו ביחד)"
    ('ry', 10, 16): R(15, 16),  # "פירוש פסוק זה נמצא בפסוק הקודם"
    ('ry', 16, 8): R(8, 9),     # "המקרא הזה והבא אחריו"
    ('ry', 18, 22): R(22, 23),  # "הוא על פסוק זה והבא אחריו ביחד"
    ('ry', 24, 7): R(7, 8),     # "ביאר פסוק זה והבא אחריו"
    ('ry', 24, 8): R(8, 9),     # "ביאר פסוק זה והבא אחריו"
    ('ry', 24, 13): R(13, 14),  # "(פסוק זה והבא אחריו) כתובים במקום אחר"
    ('ry', 24, 21): R(21, 22),  # "פי' פסוק זה והבא אחריו"
    ('ry', 24, 30): R(30, 34),  # "מתיחס לפסוקים מכאן ועד סוף הפרק"
}
# FIRST: השורה הראשונה של המפרש בפסוק זה היא המשכו של הפסוק הקודם
FIRST = {
    ('ry', 10, 25): R(24, 25),
    ('ry', 10, 30): R(29, 30),
    ('ry', 14, 21): R(20, 21),
    ('gra', 27, 19): R(18, 19),
}


def load_verses(db):
    """(פרק, פסוק) → (lineIndex מבוסס-1, 'א', 'א') מתוך משלי שב-seforim.db."""
    c = sqlite3.connect(db)
    bid = c.execute("select id from book where title=?", (HE,)).fetchone()[0]
    out = {}
    for li, h in c.execute("select lineIndex, heRef from line where bookId=? "
                           "and heRef is not null", (bid,)):
        m = re.match(r'משלי, (\S+), (\S+)$', h)
        if m:
            out[(gem(m.group(1)), gem(m.group(2)))] = (li + 1, m.group(1), m.group(2))
    return out


def footnote_html(docx_path):
    """footnotes.xml → {id: html}; פסקאות מרובות מחוברות ב-<br>."""
    z = zipfile.ZipFile(docx_path)
    fx = etree.fromstring(z.read('word/footnotes.xml'))
    notes = {}
    for f in fx.iter(W + 'footnote'):
        fid = f.get(W + 'id')
        if int(fid) <= 0:
            continue
        paras = []
        for p in f.iter(W + 'p'):
            segs = []
            for r in p.iter(W + 'r'):
                b, u = run_props(r)
                for ch in r:
                    if ch.tag == W + 't':
                        segs.append((ch.text or '', b, u))
                    elif ch.tag == W + 'tab':
                        segs.append((' ', b, u))
            h = to_html(segs)
            if h:
                paras.append(h)
        notes[fid] = '<br>'.join(paras)
    return notes


def build(parsed, notes, verses, key):
    meta = BOOKS[key]
    title = meta['title']
    ntitle = NOTES_PREFIX + title
    lines = ['<h1>%s</h1>' % meta['h1'], meta['author']]
    # ספר ההערות: שורה 2 ריקה (לא נמחקת) — שורת מחבר לא מקושרת פוסלת את המיזוג
    nlines = ['<h1>%s</h1>' % ntitle, '']
    npath_written = []
    linemap = {}          # שורה (1-based) → [פסוקים]
    links, fn_links = [], []
    n_fn = 0
    used = set()

    def add_notes(html, path):
        nonlocal n_fn, npath_written
        out = html
        for fid in re.findall(r'\x00FN(\d+)\x00', html):
            n_fn += 1
            out = out.replace('\x00FN%s\x00' % fid, '<sup>%d</sup>' % n_fn, 1)
            if path != npath_written:
                i = 0
                while i < min(len(path), len(npath_written)) and path[i] == npath_written[i]:
                    i += 1
                nlines.extend(path[i:])
                npath_written = list(path)
            nlines.append('<sup>%d</sup> %s' % (n_fn, notes[fid]))
            fn_links.append((len(lines) + 1, len(nlines)))
        return out

    for c in parsed['chapters']:
        ch = gem(c['perek'])
        intro = c.get('intro', {}).get(key, [])
        pes = [p for p in c['pesukim'] if p[key]]
        if not intro and not pes:
            continue
        h2 = '<h2>פרק %s</h2>' % c['perek']
        lines.append(h2)
        for e in intro:
            vs = PARA.get((key, e['para']), [1])
            used.add((key, e['para']))
            lines.append(add_notes(e['html'], [h2]))
            linemap[len(lines)] = [(ch, v) for v in vs]
        for p in pes:
            v = gem(p['pasuk'])
            h3 = '<h3>פסוק %s</h3>' % p['pasuk']
            lines.append(h3)
            for j, e in enumerate(p[key]):
                vs = {v}
                if (key, e['para']) in PARA:
                    vs |= set(PARA[(key, e['para'])])
                    used.add((key, e['para']))
                if (key, ch, v) in BLOCK:
                    vs |= set(BLOCK[(key, ch, v)])
                    used.add((key, ch, v))
                if j == 0 and (key, ch, v) in FIRST:
                    vs |= set(FIRST[(key, ch, v)])
                    used.add((key, ch, v))
                lines.append(add_notes(e['html'], [h2, h3]))
                # הפסוק של השורה ראשון, אחריו השאר בסדר עולה
                linemap[len(lines)] = [(ch, v)] + [(ch, x) for x in sorted(vs - {v})]

    for li, vs in sorted(linemap.items()):
        for ch, v in vs:
            dbl, hc, hv = verses[(ch, v)]
            links.append({
                'line_index_1': li,
                'heRef_2': '%s %s, %s' % (HE, hc, hv),
                'path_2': PATH_2,
                'line_index_2': dbl,
                'ref_2': '%s %d:%d' % (REF, ch, v),
                'Conection Type': 'source',
            })
    for a, b in fn_links:
        links.append({
            'line_index_1': a,
            'heRef_2': 'הערות',
            'path_2': ntitle + '.txt',
            'line_index_2': b,
            'Conection Type': 'footnotes',
        })
    # רשומות לאותו פסוק רצופות בקובץ (validate_sidecars: אחרת groupConsecutiveLinks
    # מפצל את שורות המפרש של פסוק אחד לכמה קבוצות בתצוגה); ההערות בסוף.
    links.sort(key=lambda r: (r['Conection Type'] != 'source', r['line_index_2'], r['line_index_1']))
    return title, lines, (ntitle, nlines) if n_fn else None, links, linemap, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parsed', required=True)
    ap.add_argument('--docx', required=True)
    ap.add_argument('--db', required=True, help='seforim.db שמכיל את משלי')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    parsed = json.load(open(a.parsed, encoding='utf-8'))
    notes = footnote_html(a.docx)
    verses = load_verses(a.db)
    assert len(verses) == 915, len(verses)
    # הפסוקים ב-docx הם בדיוק פסוקי משלי, בסדר
    got = [(gem(c['perek']), gem(p['pasuk'])) for c in parsed['chapters'] for p in c['pesukim']]
    assert got == sorted(verses), 'verse sequence differs from Sefaria'
    # כל מפתח ב-PARA חייב להימצא (אחרת הטבלה התיישנה)
    loc = {}
    for c in parsed['chapters']:
        for k in ('ry', 'gra'):
            for e in c.get('intro', {}).get(k, []):
                loc[(k, e['para'])] = (gem(c['perek']), 0)
        for p in c['pesukim']:
            for k in ('ry', 'gra'):
                for e in p[k]:
                    loc[(k, e['para'])] = (gem(c['perek']), gem(p['pasuk']))
    for k, vs in PARA.items():
        assert k in loc, ('PARA key not found', k)
        ch, v = loc[k]
        assert v == 0 or v in vs, ('PARA range excludes own verse', k)
        assert all((ch, x) in verses for x in vs), ('PARA range out of chapter', k)
    os.makedirs(a.out, exist_ok=True)
    used_all = set()
    for key in BOOKS:
        title, lines, comp, links, linemap, used = build(parsed, notes, verses, key)
        used_all |= used
        with open(os.path.join(a.out, title + '.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        if comp:
            with open(os.path.join(a.out, comp[0] + '.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(comp[1]) + '\n')
        with open(os.path.join(a.out, title + '_links.json'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(links, ensure_ascii=False, indent=2) + '\n')
        with open(os.path.join(a.out, title + '_linemap.json'), 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in linemap.items()}, f, ensure_ascii=False)
        multi = sum(1 for v in linemap.values() if len(v) > 1)
        print('%-24s lines=%-5d notes=%-3d links=%-5d source=%-5d footnotes=%-3d multi-verse lines=%d'
              % (title, len(lines), sum(1 for l in (comp[1] if comp else []) if l.startswith('<sup>')),
                 len(links), sum(r['Conection Type'] == 'source' for r in links),
                 sum(r['Conection Type'] == 'footnotes' for r in links), multi))
    unused = [k for k in PARA if k not in used_all] + \
             [k for k in list(BLOCK) + list(FIRST) if k not in used_all]
    assert not unused, ('unused multi-verse rules', unused)


if __name__ == '__main__':
    main()
