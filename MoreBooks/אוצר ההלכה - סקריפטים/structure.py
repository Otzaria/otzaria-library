"""Parse Otzar HaHalacha into a structured model anchored to Shulchan Aruch.

Page furniture, from the top:
  * running head  -- "סימן X סעיף Y", the anchor for everything on the page
  * an optional Shulchan Aruch band on a se'if's opening page: the mechaber's
    text, the Rema's glosses, and Be'er HaGolah's lettered notes in the margin
  * the "אוצר ההלכה" band -- two columns, read right column first,
    carrying numbered entries: marker, lemma from the Shulchan Aruch, body,
    and the source work in parentheses
  * the "הערות וציונים" band -- footnotes keyed by a running number
"""
import collections
import os
import re
import sys

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import otzar_extract as ox
from otzar_extract import (collect, profile, learn, line_text,
                           line_segments, is_letter)

OTZAR = 'אוצר ההלכה'
NOTES = 'הערות וציונים'
BEER = 'באר הגולה'
HEAD = re.compile('סימן\\s+([א-ת"״\']+)'
                  '(?:\\s+סעיף\\s+([א-ת"״\']+))?')
# a siman can carry an appendix whose entry numbering restarts at one
EXTRA = re.compile('^(מילואים|השמטות|הוספות)\\s+ל?סימן\\s+([א-ת"״\']+)')
BANNER = re.compile('^(מילואים|השמטות|הוספות)\\b')
# the closing apparatus of a volume: indexes and bibliographies, not halacha
TAIL = re.compile('^(מפתח|רשימת|תוכן|לוח)')
MARKER = re.compile('^([א-ת]{1,4})\\((?:\\s|$)')
COL_SPLIT = 283.0
MARKER_MIN_SIZE = 11.0

VALUES = {'א': 1, 'ב': 2, 'ג': 3, 'ד': 4, 'ה': 5,
          'ו': 6, 'ז': 7, 'ח': 8, 'ט': 9, 'י': 10,
          'כ': 20, 'ך': 20, 'ל': 30, 'מ': 40, 'ם': 40,
          'נ': 50, 'ן': 50, 'ס': 60, 'ע': 70,
          'פ': 80, 'ף': 80, 'צ': 90, 'ץ': 90,
          'ק': 100, 'ר': 200, 'ש': 300, 'ת': 400}


def gematria(s):
    s = re.sub('[^א-ת]', '', s or '')
    return sum(VALUES.get(c, 0) for c in s) if s else None


def load(path):
    doc = pymupdf.open(path)
    ox.SPACE_THRESHOLD = ox.calibrate_space(doc)
    buckets, ref_text, _ = collect(doc)
    table, report = learn(buckets, profile(ref_text))
    by_family = collections.defaultdict(dict)
    for key, (nm, fn) in table.items():
        by_family[key[0]][nm] = fn
    by_family = {f: list(d.items()) for f, d in by_family.items()}
    fallback = {}
    for key, name, sc, n, _ in sorted(report, key=lambda r: r[3]):
        fallback[key[0]] = table[key]

    # a family none of the standard candidates could read is a shuffled
    # mapping; it can be solved against the book's own vocabulary, but that
    # search is slow, so it is opt-in
    if not os.environ.get('OTZAR_SOLVE'):
        return doc, table, fallback, by_family
    from solve_sub import learn_family, lexicon
    missing = collections.Counter()
    for key, texts in buckets.items():
        if key[0] not in by_family:
            missing[key[0]] += len(' '.join(texts))
    lex = None
    for fam, n in missing.most_common():
        if n < 200:
            break
        if lex is None:
            lex = lexicon(doc)
        fn, rate = learn_family(doc, fam, lex)
        if fn is None:
            continue
        by_family[fam] = [('permutation', fn)]
        fallback[fam] = ('permutation', fn)
        table[(fam, 0, 0)] = ('permutation', fn)
        load.solved = getattr(load, 'solved', [])
        load.solved.append((fam, n, rate))
    return doc, table, fallback, by_family


def page_lines(page, table, fallback, by_family, unres):
    out = []
    for blk in page.get_text("rawdict")["blocks"]:
        for ln in blk.get("lines", []):
            segs = line_segments(ln, table, fallback, by_family, unres)
            if not segs:
                continue
            bb = ln["bbox"]
            out.append({
                'y': bb[1], 'x0': bb[0], 'x1': bb[2],
                'page': page.number + 1,
                'sz': max(sp["size"] for sp in ln["spans"]),
                'fonts': {sp["font"].split('+')[-1] for sp in ln["spans"]},
                'text': ' '.join(t for t, _, _ in segs).strip(),
                'segs': segs,
            })
    return out


