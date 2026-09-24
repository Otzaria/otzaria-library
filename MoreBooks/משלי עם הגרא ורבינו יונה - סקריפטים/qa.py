#!/usr/bin/env python3
"""בדיקות לפלט של build.py. מדפיס מספרים בלבד (וקטעים של עד ~50 תווים).

    python3 qa.py --docx ~/Downloads/__משלי.docx --parsed <tmp>/parsed.json \
        --db <seforim.db> --out <tmp>/out [--scan]

1. שימור טקסט: טוקנים של ה-docx (קריאה עצמאית ב-python-docx, בלי המפרק)
   מול טוקני הפלט — ריבוי זהה, ורצף זהה (difflib) לכל ספר.
2. מבנה: כותרות פרק/פסוק עולות, אין שורות ריקות, אין <i> / class="footnote".
3. הערות: <sup>N</sup> רציפים, כל סמן מקושר לשורת ההערה שלו.
4. קישורים: כל שורת תוכן מקושרת לפסוק שתחת כותרתו; ref_2/heRef_2/line_index_2
   תואמים זה לזה ול-DB; בלי טווחים; בלי commentary.
5. חוזה המיזוג (merge_contract.check של אוצר ההלכה).
--scan: כל השורות שמזכירות טווח/המשך פסוקים, ומה נעשה בהן.
"""
import argparse
import collections
import difflib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import zipfile

import docx
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import BOOKS, NOTES_PREFIX, gem, load_verses  # noqa: E402

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'
NIK = re.compile(r'[֑-ׇ]')
LABEL = re.compile(r'^\s*(?:רבי?נו יונה|ב?הגר["״]א)\s*:\s*')


