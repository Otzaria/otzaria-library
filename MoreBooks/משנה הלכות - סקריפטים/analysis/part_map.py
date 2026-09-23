# siman_map, splits, subject lines, overlap verification.
import sys, json, collections, difflib, re
sys.path.insert(0, '/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad/build')
from lib import *

# printed simanim whose heading was lost in the file (content appended to the preceding file siman).
# Determined from line-level n-gram attribution + surviving "... סימן X" remnant lines (see structure_plan.md).
LOST = {13: [86, 98, 119, 146, 156], 14: [205, 213], 15: [49]}
MISSING = {12: [403], 16: [136, 137], 17: [73]}   # printed simanim whose content is absent from the file
NONEXIST = {14: [93, 105]}                      # numbers skipped by the printed numbering itself

def printed_numbers(vi, h2, P):
    """printed number for every file h2, in order."""
    if vi == 17:
        return [h['val'] for h in h2]              # labels already match print (73 skipped; 117 kept although print has no heading)
    if vi == 9:
        return [h['val'] + 150 for h in h2]
    pnums = [p['n'] for p in P]
    drop = set(LOST.get(vi, [])) | set(MISSING.get(vi, []))
    seq = [n for n in pnums if n not in drop]
    assert len(seq) == len(h2), (vi, len(seq), len(h2))
    return seq

def first_line_of(vi, lines, a, b, P_X, P_prev):
    """first file line (a..b) that belongs to printed siman X; returns (line, remnant_line_or_None)."""
    sx = stream(P_X['lines'])[0]
    top = norm(''.join(t['t'] for t in P_X['topic']))
    rem = None
    for ln in range(a, b + 1):
        w = lines[ln-1].split()
        if len(w) <= 5 and 'סימן' in w and w.index('סימן') + 1 < len(w) and gval(w[w.index('סימן') + 1]) == P_X['n']:
            rem = ln
            return ln + 1, rem
    # topic line (exact or fuzzy)
    best = None
    for ln in range(a, b + 1):
        t = norm(lines[ln-1])
        if top and t and difflib.SequenceMatcher(None, t, top).ratio() >= 0.8:
            best = ln; break
    if best is None:
        # first line whose head is found near the start of X's stream
        for ln in range(a, b + 1):
            t = norm(lines[ln-1])[:30]
            if len(t) >= 10 and 0 <= sx.find(t) < 0.1 * len(sx):
                best = ln; break
    if best is None:
        return None, None
    # include immediately preceding short lines that occur at the very start of X (e.g. a line printed right after the topic)
    ln = best
    sp = stream(P_prev['lines'])[0]
    while ln - 1 >= a:
        t = norm(lines[ln-2])
        if 0 < len(t) <= 40 and sx.find(t) >= 0 and sx.find(t) < 0.05 * len(sx) and sp.find(t) < 0:
            ln -= 1
        else:
            break
    return ln, rem