def merge_fragments(lines):
    """Rejoin line fragments the print file split mid-word.

    An entry number such as "שט(" can arrive as two separate lines sitting
    side by side, which hides the marker from the matcher.
    """
    out = []
    for ln in sorted(lines, key=lambda l: (round(l['y'] / 2), -l['x0'])):
        if out:
            prev = out[-1]
            same_row = abs(prev['y'] - ln['y']) < 2.0
            same_col = (prev['x0'] >= COL_SPLIT) == (ln['x0'] >= COL_SPLIT)
            touching = abs(prev['x0'] - ln['x1']) < 2.0
            if same_row and same_col and touching and \
                    abs(prev['sz'] - ln['sz']) < 1.5:
                prev['text'] += ln['text']
                prev['segs'] = prev['segs'] + ln['segs']
                prev['x0'] = ln['x0']
                prev['fonts'] |= ln['fonts']
                continue
        out.append(dict(ln))
    return out


def _rows(lines, tol=4.0):
    """Group a column's lines into visual rows, each ordered right to left.

    A row often mixes sizes -- an inline citation sits a point or two lower
    than the prose around it -- so ordering by y alone scrambles the sentence.
    """
    out, cur = [], []
    for l in sorted(lines, key=lambda l: l['y']):
        if cur and l['y'] - cur[0]['y'] > tol:
            out.extend(sorted(cur, key=lambda l: -l['x0']))
            cur = []
        cur.append(l)
    out.extend(sorted(cur, key=lambda l: -l['x0']))
    return out


def reading_order(lines):
    """Two columns, right one first; within a column, row by row."""
    return (_rows([l for l in lines if l['x0'] >= COL_SPLIT]) +
            _rows([l for l in lines if l['x0'] < COL_SPLIT]))


def band_font(pages):
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
    return c.most_common(1)[0][0] if c else (None, 12.0)


def is_marker(line, body_font=None):
    m = MARKER.match(line['text'].strip())
    if not m or line['sz'] < MARKER_MIN_SIZE:
        return None
    # the number is set in the display face; body-face text that merely opens
    # with a letter and a bracket is a citation, not an entry
    if body_font and line['segs'] and line['segs'][0][1] == body_font:
        return None
    # the number sits hard against the right edge of its column
    edge = 538.5 if line['x0'] >= COL_SPLIT else 275.0
    if abs(line['x1'] - edge) > 8:
        return None
    return m.group(1)


def parse(path, page_limit=None):
    doc, table, fallback, by_family = load(path)
    unres = collections.Counter()
    pages, siman, seif, section = [], None, None, None
    tail = False
    for i, page in enumerate(doc):
        if page_limit and i >= page_limit:
            break
        lines = merge_fragments(page_lines(page, table, fallback,
                                           by_family, unres))
        lines.sort(key=lambda l: l['y'])
        head = None
        for l in lines[:5]:
            if l['sz'] <= 14:
                continue
            m = EXTRA.match(l['text'].strip())
            if m:
                siman, seif, section = m.group(2), None, m.group(1)
                head = m
                break
            m = HEAD.search(l['text'])
            if m:
                siman, seif, section = m.group(1), m.group(2), None
                head = m
                break
        # once the halachic body ends the volume prints its indexes, which
        # carry no running head of their own and must not join the last entry
        top = [l for l in lines[:6] if l['sz'] > 14]
        titled = any(HEAD.search(l['text']) or EXTRA.match(l['text'].strip())
                     for l in top)
        if siman is not None and not titled:
            if top and any(TAIL.match(l['text'].replace(' ', '')) for l in top):
                tail = True
            elif not top:
                tail = True
        if tail:
            pages.append({'page': i + 1, 'siman': None, 'seif': None,
                          'section': None, 'lines': [], 'otzar_y': None,
                          'notes_y': None, 'has_sa': False})
            continue
        otzar_y = next((l['y'] for l in lines if l['text'].strip() == OTZAR), None)
        notes_y = next((l['y'] for l in lines if l['text'].strip() == NOTES), None)
        pages.append({
            'page': i + 1, 'siman': siman, 'seif': seif,
            'section': section, 'lines': lines,
            'otzar_y': otzar_y, 'notes_y': notes_y,
            'has_sa': any(l['text'].strip() == BEER for l in lines),
        })
    return doc, pages, unres


