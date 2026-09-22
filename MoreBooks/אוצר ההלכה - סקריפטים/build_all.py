"""Build the Otzaria deliverables for Otzar HaHalacha.

Per volume: the book file, and the links sidecar that anchors every entry to
its se'if in Shulchan Aruch Orach Chaim.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structure import parse, entries, gematria
from notes import notes_of
from render import band_style, render_entry

REPO = '/Users/david/Documents/otzaria-books/otzaria-library'
SA_PATH = os.path.join(
    REPO, 'extraBooks/SefariaToOtzria/sefaria_export/ספרים/'
    'אוצריא/הלכה/שולחן ערוך/'
    'שולחן ערוך, אורח חיים.txt')
SA_TITLE = 'שולחן ערוך, אורח חיים'
SA_REF = 'Shulchan Arukh, Orach Chayim '
AUTHOR = 'מכון "איש מצליח"'

H2 = re.compile(r'^<h2>סימן ([א-ת]+)</h2>$')
SEIF = re.compile(r'^\(([א-ת]{1,3})\)')


def sa_index():
    """Index the Shulchan Aruch: se'if line numbers, and each siman's spelling.

    The spelling matters: this corpus writes 272 as ער"ב and 298 as רח"צ,
    avoiding the words those letters would otherwise spell. Taking the headings
    from the Shulchan Aruch file keeps the two books reading alike.
    """
    idx, names, siman = {}, {}, None
    with open(SA_PATH, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip('\n')
            m = H2.match(line)
            if m:
                siman = gematria(m.group(1))
                names[siman] = m.group(1)
                continue
            m = SEIF.match(line)
            if m and siman:
                idx.setdefault((siman, gematria(m.group(1))), n)
    return idx, names


def heb_num(n):
    """Plain gematria, the spelling the corpus uses in headings."""
    out, rest = [], n
    for val, sign in ((400, 'ת'), (300, 'ש'), (200, 'ר'),
                      (100, 'ק'), (90, 'צ'), (80, 'פ'),
                      (70, 'ע'), (60, 'ס'), (50, 'נ'),
                      (40, 'מ'), (30, 'ל'), (20, 'כ'),
                      (10, 'י'), (9, 'ט'), (8, 'ח'),
                      (7, 'ז'), (6, 'ו'), (5, 'ה'),
                      (4, 'ד'), (3, 'ג'), (2, 'ב'), (1, 'א')):
        while rest >= val:
            out.append(sign)
            rest -= val
    s = ''.join(out)
    return s.replace('יה', 'טו').replace(
        'יו', 'טז')


NOTES_PREFIX = 'הערות על '


def build(path, title, sa, names, report):
    doc, pages, unres = parse(path)
    body_font, body_size = band_style(pages)
    notes, by_page, _ = notes_of(pages)
    called = set()
    ents = entries(pages)
    counts = collections.Counter()

    notes_title = NOTES_PREFIX + title
    lines = ['<h1>%s</h1>' % title, AUTHOR]
    # The notes are their own book, which the DB generator merges back into
    # the base book as inline footnotes (HearotCompanionMerge). That merge is
    # all-or-nothing: one non-heading line the links file does not reference
    # and the whole volume stays standalone, so this file carries headings and
    # linked notes and nothing else -- no byline.
    nlines = ['<h1>%s</h1>' % notes_title]
    path, written = [], []
    links = []
    sn = fn = None
    section = object()
    for e in ents:
        n_siman = gematria(e['siman'])
        n_seif = gematria(e['seif']) if e['seif'] else None
        if n_siman != sn:
            # the same siman can be spelled two ways across the volume, so the
            # number is what groups it and the Shulchan Aruch supplies the name
            sn, fn, section = n_siman, None, object()
            lines.append('<h2>סימן %s</h2>' % names.get(sn, e['siman']))
            path = ['<h2>סימן %s</h2>' % names.get(sn, e['siman'])]
        if e['section'] != section:
            section = e['section']
            fn = None
            if section:
                lines.append('<h3>%s</h3>' % section)
                path = path[:1] + ['<h3>%s</h3>' % section]
        if not section and n_seif != fn:
            fn = n_seif
            lines.append('<h3>סעיף %s</h3>' % heb_num(fn or 1))
            path = path[:1] + ['<h3>סעיף %s</h3>' % heb_num(fn or 1)]
        sink = []
        lines.append(render_entry(e, notes, by_page, body_font, body_size,
                                  counts, called, sink))
        for n, body in sink:
            if path != written:
                i = 0
                while i < len(written) and i < len(path) \
                        and written[i] == path[i]:
                    i += 1
                nlines.extend(path[i:])
                written = list(path)
            if '<i>' in body or '<i ' in body or '</i>' in body:
                report['italic_notes'] += 1
            nlines.append('<sup>%d</sup> %s' % (n, body))
            links.append({
                'line_index_1': len(lines),
                'heRef_2': 'הערות',
                'path_2': notes_title + '.txt',
                'line_index_2': len(nlines),
                'Conection Type': 'footnotes',
            })
        target = sa.get((sn, n_seif or 1))
        if target is None:
            report['no_sa_target'].add((e['siman'], e['seif']))
            continue
        links.append({
            'line_index_1': len(lines),
            'line_index_2': target,
            'heRef_2': '%s %s, %s' % (SA_TITLE, names.get(sn, e['siman']),
                                      heb_num(n_seif or 1)),
            'path_2': SA_TITLE + '.txt',
            'ref_2': '%s%d:%d' % (SA_REF, sn, n_seif or 1),
            'Conection Type': 'source',
        })
    # a handful of notes carry no call anywhere in the body; they are appended
    # so nothing printed in the book is dropped, and after the links are fixed
    # so the line numbers already issued stay valid
    stray = [(s, n) for s in sorted(notes) for n in sorted(notes[s])
             if (s, n) not in called and notes[s][n]]
    if stray:
        # these have no call to anchor them, so they cannot be linked -- and an
        # unlinked line in the notes file would veto the merge. They go at the
        # end of the base book instead, where nothing printed is lost.
        lines.append('<h2>הערות ללא ציון בגוף</h2>')
        for s, n in stray:
            lines.append('<b>סימן %s הערה %d.</b> %s'
                         % (names.get(s, heb_num(s)), n, notes[s][n]))
        report['stray_notes'] += len(stray)

    report['entries'] += len(ents)
    report['notes'] += sum(len(v) for v in notes.values())
    report['calls'] += counts['calls']
    report['orphan'] += counts['orphan_call']
    report['links'] += len(links)
    report['note_lines'] += sum(1 for l in nlines if l.startswith('<sup>'))
    return lines, nlines, links, notes_title, unres


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/tmp/claude-501/out')
    ap.add_argument('--vols', default='א,ג,ד,ה,ו')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sa, names = sa_index()
    print('Shulchan Aruch index: %d se\'if lines, %d simanim'
          % (len(sa), len(names)))
    report = collections.Counter()
    report['no_sa_target'] = set()
    for vol in a.vols.split(','):
        src = '/Users/david/Downloads/אוצר ההלכה שבת %s.pdf' % vol
        title = ('אוצר ההלכה על שולחן '
                 'ערוך אורח חיים חלק %s' % vol)
        lines, nlines, links, ntitle, unres = build(
            src, title, sa, names, report)
        for name, body in ((title, lines), (ntitle, nlines)):
            with open(os.path.join(a.out, name + '.txt'), 'w',
                      encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(body) + '\n')
        with open(os.path.join(a.out, title + '_links.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(links, f, ensure_ascii=False, indent=1)
        print('%-52s lines=%-6d notes=%-6d links=%-6d unresolved=%d'
              % (title, len(lines), len(nlines), len(links),
                 sum(unres.values())))
    print('\nentries %d | notes %d | footnote calls %d (orphaned %d) | '
          'links %d | note lines %d'
          % (report['entries'], report['notes'], report['calls'],
             report['orphan'], report['links'], report['note_lines']))
    if report['italic_notes']:
        print('NOTES CARRYING <i> MARKUP (would veto the merge): %d'
              % report['italic_notes'])
    print('notes with no call in the body, appended to the base book: %d'
          % report['stray_notes'])
    if report['no_sa_target']:
        print('no Shulchan Aruch target for:',
              sorted(report['no_sa_target'])[:10])


if __name__ == '__main__':
    main()