def where(t, st, n=6):
    """(fraction of t's n-grams found in stream st, median relative position of the hits)"""
    g = [t[j:j+n] for j in range(max(0, len(t)-n+1))]
    if not g: return None
    hits = [st.find(x) for x in g]; hits = [h for h in hits if h >= 0]
    if not hits: return [0.0, None]
    hits.sort()
    return [round(len(hits)/len(g), 2), round(hits[len(hits)//2]/max(1, len(st)), 3)]

def containment(ftxt, ptxt):
    fg = grams(ftxt); pg = grams(ptxt)
    return round(len(fg & pg) / max(1, len(fg)), 3), len(fg)

def subject_for(lines, a, b, P_X):
    top = norm(''.join(t['t'] for t in P_X['topic']))
    if not top:
        return {'line': None, 'reason': 'no_topic_in_print'}
    hi = min(b, a + 6)
    rng = [ln for ln in range(a, hi + 1) if norm(lines[ln-1])]
    SM = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio()
    for ln in rng:                                   # pass 1: one line
        t = norm(lines[ln-1])
        if t == top:
            return {'line': ln, 'match': 'exact'}
    for ln in rng:                                   # pass 2: topic spread over 2-4 lines
        t = norm(lines[ln-1])
        if not (top.startswith(t) or SM(t, top[:len(t)]) >= 0.85):
            continue
        cat = t
        for k in range(1, 4):
            if ln + k > b: break
            cat += norm(lines[ln + k - 1])
            if cat == top:
                return {'line': None, 'lines': list(range(ln, ln + k + 1)), 'match': 'multi_line'}
            if len(cat) > len(top) * 1.2 + 5: break
    for ln in rng:
        t = norm(lines[ln-1]); r = SM(t, top)
        if r >= 0.8 and len(t) <= len(top) * 1.25 + 5:
            return {'line': ln, 'match': 'fuzzy', 'ratio': round(r, 2)}
    for ln in rng:                                   # pass 2b: fuzzy multi-line
        t = norm(lines[ln-1])
        if not (top.startswith(t) or SM(t, top[:len(t)]) >= 0.85):
            continue
        cat = t
        for k in range(1, 4):
            if ln + k > b: break
            cat += norm(lines[ln + k - 1])
            if cat == top or (abs(len(cat) - len(top)) <= 0.1 * len(top) + 3 and SM(cat, top) >= 0.9):
                return {'line': None, 'lines': list(range(ln, ln + k + 1)), 'match': 'multi_line'}
            if len(cat) > len(top) * 1.2 + 5: break
    for ln in rng:                                   # pass 3: topic + running text in one line
        t = norm(lines[ln-1]); k = min(len(top), 25)
        if len(t) > len(top) + 10 and (t.startswith(top[:k]) or SM(t[:len(top)], top) >= 0.85):
            return {'line': None, 'partial': True, 'partial_line': ln}
    return {'line': None, 'reason': 'topic_not_found_in_file'}

def build(vi):
    lines, h2 = load_file(vi)
    L, P = load_pdf(vi)
    pn = {p['n']: p for p in P}
    nums = printed_numbers(vi, h2, P)
    siman_map = []; splits = []; segs = []; extra_del = []
    for h, n in zip(h2, nums):
        siman_map.append({'file_line': h['line'], 'site_label': h['label'], 'printed': n})
        segs.append([h['line'] + 1, h['end'], n])
    # splits: a lost printed X lives at the end of the file siman whose printed number is the previous existing one
    for X in LOST.get(vi, []):
        idx = [i for i, s in enumerate(segs) if s[2] < X]
        i = max(idx, key=lambda i: segs[i][2])
        a, b, n0 = segs[i]
        ln, rem = first_line_of(vi, lines, a, b, pn[X], pn[n0])
        sp = stream(pn[n0]['lines'])[0]; sx = stream(pn[X]['lines'])[0]
        prevln = (rem - 1) if rem else ln - 1
        topic_x = norm(''.join(t['t'] for t in pn[X]['topic']))
        tL = norm(lines[ln-1])
        entry = {'printed': X, 'file_line': ln,
                 'check': {'first_line_in_printed_X': where(tL, sx),
                           'first_line_in_prev_printed': where(tL, sp),
                           'first_line_topic_ratio': round(difflib.SequenceMatcher(None, tL, topic_x).ratio(), 2) if topic_x else None,
                           'prev_line': prevln,
                           'prev_line_in_prev_printed': where(norm(lines[prevln-1]), sp),
                           'prev_line_in_printed_X': where(norm(lines[prevln-1]), sx)}}
        if len(norm(lines[prevln-1])) <= 12:
            entry['check']['prev_line_short'] = True
            entry['check']['line_before_prev_in_prev_printed'] = where(norm(lines[prevln-2]), sp)
        if rem:
            entry['check']['heading_remnant_line'] = rem
            extra_del.append({'line': rem, 'reason': f'שורת "... סימן X" — שארית הכותרת של סימן {X} שאבדה במיזוג'})
        splits.append(entry)
        segs[i][1] = (rem - 1) if rem else ln - 1
        segs.insert(i + 1, [ln, b, X])
    # overlap per segment
    ov = []
    for a, b, n in segs:
        tgt = n
        if vi == 17 and n == 117:
            tgt = 116                                 # print has no heading 117; its text is inside printed 116
        ftxt = norm(''.join(lines[a-1:b]))
        c, ng = containment(ftxt, stream(pn[tgt]['lines'])[0])
        ov.append({'printed': n, 'first': a, 'last': b, 'overlap': c, 'ngrams': ng})
    # subject lines
    subj = []
    for a, b, n in segs:
        if vi == 17 and n == 117:
            r = {'line': None, 'reason': 'no_printed_heading'}
        else:
            r = subject_for(lines, a, b, pn[n])
        r = {'printed': n} | r
        subj.append(r)
    return {'lines': lines, 'h2': h2, 'P': P, 'siman_map': siman_map, 'splits': splits, 'segs': segs,
            'overlap': ov, 'subject_line': subj, 'extra_del': extra_del}

if __name__ == '__main__':
    for vi in range(1, 18):
        r = build(vi)
        ov = r['overlap']
        mn = min(ov, key=lambda o: o['overlap'])
        low = [(o['printed'], o['overlap'], o['ngrams']) for o in ov if o['overlap'] < 0.8]
        sj = collections.Counter(('partial' if s.get('partial') else s.get('match') or s.get('reason')) for s in r['subject_line'])
        print(vi, 'min', mn['printed'], mn['overlap'], 'low', low, dict(sj))
        for s in r['splits']: print('   split', s)
