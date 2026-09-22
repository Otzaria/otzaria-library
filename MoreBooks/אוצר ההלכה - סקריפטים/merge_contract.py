"""Check a volume against HearotCompanionMerge's all-or-nothing contract.

The DB generator folds "הערות על X" back into X as inline footnotes, but only
if the pair is clean: every non-heading line of the notes file is referenced by
a links record, no note carries <i> markup, no base line already has inline
footnotes, and every note's leading marker finds an unconsumed twin in its base
line. One violation and the whole volume silently stays a separate book, so the
check belongs here rather than in a DB log.
"""
import json
import os
import re
import sys

HEADING = re.compile(r'^﻿?<h[1-6]', re.I)
NOTE_SUP = re.compile(r'^﻿?<sup(?:\s[^>]*)?>([^<]+)</sup>\s*')
PREFIX = 'הערות על '


def anchors(line, token):
    esc = re.escape(token)
    out = []
    for pat in (r'<sup>%s</sup>' % esc,
                r'<sup\s[^>]*>%s</sup>' % esc,
                r'<small\s[^>]*>\s*%s\s*</small>' % esc):
        out += [m.span() for m in re.finditer(pat, line)]
    return sorted(out)


def check(book_dir, links_dir, title):
    base = open(os.path.join(book_dir, title + '.txt'),
                encoding='utf-8').read().split('\n')
    recs = json.load(open(os.path.join(links_dir, title + '_links.json'),
                          encoding='utf-8'))
    foot = [r for r in recs if r['Conection Type'] == 'footnotes']
    if not foot:
        return ['no footnotes records']
    ntitle = os.path.splitext(foot[0]['path_2'])[0]
    bad = []
    if not ntitle.startswith(PREFIX):
        bad.append('companion title %r lacks the %r prefix' % (ntitle, PREFIX))
    notes = open(os.path.join(book_dir, ntitle + '.txt'),
                 encoding='utf-8').read().split('\n')
    ref = {r['line_index_2'] - 1 for r in foot}
    unlinked = [j + 1 for j, l in enumerate(notes)
                if j not in ref and l.strip() and not HEADING.match(l)]
    if unlinked:
        bad.append('%d unlinked note lines, first at %d'
                   % (len(unlinked), unlinked[0]))
    for j in sorted(ref):
        if not (0 <= j < len(notes)):
            bad.append('link out of range: note line %d' % (j + 1))
            continue
        n = notes[j]
        if not n.strip():
            bad.append('linked blank note line %d' % (j + 1))
        if '<i>' in n or '<i ' in n or '</i>' in n:
            bad.append('note line %d carries <i> markup' % (j + 1))
        if HEADING.match(n):
            bad.append('linked heading note line %d' % (j + 1))
    # every note must find its own unconsumed marker in the base line
    per = {}
    for r in sorted(foot, key=lambda r: r['line_index_2']):
        per.setdefault(r['line_index_1'] - 1, []).append(r['line_index_2'] - 1)
    unanchored = 0
    for i, js in per.items():
        if not (0 <= i < len(base)):
            bad.append('link out of range: base line %d' % (i + 1))
            continue
        if 'class="footnote' in base[i]:
            bad.append('base line %d already carries inline footnotes' % (i + 1))
        used = []
        for j in js:
            m = NOTE_SUP.match(notes[j])
            if not m:
                unanchored += 1
                continue
            free = [a for a in anchors(base[i], m.group(1)) if a not in used]
            if free:
                used.append(free[0])
            else:
                unanchored += 1
    if unanchored:
        bad.append('%d notes would be appended, not anchored' % unanchored)
    if any(r.get('start') is not None for r in recs):
        bad.append('word-anchored links present')
    if any('line_index_1_end' in r or 'line_index_2_end' in r for r in recs):
        bad.append('ranged links present')
    return bad


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else '/Users/david/otzar-out2'
    titles = sorted(os.path.splitext(f)[0] for f in os.listdir(src)
                    if f.endswith('_links.json'))
    titles = [t[:-len('_links')] for t in titles]
    fail = 0
    for t in titles:
        bad = check(src, src, t)
        print('%-52s %s' % (t, 'MERGEABLE' if not bad else 'WOULD NOT MERGE'))
        for b in bad:
            print('    - %s' % b)
        fail += bool(bad)
    print('\n%d of %d volumes merge cleanly' % (len(titles) - fail, len(titles)))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
