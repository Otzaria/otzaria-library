"""Build the Otzaria files of שו"ת משנה הלכות from the tshuvos.com scrape.

Inputs (all produced and verified earlier in this session):
  --src            the scraped volumes (משנה הלכות חלק X.txt, CRLF)
  structure_plan   printed numbering, sections, splits, deletions, joins,
                   topic lines -- everything derived from the printed PDF
  lost_chars       letters the site lost in windows-1255, restored from the PDF
  missing_simanim  whole simanim the site lacks, extracted from the PDF

Output: --out/שות משנה הלכות חלק X.txt (LF).
"""
import argparse
import json
import os
import re

VOLS = ['א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט', 'י',
        'יא', 'יב', 'יג', 'יד', 'טו', 'טז', 'יז']
VOL_NUM = {v: i + 1 for i, v in enumerate(VOLS)}
AUTHOR_LINE = 'רבי מנשה קליין'
# lines of the PDF-extracted simanim set in the printed topic font
# (DWVilna Bold 12.7): the opening topic, plus sub-headings inside 16:137
MISSING_BOLD = {'12:403': {0}, '16:136': {0, 4},
                '16:137': {0, 1, 19, 22, 31}, '17:73': {0, 1}}

ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט']
TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ']
HUNDREDS = ['', 'ק', 'ר', 'ש', 'ת', 'תק', 'תר', 'תש', 'תת', 'תתק']


def gematria(n):
    assert 0 < n < 1000, n
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    if rest == 15:
        return HUNDREDS[h] + 'טו'
    if rest == 16:
        return HUNDREDS[h] + 'טז'
    return HUNDREDS[h] + TENS[t] + ONES[o]


def normalize(s):
    # the site writes geresh as a backtick in volumes א-טז
    s = s.replace('`', "'").replace('’', "'")
    s = re.sub('[‎‏‪-‮]', '', s)
    return re.sub(' {2,}', ' ', s).strip()


def build_volume(vol, src, plan, lost, missing):
    P = plan[vol]
    path = os.path.join(src, 'משנה הלכות חלק %s.txt' % vol)
    raw = open(path, encoding='utf-8').read().splitlines()
    text = {i + 1: l for i, l in enumerate(raw)}   # 1-based, as in the plan

    # 1. literal prefix edits (before the letter fixes: a stripped prefix
    #    may itself hold the lost letters)
    edited = set()
    for e in P['line_edits']:
        assert e['action'] == 'strip_prefix'
        assert text[e['line']].startswith(e['prefix']), e
        text[e['line']] = text[e['line']][len(e['prefix']):]
        edited.add(e['line'])
    # 2. letters lost in windows-1255
    for r in lost.get(vol, []):
        ln, old, new = r['line'], r['old'], r['new']
        assert new is not None, r
        if ln in edited:
            assert '?' not in text[ln], (vol, ln)
            continue
        assert text[ln].count(old) == 1, (vol, ln, old)
        text[ln] = text[ln].replace(old, new)
    # 3. deletions
    deleted = {d['line'] for d in P['delete_lines']}
    for ln in deleted:
        assert not text[ln].startswith('<h'), (vol, ln)

    h2_lines = {m['file_line']: m['printed'] for m in P['siman_map']}
    for ln in h2_lines:
        assert text[ln].startswith('<h2>'), (vol, ln)

    # 4. joins: the printed paragraph runs on across the site's line break
    join_after = {j['line'] for j in P['joins']}
    join_after |= {j['line'] for j in P['joins_extra']
                   if j.get('kind') == 'mid_sentence'}
    join_after -= {ln for ln in join_after
                   if ln in deleted or ln + 1 in deleted
                   or ln in h2_lines or ln + 1 in h2_lines}

    # body units: [first original line, text, last original line];
    # text None marks a site <h2>
    units = []
    absorbed = set()
    for ln in range(3, len(raw) + 1):
        if ln in h2_lines:
            units.append([ln, None, ln])
            continue
        if ln in deleted:
            continue
        prev = units[-1] if units else None
        if prev and prev[1] is not None and prev[2] == ln - 1 \
                and (ln - 1) in join_after:
            prev[1] = prev[1] + ' ' + text[ln]
            prev[2] = ln
            absorbed.add(ln)
            continue
        units.append([ln, text[ln], ln])

    # 5. topic lines -> <b>
    bold = set()
    for s in P['subject_line']:
        m = s.get('match')
        if s.get('partial') or m is None:
            continue
        if m in ('exact', 'exact_after_line_edit', 'multi_line_joined', 'fuzzy'):
            if m == 'fuzzy' and s.get('ratio', 0) < 0.8:
                continue
            bold.add(s['line'])
        elif m == 'multi_line':
            bold.update(s['lines'])
    bold -= absorbed

    splits = {s['file_line']: s['printed'] for s in P['splits']}
    sections = {s['before_printed']: s['title'] for s in P['sections']}
    has_sections = bool(sections)
    siman_tag = 'h3' if has_sections else 'h2'
    missing_here = {int(k.split(':')[1]): v for k, v in missing.items()
                    if int(k.split(':')[0]) == VOL_NUM[vol]}

    out = ['<h1>שו"ת משנה הלכות חלק %s</h1>' % vol, AUTHOR_LINE]
    printed_seen = []
    in_section = [False]

    def open_siman(n):
        if n in sections:
            out.append('<h2>%s</h2>' % sections[n])
            in_section[0] = True
        tag = siman_tag if (in_section[0] or not has_sections) else 'h2'
        out.append('<%s>סימן %s</%s>' % (tag, gematria(n), tag))
        printed_seen.append(n)

    def emit_missing_before(n):
        for m in sorted(k for k in missing_here if k < n
                        and k not in printed_seen):
            open_siman(m)
            key = '%d:%d' % (VOL_NUM[vol], m)
            for i, x in enumerate(missing_here[m]):
                x = normalize(x)
                assert x, (key, i)
                out.append('<b>%s</b>' % x if i in MISSING_BOLD[key] else x)

    for first, t, last in units:
        if t is None:
            n = h2_lines[first]
            emit_missing_before(n)
            open_siman(n)
            continue
        if first in splits:
            emit_missing_before(splits[first])
            open_siman(splits[first])
        t = normalize(t)
        if not t:
            continue
        out.append('<b>%s</b>' % t if first in bold else t)
    emit_missing_before(10 ** 6)

    return out, printed_seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--build', required=True, help='dir holding the plan JSONs')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    plan = json.load(open(os.path.join(a.build, 'structure_plan.json')))
    lost_raw = json.load(open(os.path.join(a.build, 'lost_chars.json')))
    recs = lost_raw if isinstance(lost_raw, list) else lost_raw['records']
    lost = {}
    for r in recs:
        lost.setdefault(r['vol'], []).append(r)
    missing = json.load(open(os.path.join(a.build, 'missing_simanim.json')))
    os.makedirs(a.out, exist_ok=True)
    for vol in VOLS:
        lines, seen = build_volume(vol, a.src, plan, lost, missing)
        name = 'שות משנה הלכות חלק %s.txt' % vol
        with open(os.path.join(a.out, name), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        gaps = [n for n in range(seen[0], seen[-1] + 1) if n not in seen]
        print('%-3s simanim %d (%d-%d) gaps=%s lines=%d' % (
            vol, len(seen), seen[0], seen[-1], gaps, len(lines)))


if __name__ == '__main__':
    main()
