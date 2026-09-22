"""Turn parsed entries into Otzaria book lines.

One entry becomes one physical line, because a line is Otzaria's addressing
unit: links, bookmarks and notes all point at a line number.
"""
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structure import (parse, entries, reading_order, is_marker, gematria,
                       OTZAR, NOTES)
from notes import notes_of

# The note stays out of the line. Otzaria's own convention for a book that
# came with its own apparatus is a second book -- "הערות על X" -- reached by a
# links record of type "footnotes", so the reader gets the note in the
# commentary pane instead of a tooltip buried in the prose.
CALL = '<sup>%d</sup>'


def band_style(pages):
    """The (font, size) the Otzar HaHalacha prose is set in."""
    c = collections.Counter()
    for pg in pages:
        if pg['otzar_y'] is None:
            continue
        hi = pg['notes_y'] if pg['notes_y'] is not None else 10 ** 6
        for l in pg['lines']:
            if pg['otzar_y'] < l['y'] < hi:
                for t, f, z in l['segs']:
                    c[(f, z)] += len(t)
    return c.most_common(1)[0][0]


def classify(seg, body_font, body_size):
    """head (the lemma and its number), note (a footnote call), src, or body."""
    t, f, z = seg
    digits = re.sub(r'[\s.]', '', t)
    if digits.isdigit() and 0 < len(digits) < 4 and z < body_size * 0.65:
        return 'note'
    if f != body_font:
        return 'head' if z >= body_size - 1.5 else 'src'
    return 'body'


def render_entry(ent, notes, by_page, body_font, body_size, counts,
                 called=None, sink=None):
    """Render one entry.

    ``sink``, when given, receives ``(number, text)`` for every note this
    entry calls, in the order the calls appear; the entry itself keeps only
    the marker.
    """
    head, parts, seen = [], [], set()
    for l in ent['lines']:
        page = l.get('page', ent['page'])
        for seg in l['segs']:
            kind = classify(seg, body_font, body_size)
            t = seg[0].strip()
            if not t:
                continue
            if kind == 'note':
                n = int(re.sub(r'[\s.]', '', t))
                if n in seen:            # the file redraws the call to fake bold
                    continue
                seen.add(n)
                # the band that answers a call sits at the foot of the page
                # the call is on, so resolve there first
                key = gematria(ent['siman'])
                body = by_page.get(page, {}).get(n)
                if body is None:
                    body = notes.get(key, {}).get(n)
                if body is not None and called is not None:
                    called.add((key, n))
                counts['calls'] += 1
                parts.append(CALL % n)
                if body:
                    if sink is not None:
                        sink.append((n, body))
                    counts['linked'] += 1
                else:
                    counts['orphan_call'] += 1
            elif kind == 'head' and not parts:
                head.append(t)
            elif kind == 'src':
                parts.append('<b>%s</b>' % t)
            else:
                parts.append(t)
    # the se'if is already the enclosing heading, so only "שם" and the lemma
    # are worth repeating on the entry itself
    head = [h for h in head
            if not re.fullmatch(r'סעיף\s+[א-ת]{1,3}[\'׳״"]?', h)]
    if ent['num'] is None:
        lead = ' '.join(head)
    elif head:
        lead = '%s) %s' % (ent['num'], ' '.join(head))
    else:
        lead = '%s)' % ent['num']
    if not lead.strip():
        return re.sub(r'\s+([.,:;])', r'\1', ' '.join(parts)).strip()
    text = re.sub(r'\s+([.,:;])', r'\1', ' '.join(parts))
    return '<b>%s</b> %s' % (lead.strip(), text.strip())


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/david/Downloads/אוצר ההלכה שבת א.pdf"
    doc, pages, unres = parse(path)
    body_font, body_size = band_style(pages)
    print('body style: %s %.1f' % (body_font, body_size))
    notes, by_page, order = notes_of(pages)
    ents = entries(pages)
    counts = collections.Counter()
    for e in ents[:3] + ents[300:302]:
        print('\n--- סימן %s סעיף %s  עמוד %d'
              % (e['siman'], e['seif'], e['page']))
        print(render_entry(e, notes, by_page, body_font, body_size,
                           counts)[:700])
    counts.clear()
    for e in ents:
        render_entry(e, notes, by_page, body_font, body_size, counts)
    print('\nfootnote calls: %d  resolved: %d  orphaned: %d'
          % (counts['calls'], counts['linked'], counts['orphan_call']))
    called = set()
    for e in ents:
        render_entry(e, notes, by_page, body_font, body_size,
                     collections.Counter(), called)
    total_notes = sum(len(v) for v in notes.values())
    unused = [(s, n) for s in notes for n in notes[s] if (s, n) not in called]
    print('notes defined: %d  never called: %d' % (total_notes, len(unused)))


if __name__ == '__main__':
    main()