def toks(s):
    # סמן הערה ותגי עיצוב נכנסו בלי רווח (במקום ה-footnoteReference / גבול ה-run)
    s = re.sub(r'<sup>\d+</sup>', '', s)
    s = re.sub(r'<br>', ' ', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return [t for t in re.split(r'\s+', s) if t and t not in ('|', '–')]


def docx_tokens(path):
    """קריאה עצמאית: פסקאות שאינן פסוק/פרק, בלי תווית המפרש; תיבות טקסט פעם אחת."""
    d = docx.Document(path)
    per_para = {}
    for i, p in enumerate(d.paragraphs):
        # w:r ישירים ו-w:hyperlink לפי הסדר; w:t שבתוך תיבות טקסט אינם ילדים ישירים
        t = ''
        for el in p._p:
            if el.tag == W + 'r':
                t += ''.join(x.text or '' for x in el.findall(W + 't'))
            elif el.tag == W + 'hyperlink':
                t += ''.join(x.text or '' for r in el.findall(W + 'r') for x in r.findall(W + 't'))
        box = []
        for ac in p._p.iter(MC + 'AlternateContent'):
            ch = ac.find(MC + 'Choice')
            for x in ch.iter(W + 't'):
                box.append(x.text or '')
        s = re.sub(r'\s+', ' ', t).strip()
        if re.match(r'^פרק [א-ת]{1,3}$', s) or re.match(r'^\([א-ת]{1,3}\)', s):
            continue
        s = LABEL.sub('', s)
        tk = toks(s.replace('<', '&lt;')) + [w for b in box for w in b.split()]
        if tk:
            per_para[i] = tk
    z = zipfile.ZipFile(path)
    fx = etree.fromstring(z.read('word/footnotes.xml'))
    fn = []
    for f in fx.iter(W + 'footnote'):
        if int(f.get(W + 'id')) > 0:
            for p in f.iter(W + 'p'):
                fn += toks(''.join(x.text or '' for x in p.iter(W + 't')).replace('<', '&lt;'))
    return per_para, fn


def read(path):
    return open(path, encoding='utf-8').read().split('\n')[:-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--docx', required=True)
    ap.add_argument('--parsed', required=True)
    ap.add_argument('--db', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--scan', action='store_true')
    a = ap.parse_args()
    bad = 0
    parsed = json.load(open(a.parsed, encoding='utf-8'))
    verses = load_verses(a.db)

    # ---- 1. שימור טקסט
    per_para, fn_tok = docx_tokens(a.docx)
    owner = {}
    for c in parsed['chapters']:
        for k in ('ry', 'gra'):
            for e in c.get('intro', {}).get(k, []):
                owner[e['para']] = k
        for p in c['pesukim']:
            for k in ('ry', 'gra'):
                for e in p[k]:
                    owner[e['para']] = k
    orphan = [i for i in per_para if i not in owner]
    print('1. docx content paragraphs %d, assigned to a commentator %d, orphan %d %s'
          % (len(per_para), len(owner), len(orphan), orphan[:5]))
    bad += bool(orphan)
    out_all, src_all = collections.Counter(), collections.Counter()
    for k, meta in BOOKS.items():
        L = read(os.path.join(a.out, meta['title'] + '.txt'))
        body = [t for l in L[2:] if not re.match(r'<h[1-6]>', l) for t in toks(l)]
        src = [t for i in sorted(per_para) if owner.get(i) == k for t in per_para[i]]
        sm = difflib.SequenceMatcher(None, src, body, autojunk=False)
        ops = [o for o in sm.get_opcodes() if o[0] != 'equal']
        print('   %-22s docx tokens %6d  book tokens %6d  diff ops %d'
              % (meta['title'], len(src), len(body), len(ops)))
        for o in ops[:5]:
            print('      ', o[0], ' '.join(src[o[1]:o[2]])[:50], '->', ' '.join(body[o[3]:o[4]])[:50])
        bad += bool(ops)
        out_all.update(body)
        src_all.update(src)
        np_ = os.path.join(a.out, NOTES_PREFIX + meta['title'] + '.txt')
        if os.path.exists(np_):
            out_all.update(t for l in read(np_)[2:] if not re.match(r'<h[1-6]>', l) for t in toks(l))
    src_all.update(fn_tok)
    miss, extra = src_all - out_all, out_all - src_all
    print('   whole-work multiset (books+notes vs docx+footnotes): missing %d, extra %d'
          % (sum(miss.values()), sum(extra.values())), list(miss.items())[:5], list(extra.items())[:5])
    bad += bool(miss or extra)

    # ---- 2-4
    for k, meta in BOOKS.items():
        title = meta['title']
        L = read(os.path.join(a.out, title + '.txt'))
        links = json.load(open(os.path.join(a.out, title + '_links.json'), encoding='utf-8'))
        raw = open(os.path.join(a.out, title + '_links.json'), 'rb').read()
        print('\n== %s: %d lines, %d links' % (title, len(L), len(links)))
        probs = collections.Counter()
        if raw.startswith(b'\xef\xbb\xbf') or b'\r' in raw or not raw.endswith(b'\n') or raw.endswith(b'\n\n'):
            probs['links byte contract'] += 1
        if L[0] != '<h1>%s</h1>' % meta['h1'] or L[1] != meta['author']:
            probs['header'] += 1
        ch = v = 0
        under = {}
        for i, l in enumerate(L[2:], start=3):
            if not l.strip():
                probs['empty line'] += 1
            if '<i>' in l or 'class="footnote' in l:
                probs['<i>/class=footnote'] += 1
            m = re.match(r'<h2>פרק (\S+)</h2>$', l)
            if m:
                n = gem(m.group(1))
                if n <= ch:
                    probs['perek order'] += 1
                ch, v = n, 0
                continue
            m = re.match(r'<h3>פסוק (\S+)</h3>$', l)
            if m:
                n = gem(m.group(1))
                if n <= v:
                    probs['pasuk order'] += 1
                v = n
                continue
            if re.match(r'<h\d', l):
                probs['other heading'] += 1
            under[i] = (ch, v)
            if l.count('<b>') != l.count('</b>') or l.count('<u>') != l.count('</u>'):
                probs['unbalanced tag'] += 1
        src = [r for r in links if r['Conection Type'] == 'source']
        fnl = [r for r in links if r['Conection Type'] == 'footnotes']
        other = [r for r in links if r['Conection Type'] not in ('source', 'footnotes')]
        probs['other link type'] += len(other)
        by = collections.defaultdict(list)
        for r in src:
            by[r['line_index_1']].append(r)
            m = re.match(r'Proverbs (\d+):(\d+)$', r.get('ref_2', ''))
            if not m:
                probs['bad ref_2'] += 1
                continue
            key = (int(m.group(1)), int(m.group(2)))
            dbl, hc, hv = verses[key]
            if r['line_index_2'] != dbl:
                probs['line_index_2 != DB'] += 1
            if r['heRef_2'] != 'משלי %s, %s' % (hc, hv):
                probs['heRef_2 mismatch'] += 1
            if r['path_2'] != 'אוצריא\\תנך\\כתובים\\משלי.txt':
                probs['path_2'] += 1
            if under.get(r['line_index_1'], (None,))[0] != key[0]:
                probs['link to other chapter'] += 1
        for r in links:
            if any(x in r for x in ('line_index_1_end', 'line_index_2_end', 'start', 'end')):
                probs['ranged/anchored'] += 1
            if not all(isinstance(r[x], int) for x in ('line_index_1', 'line_index_2')):
                probs['non-int index'] += 1
            if 'ref_2' in r and r['Conection Type'] == 'footnotes':
                probs['ref_2 on footnotes'] += 1
        dup = sum(len(rs) - len({x['ref_2'] for x in rs}) for rs in by.values())
        probs['duplicate (line,ref)'] += dup
        for i, (c, vv) in under.items():
            rs = by.get(i)
            if not rs:
                probs['unlinked content line'] += 1
                continue
            own = 'Proverbs %d:%d' % (c, vv)
            if vv and own not in {x['ref_2'] for x in rs}:
                probs['own verse not linked'] += 1
        probs['link on heading/header line'] += sum(1 for i in by if i not in under)
        multi = {i: rs for i, rs in by.items() if len(rs) > 1}
        # הערות
        sups = [int(x) for l in L for x in re.findall(r'<sup>(\d+)</sup>', l)]
        if sups != list(range(1, len(sups) + 1)):
            probs['sup sequence'] += 1
        ntitle = NOTES_PREFIX + title
        if sups:
            N = read(os.path.join(a.out, ntitle + '.txt'))
            if N[0] != '<h1>%s</h1>' % ntitle or N[1] != '':
                probs['notes header'] += 1
            for r in fnl:
                num = re.match(r'<sup>(\d+)</sup> ', N[r['line_index_2'] - 1])
                if not num or '<sup>%s</sup>' % num.group(1) not in L[r['line_index_1'] - 1]:
                    probs['footnote link marker mismatch'] += 1
                if r['path_2'] != ntitle + '.txt' or r['heRef_2'] != 'הערות':
                    probs['footnote link fields'] += 1
            if len(fnl) != len(sups):
                probs['footnote link count'] += 1
        probs = {x: n for x, n in probs.items() if n}
        print('   content lines %d | source %d (lines with >1 verse: %d, extra entries %d) | footnotes %d | sups %d'
              % (len(under), len(src), len(multi), len(src) - len(by), len(fnl), len(sups)))
        print('   problems:', probs or 'none')
        bad += bool(probs)

    # ---- 5. חוזה המיזוג
    spec = importlib.util.spec_from_file_location(
        'mc', os.path.join(HERE, '..', 'אוצר ההלכה - סקריפטים', 'merge_contract.py'))
    mc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mc)
    print('\n5. merge contract')
    for k, meta in BOOKS.items():
        if not os.path.exists(os.path.join(a.out, NOTES_PREFIX + meta['title'] + '.txt')):
            print('   %-22s (no notes)' % meta['title'])
            continue
        b = mc.check(a.out, a.out, meta['title'])
        print('   %-22s %s %s' % (meta['title'], 'MERGEABLE' if not b else 'WOULD NOT MERGE', b))
        bad += bool(b)

    if a.scan:
        scan(a.out)
    print('\nRESULT:', 'OK' if not bad else '%d check groups failed' % bad)
    return 1 if bad else 0


SCAN = [r'ג\.פ', r'א\.ה', r'פסוקים', r'הפסוק(?:ים)? ה?ב(?:א|אים)', r'זה והבא', r'והבא אחריו',
        r'המשך', r'ביחד', r'עד סוף', r'מכאן ועד', r'עד פסוק', r'קושר', r'שניהם',
        r'בפסוק הקודם', r'(?:ראה|עיין|עי\') ב?פסוק', r'תמצא ב']


def scan(out):
    print('\n--scan: lines mentioning another verse / a range (candidates for multi-verse)')
    for k, meta in BOOKS.items():
        L = read(os.path.join(out, meta['title'] + '.txt'))
        links = json.load(open(os.path.join(out, meta['title'] + '_links.json'), encoding='utf-8'))
        n = collections.Counter(r['line_index_1'] for r in links if r['Conection Type'] == 'source')
        cand = collections.Counter()
        cand_multi = collections.Counter()
        for i, l in enumerate(L, start=1):
            t = NIK.sub('', re.sub(r'<[^>]+>', '', l))
            hits = [p for p in SCAN if re.search(p, t)]
            for p in hits:
                cand[p] += 1
                cand_multi[p] += n[i] > 1
        print('  %s' % meta['title'])
        for p in SCAN:
            if cand[p]:
                print('     %-32s lines %3d  multi-linked %3d' % (p, cand[p], cand_multi[p]))


if __name__ == '__main__':
    sys.exit(main())