def entries(pages):
    """Walk the Otzar band and cut it into numbered entries.

    A siman can open an appendix whose numbering restarts at one. It is
    announced either by the running head or by a banner part-way down a page,
    so both are watched for.
    """
    body_font = band_font(pages)[0]
    out, cur, section = [], None, None
    prev, prev_key = 0, None
    rejected, misprint = [], []
    for pg in pages:
        if pg['section'] != section:
            # an appendix may reprint a whole work with no entry numbers of
            # its own; closing the open entry keeps it from swallowing that
            section = pg['section']
            cur = None
            prev, prev_key = 0, None
        if pg['otzar_y'] is None or pg['siman'] is None:
            continue
        lo = pg['otzar_y']
        hi = pg['notes_y'] if pg['notes_y'] is not None else 10 ** 6
        band = [l for l in pg['lines'] if lo < l['y'] < hi]
        # an appendix banner runs across both columns, so it splits the band
        # by height rather than taking its place in one column's flow
        cuts = sorted(l['y'] for l in band
                      if l['sz'] > 15 and BANNER.match(l['text'].strip()))
        ordered, prev_y = [], lo
        for cut in cuts + [hi]:
            part = [l for l in band if prev_y < l['y'] < cut]
            ordered.append((part, cut if cut != hi else None))
            prev_y = cut
        flat = []
        for part, cut in ordered:
            flat.extend(reading_order(part))
            if cut is not None:
                flat.append(next(l for l in band if l['y'] == cut))
        for l in flat:
            m = BANNER.match(l['text'].strip()) if l['sz'] > 15 else None
            if m:
                section = m.group(1)
                cur = None
                prev, prev_key = 0, None
                continue
            mk = is_marker(l, body_font)
            if mk:
                key = (pg['siman'], section)
                if key != prev_key:
                    prev, prev_key = 0, key
                # entry numbers only ever climb, so a marker that would step
                # backwards is a lettered sub-list inside the current entry
                n = gematria(mk)
                if n < prev:
                    rejected.append((pg['page'], mk, prev))
                    if cur is not None:
                        cur['lines'].append(l)
                    continue
                if n == prev:            # the print repeats a number now and
                    n = prev + 1         # then; the run says what was meant
                    misprint.append((pg['page'], mk, n))
                prev = n
                cur = {'num': mk, 'n': n, 'siman': pg['siman'],
                       'seif': pg['seif'], 'section': section,
                       'page': pg['page'], 'lines': []}
                out.append(cur)
            elif cur is not None:
                cur['lines'].append(l)
            elif section:
                # unnumbered appendix prose still belongs to the book
                cur = {'num': None, 'n': 0, 'siman': pg['siman'],
                       'seif': pg['seif'], 'section': section,
                       'page': pg['page'], 'lines': [l]}
                out.append(cur)
    entries.rejected = rejected
    entries.misprint = misprint
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/david/Downloads/אוצר ההלכה שבת א.pdf"
    doc, pages, unres = parse(path)
    ents = entries(pages)
    by_siman = collections.OrderedDict()
    for e in ents:
        key = e['siman'] + ('/' + e['section'] if e['section'] else '')
        by_siman.setdefault(key, []).append(e)
    print('%-7s %7s %7s  %s' % ('siman', 'count', 'max', 'sequence check'))
    total_bad = 0
    for s, items in by_siman.items():
        nums = [e['n'] for e in items]
        breaks = [(i, nums[i - 1], nums[i]) for i in range(1, len(nums))
                  if nums[i] != nums[i - 1] + 1]
        total_bad += len(breaks)
        print('%-7s %7d %7d  breaks=%-3d %s'
              % (s, len(items), max(nums), len(breaks),
                 breaks[:4] if breaks else 'clean'))
    print('\nentries: %d   sequence breaks: %d   sub-list markers ignored: %d'
          % (len(ents), total_bad, len(getattr(entries, 'rejected', []))))
    print('repeated numbers in the print, renumbered: %d'
          % len(getattr(entries, 'misprint', [])))


if __name__ == '__main__':
    main()
