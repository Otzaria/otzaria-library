#!/usr/bin/env python3
"""כמה מהקובץ הקיים 'רבינו יונה על משלי.txt' מכוסה ע"י רבנו יונה שבקובץ ה-docx.

מדפיס סטטיסטיקה בלבד (חפיפת טוקנים ו-5-grams, ופסוקים שאינם ב-docx).
שימוש: coverage_old_yonah.py <parsed.json> <old.txt>
"""
import collections
import json
import re
import sys

HEB = re.compile(r'[֑-ׇ]')


def toks(s):
    s = re.sub(r'<[^>]+>|\x00FN\d+\x00', ' ', s)
    s = HEB.sub('', s).replace('״', '"').replace('׳', "'")
    s = re.sub(r'["\']', '', s)
    return re.findall(r'[א-ת]+', s)


def main(pj, old):
    d = json.load(open(pj, encoding='utf-8'))
    new = []
    newverses = set()
    for c in d['chapters']:
        for p in c['pesukim']:
            if p['ry']:
                newverses.add((c['perek'], p['pasuk']))
            for e in p['ry']:
                new += toks(e['html'])
    L = open(old, encoding='utf-8-sig').read().split('\n')
    body, oldverses, ch = [], set(), None
    per_verse = collections.defaultdict(list)
    cur = None
    for l in L[2:]:
        m = re.match(r'<h2>פרק (\S+)</h2>', l)
        if m:
            ch = m.group(1); continue
        m = re.match(r'<h3>פסוק (\S+)</h3>', l)
        if m:
            cur = (ch, m.group(1)); oldverses.add(cur); continue
        if re.match(r'<h\d', l):
            continue
        t = toks(l)
        body += t
        per_verse[cur] += t
    nc = collections.Counter(new)
    oc = collections.Counter(body)
    inter = sum(min(v, nc[k]) for k, v in oc.items())
    print('old tokens %d, docx-yonah tokens %d' % (len(body), len(new)))
    print('old token multiset covered by docx: %.2f%%' % (100 * inter / max(1, len(body))))
    grams = lambda t: {tuple(t[i:i + 5]) for i in range(len(t) - 4)}
    ng = grams(new)
    og = [tuple(body[i:i + 5]) for i in range(len(body) - 4)]
    print('old 5-grams found in docx: %.2f%%' % (100 * sum(g in ng for g in og) / max(1, len(og))))
    print('old verses %d, new verses %d, old-not-in-new %d: %s'
          % (len(oldverses), len(newverses), len(oldverses - newverses),
             sorted(oldverses - newverses)[:20]))
    low = []
    for v, t in per_verse.items():
        g = [tuple(t[i:i + 5]) for i in range(len(t) - 4)]
        if len(g) >= 5:
            r = sum(x in ng for x in g) / len(g)
            if r < 0.8:
                low.append((v, len(t), round(r, 2)))
    print('verses of old file with <80%% 5-gram cover: %d %s' % (len(low), low[:30]))
    print('old non-verse tokens (before first verse):', len(per_verse.get(None, [])))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
