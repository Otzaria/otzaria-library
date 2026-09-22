"""Parse the "הערות וציונים" band and check its numbering runs clean."""
import collections
import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from structure import parse, reading_order, gematria, COL_SPLIT

NOTE_MARK = re.compile(r'(?<![\d])(\d{1,3})\s*\.')


def band_rows(pg):
    if pg['notes_y'] is None:
        return []
    return [l for l in pg['lines'] if l['y'] > pg['notes_y'] + 4]


def body_style(pages):
    """The (font, size) most of the note prose is set in."""
    c = collections.Counter()
    for pg in pages:
        for l in band_rows(pg):
            for t, f, z in l['segs']:
                c[(f, z)] += len(t)
    return c.most_common(1)[0][0] if c else None


def _by_row(rows):
    """Notes laid out as a grid: rows down the page, right to left in a row."""
    rows = sorted(rows, key=lambda l: l['y'])
    out, cur = [], [rows[0]]
    for l in rows[1:]:
        if l['y'] - cur[-1]['y'] > 6:
            out.extend(sorted(cur, key=lambda l: -l['x0']))
            cur = []
        cur.append(l)
    out.extend(sorted(cur, key=lambda l: -l['x0']))
    return out


def _tag(rows, body):
    parts = []
    for l in rows:
        for t, f, z in l['segs']:
            digits = re.sub(r'[\s.]', '', t)
            mark = (f, z) != body and digits.isdigit() and 0 < len(digits) < 4
            parts.append((t, mark))
    return parts


def _descents(parts):
    nums = [int(re.sub(r'[\s.]', '', t)) for t, m in parts if m]
    return sum(1 for a, b in zip(nums, nums[1:]) if b <= a)


def flow(rows, body):
    """Order a page's notes band.

    Some volumes set the notes as a grid of short cells, others as two plain
    columns, and the two orders disagree. The numbering settles it: whichever
    reading produces the more ascending run of note numbers is the right one.
    """
    if not rows:
        return []
    row_first = _tag(_by_row(rows), body)
    col_first = _tag(reading_order(rows), body)
    return col_first if _descents(col_first) < _descents(row_first) else row_first


def notes_of(pages):
    """Returns {siman: {number: text}}, {page: {number: text}}, and the runs.

    The page map is what callers should prefer: the notes band sits at the foot
    of the very page that calls into it, so a number is unambiguous there even
    where a siman runs several independently numbered sets of notes.
    """
    out = collections.defaultdict(dict)
    by_page = collections.defaultdict(dict)
    order = collections.defaultdict(list)
    carry_siman, carry_num, carry_txt = None, None, []
    carry_page = None
    body = body_style(pages)
    for pg in pages:
        for text, mark in flow(band_rows(pg), body):
            if mark:
                if carry_num is not None:
                    body = ' '.join(carry_txt).strip()
                    out[carry_siman][carry_num] = body
                    by_page[carry_page][carry_num] = body
                    order[carry_siman].append(carry_num)
                carry_siman = gematria(pg['siman'])
                carry_page = pg['page']
                carry_num = int(re.sub(r'[\s.]', '', text))
                carry_txt = []
            elif carry_num is not None and text.strip():
                carry_txt.append(text.strip())
    if carry_num is not None:
        body = ' '.join(carry_txt).strip()
        out[carry_siman][carry_num] = body
        by_page[carry_page][carry_num] = body
        order[carry_siman].append(carry_num)
    _split_runons(out, order)
    return out, by_page, order


def _split_runons(out, order):
    """Recover a note whose number was set in the prose face.

    Such a number is invisible to the face test and its note ends up glued to
    the end of the one before it -- but the run says which number is missing,
    and it is still there in the text, so the join can be undone.
    """
    for siman, seq in order.items():
        fixed = []
        for i, n in enumerate(seq):
            fixed.append(n)
            nxt = seq[i + 1] if i + 1 < len(seq) else None
            while nxt != n + 1:
                m = re.search(r'(?<!\d)%d\s*\.' % (n + 1), out[siman][n])
                if not m:
                    break
                head = out[siman][n][:m.start()].strip()
                tail = out[siman][n][m.end():].strip()
                out[siman][n] = head
                n += 1
                out[siman][n] = tail
                fixed.append(n)
        order[siman] = fixed


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/david/Downloads/אוצר ההלכה שבת א.pdf"
    doc, pages, unres = parse(path)
    notes, by_page, order = notes_of(pages)
    print('%-7s %6s %6s  %s' % ('siman', 'notes', 'max', 'sequence'))
    for s, seq in order.items():
        breaks = [(seq[i - 1], seq[i]) for i in range(1, len(seq))
                  if seq[i] != seq[i - 1] + 1]
        print('%-7s %6d %6d  breaks=%-3d %s'
              % (s, len(seq), max(seq), len(breaks),
                 breaks[:4] if breaks else 'clean'))
    tot = sum(len(v) for v in notes.values())
    empty = sum(1 for v in notes.values() for t in v.values() if not t)
    print('\nnotes: %d   empty: %d' % (tot, empty))
    s0 = list(order)[0]
    for n in sorted(notes[s0])[:4]:
        print('  [%s %d] %s' % (s0, n, notes[s0][n][:90]))


if __name__ == '__main__':
    main()
