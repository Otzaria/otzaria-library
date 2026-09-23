# Decide, from the printed layout, whether file lines L and L+1 are one paragraph.
import sys, re, json, html, collections
sys.path.insert(0, '/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad/build')
from lib import *

BODY = ('Rashi', 12.7)
OPEN = ('DWVilna,Bold', 16.3)      # enlarged opening word of a printed paragraph
TOPIC = ('DWVilna,Bold', 12.7)

def col_bounds(x):
    # two columns: right column x0>=280
    return (286, 509) if x['x0'] >= 275 else (41, 264)

def find_junction(A, B, st):
    """index in st of the first char of B, requiring A's tail right before it."""
    for K in (20, 14, 10, 7):
        a = A[-K:]; b = B[:K]
        if len(a) < min(K, 5) or len(b) < min(K, 5):
            continue
        i = st.find(a + b)
        if i >= 0 and st.find(a + b, i + 1) < 0:
            return i + len(a), f'exact{K}'
    # fuzzy: B head found shortly after A tail
    for K in (14, 10):
        a = A[-K:]; b = B[:K]
        pa = st.find(a)
        while pa >= 0:
            pb = st.find(b, pa + len(a))
            if 0 <= pb - (pa + len(a)) <= 6:
                return pb, f'gap{pb - (pa + len(a))}'
            pa = st.find(a, pa + 1)
    # approximate: last unique 6-gram of A's tail and first unique 6-gram of B's head, close together
    def uniq_hits(t, rng):
        hits = []
        for k in rng:
            g = t[k:k+6]
            if len(g) < 6: continue
            i = st.find(g)
            if i >= 0 and st.find(g, i + 1) < 0:
                hits.append((k, i))
        return hits
    ha = uniq_hits(A, range(max(0, len(A)-40), len(A)-5))
    hb = uniq_hits(B, range(0, min(len(B), 40)))
    if ha and hb:
        ka, ia = ha[-1]; kb, ib = hb[0]
        endA = ia + (len(A) - ka)          # predicted index right after A
        startB = ib - kb                   # predicted index of B's first char
        if abs(startB - endA) <= 12 and startB > 0:
            return startB, f'approx{startB - endA}'
    return None, 'not_found'

def classify(vi, lines, L, seg_pdf_lines, st, own):
    A = norm(lines[L-1]); B = norm(lines[L])
    if not A or not B:
        return 'undecided', 'empty_norm', None
    j, how = find_junction(A, B, st)
    if j is None:
        return 'undecided', how, None
    la, lb = own[j-1], own[j]
    X, Y = seg_pdf_lines[la], seg_pdf_lines[lb]
    fx, fy = (X['font'], X['size']), (Y['font'], Y['size'])
    info = {'how': how, 'X': [X['p'], X['font'], X['size'], X['x0'], X['x1']], 'Y': [Y['p'], Y['font'], Y['size'], Y['x0'], Y['x1']]}
    if la == lb:
        return 'join', 'same_printed_line', info
    if fy == OPEN:
        return 'keep', 'next_starts_printed_paragraph', info
    if fx == TOPIC and fy == TOPIC:
        if re.match(r'^\s*[א-ת]{1,2}[.)]', lines[L]):
            return 'keep', 'topic_list_item', info
        return 'join', 'topic_wrapped', info
    if fx == BODY and fy == BODY:
        cl, cr = col_bounds(X)
        full_left = X['x0'] <= cl + 3
        if full_left:
            return 'join', 'prev_printed_line_runs_to_margin', info
        return 'keep', 'prev_printed_line_is_paragraph_end', info
    if fx != fy:
        return 'keep', 'font_block_change', info
    # same non-body font (address block, signature...)
    cl, cr = col_bounds(X)
    if X['x0'] <= cl + 3 and X['x1'] >= cr - 3:
        return 'join', 'same_block_full_line', info
    return 'undecided', 'same_nonbody_block', info

# ---------- vol 17 <br> separators from the site pages ----------
SEP = re.compile(r'((?:\s*<(?:/?p|br)\s*/?>\s*)+)', re.I)
def br_candidates(lines, h2):
    from bs4 import BeautifulSoup
    byval = {h['val']: h for h in h2}
    out = []; stats = collections.Counter()
    for N in range(1, 256):
        f = f'{S}/site/raw/17/{N}.html'
        try:
            raw = open(f, 'rb').read().decode('cp1255', errors='replace')
        except FileNotFoundError:
            stats['page_missing'] += 1; continue
        td = BeautifulSoup(raw, 'html.parser').select_one('td.teshuvaTable')
        if td is None or N not in byval:
            stats['no_cell'] += 1; continue
        parts = SEP.split(td.decode_contents())
        chunks = []  # (text, sep_after)
        for k in range(0, len(parts), 2):
            t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', parts[k])).replace('\xa0', ' ')).strip()
            sep = parts[k+1] if k + 1 < len(parts) else ''
            if t:
                chunks.append([t, sep])
            elif chunks:
                chunks[-1][1] += sep
        h = byval[N]
        flines = [(ln, re.sub(r'\s+', ' ', lines[ln-1]).strip()) for ln in range(h['line'] + 1, h['end'] + 1)]
        ptr = 0; mapped = []
        for t, sep in chunks:
            m = None
            for q in range(ptr, len(flines)):
                if flines[q][1] == t:
                    m = flines[q][0]; ptr = q + 1; break
            mapped.append((m, sep))
        for (m1, sep), (m2, _) in zip(mapped, mapped[1:]):
            tags = re.findall(r'<\s*(/?\w+)', sep)
            if tags and all(t.lower() == 'br' for t in tags):
                stats['br_only_sep'] += 1
                if m1 and m2 and m2 == m1 + 1:
                    out.append(m1)
                else:
                    stats['br_sep_unmapped'] += 1
    return sorted(set(out)), stats
