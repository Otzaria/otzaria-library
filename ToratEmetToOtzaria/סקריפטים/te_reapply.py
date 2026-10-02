"""Re-apply a corrected Torat Emet conversion to the books already in the library.

The books in ToratEmetToOtzaria/ספרים were converted years ago by scripts that did
not read each book's CosmeticsType rules, and have since been corrected by hand
(user reports, spacing, gershayim, images, tables, heading wording...). Converting
again from the source would throw those corrections away, so this script does not
replace the files: the current file is the baseline, and from a fresh conversion
(te_convert.py) it takes only what the old conversion got wrong:

  * inline formatting the rules define (union with the current formatting),
  * removal of raw Torat Emet tokens still in the text ('[[[', '{', '<QM>', 'JJ'...),
  * text a rule generates that the old conversion lost ('?' for <QM>, ',' for <~>),
  * heading levels, only where the old conversion flattened them ("headings": "new").

The current file's characters, line structure (links point at line numbers) and
heading wording win everywhere else. Lines that cannot be aligned to the source are
left untouched. A closer of the current file with no opener in its line formats
nothing (it is a stray closer of the source). Text that only the current file has
takes the conversion's formatting only where the conversion has it on both sides;
an element a maintainer added (the gray '(תחילת העמוד)' page mark) keeps its own
formatting, and a line listed in the book's "keep" (fixed by hand in a way the
conversion would undo) is left exactly as it is.
Run on its own output, the script changes nothing.

--check verifies that every text difference is a rule token removed or rule text
added, and that the formatting is sound:
  * every source tag left unclosed at a heading or at the end of the book (te_convert
    renders it as literal text) is listed in the book's "unbalanced" as [source line,
    tag], once per such tag, and every entry still matches one;
  * no tag runs over more than --max-carry source lines (10) unless the span is listed
    in "carried" as [open line, close line, tag], and every entry still matches one;
  * every "keep" entry [line, text] still names a line with that text;
  * in every line it changes: no tag open at the end of the line, no <b>/<i>/<u>/<sup>/
    <sub> inside itself, no char with formatting that neither the current line nor the
    conversion of its source line has, and a second run would not change the line again.
It writes nothing; --write skips a book that fails.

Usage (from the repo root):
    python ToratEmetToOtzaria/סקריפטים/te_reapply.py --src "<Torat Emet dir>" --check
    python ToratEmetToOtzaria/סקריפטים/te_reapply.py --src "<Torat Emet dir>" --write [--only חברותא]
"""
import argparse
import collections
import json
import os
import sys

import te_convert as E
import difflib
import html as html_mod
import re

EFFECT_TAGS = {'b': 'b', 'strong': 'b', 'i': 'i', 'em': 'i', 'u': 'u', 'big': 'big',
               'small': 'small', 'sup': 'sup', 'sub': 'sub'}
HTML_TAGS = {'a', 'abbr', 'blockquote', 'br', 'center', 'div', 'font', 'hr', 'img', 'p', 'span',
             'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul', 'ol', 'li', 'q', 'del', 'ins',
             's', 'strike', 'mark', 'code', 'pre', 'cite', 'var', 'dfn', 'tt', 'nobr'}
TAG_RE = re.compile(r'<(/?)([A-Za-z~][A-Za-z0-9]*)([^<>]*)>')
HEAD_RE = re.compile(r'^\s*<h([1-6])([^>]*)>(.*?)</h\1>\s*$', re.S | re.I)


class Ch:
    __slots__ = ('c', 'eff', 'gen')

    def __init__(self, c, eff, gen=False):
        self.c, self.eff, self.gen = c, eff, gen


def parse_new(html):
    """-> items: Ch | ('a', tag) | ('x', FROM)"""
    items, stack, gen, group = [], [], 0, 0
    pos = 0
    for m in TAG_RE.finditer(html):
        for ch in html_mod.unescape(html[pos:m.start()]):
            items.append(Ch(ch, tuple(stack), group if gen > 0 else 0))
        pos = m.end()
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        if name == 'tex':
            items.append(('x', bytes.fromhex(re.search(r'd="([0-9a-f]*)"', attrs).group(1)).decode()))
        elif name == 'teg':
            gen += -1 if closing else 1
            if not closing:
                group += 1
        elif name == 'br':
            items.append(('a', '<br>'))
        elif name in EFFECT_TAGS:
            e = EFFECT_TAGS[name]
            if closing:
                if e in stack:
                    stack.reverse(); stack.remove(e); stack.reverse()
            else:
                stack.append(e)
    for ch in html_mod.unescape(html[pos:]):
        items.append(Ch(ch, tuple(stack), group if gen > 0 else 0))
    return items


DROP_CUR_TAG = [re.compile(r'^<span style="color=#0055ff">$', re.I)]


def parse_cur(html):
    """-> items: Ch | ('a', tag). Unknown non-HTML tags (Torat Emet tokens such as
    <QM>, <~>) become literal text so the merge can match them to consumed tokens."""
    html = html.replace('&nbsp;', ' ').replace('\xa0', ' ')
    # the old conversion sometimes put a closing tag inside a token: '<</b>QM>'
    html = re.sub(r'<((?:</?[a-z]+>)+)([A-Z~][A-Z0-9]*)>', r'\1<\2>', html)
    items, stack, dropped = [], [], []
    pos = 0

    def text(t):
        for ch in t:
            items.append(Ch(ch, tuple(stack)))

    for m in TAG_RE.finditer(html):
        text(html[pos:m.start()])
        pos = m.end()
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        tag = m.group(0)
        if name in EFFECT_TAGS:
            e = EFFECT_TAGS[name]
            if closing:
                if e in stack:
                    stack.reverse(); stack.remove(e); stack.reverse()
                # A closer with no opener in the line formats nothing, as in the
                # reader. It is a stray closer of the source ('{a} b}' in Chavruta,
                # '}}(ל, א)}}' in מנורת המאור), not formatting carried from the line
                # before: what the source really carries over lines comes from the
                # conversion. Applying it to the text before it bolded or shrank
                # whole lines (a1f39803: 773 lines in 13 books).
            else:
                stack.append(e)
        elif name == 'br':
            items.append(('a', '<br>'))
        elif re.fullmatch(r'h[1-6]', name):
            continue             # heading tags in mid-line: debris of the old conversion
        elif name in HTML_TAGS:
            if not closing and any(p.match(tag) for p in DROP_CUR_TAG):
                dropped.append(name)
                continue
            if closing and name in dropped:
                dropped.remove(name)
                continue
            items.append(('a', re.sub(r'^<(/?)' + m.group(2), lambda k: '<' + k.group(1) + name, tag)))
        else:
            text(tag)            # a Torat Emet token that survived as a pseudo-tag
    text(html[pos:])
    return items


def chars(items):
    return [it for it in items if isinstance(it, Ch)]


def align(a, b):
    """Char alignment of two strings -> opcodes.

    Anchors on equal non-space tokens first (spaces are too common to anchor on),
    then aligns the chars of each gap between anchors. Fast on long lines.
    """
    tok = r'[\u05d0-\u05ea\u0591-\u05c7\u05f3\u05f4A-Za-z0-9\'"]+|[^\s]'
    ta = [(m.start(), m.end()) for m in re.finditer(tok, a)]
    tb = [(m.start(), m.end()) for m in re.finditer(tok, b)]
    # a word matches whatever its gershayim are written with: רש''י / רש"י / רש״י
    def norm(t):
        return t.replace("''", '"').replace('\u05f4', '"').replace('\u05f3', "'")
    sa = [norm(a[x:y]) for x, y in ta]
    sb = [norm(b[x:y]) for x, y in tb]
    ops = []
    pa = pb = 0                # char positions already covered

    def gap(A2, B2):
        nonlocal pa, pb
        if pa < A2 or pb < B2:
            for o, x1, x2, y1, y2 in difflib.SequenceMatcher(None, a[pa:A2], b[pb:B2],
                                                             autojunk=False).get_opcodes():
                ops.append((o, pa + x1, pa + x2, pb + y1, pb + y2))
        pa, pb = A2, B2

    for blk in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_matching_blocks():
        if blk.size == 0:
            continue
        A1, B1 = ta[blk.a][0], tb[blk.b][0]
        A2, B2 = ta[blk.a + blk.size - 1][1], tb[blk.b + blk.size - 1][1]
        gap(A1, B1)
        # inside an equal token run the text between tokens (spaces) may still differ
        for o, x1, x2, y1, y2 in difflib.SequenceMatcher(None, a[A1:A2], b[B1:B2],
                                                         autojunk=False).get_opcodes():
            ops.append((o, A1 + x1, A1 + x2, B1 + y1, B1 + y2))
        pa, pb = A2, B2
    gap(len(a), len(b))
    return ops


def consumed_near(nitems_pos, markers, i, run):
    """Is the cur-only text `run`, inserted at new-char index i, made of consumed tokens?"""
    core = run.strip()
    if not core:
        return False
    window = [frm for (p, frm) in markers if i - len(frm) - 3 <= p <= i + 3]
    if not window:
        return False
    if re.fullmatch(r'[<>]+', core.replace(' ', '')):
        return True              # stray '<' debris the old conversion left by a consumed token
    # every piece of the run must be a piece of some nearby consumed token
    joined = ''.join(window)
    pieces = core.split()
    return all(pc in joined or any(pc in f for f in window) for pc in pieces)


def own_elements(C, eq_cur):
    """Cur-char indices inside an element of the current file (<span>, <div>...) none of
    whose letters is source text: markup a maintainer added, such as the page mark
    '<span style="color:Gray;"><small><small>(תחילת העמוד)</small></small></span>'.
    Its formatting is the maintainer's; the conversion has nothing to say about it."""
    own, stack, k = set(), [], 0
    for it in C:
        if isinstance(it, Ch):
            k += 1
            continue
        m = re.match(r'<(/?)([a-z][a-z0-9]*)', it[1])
        if not m or m.group(2) in ('br', 'img', 'hr'):
            continue
        if not m.group(1):
            stack.append((m.group(2), k))
        else:
            for x in range(len(stack) - 1, -1, -1):
                if stack[x][0] == m.group(2):
                    _, start = stack.pop(x)
                    span = range(start, k)
                    if span and not any(j in eq_cur for j in span):
                        own.update(span)
                    break
    return own


def merge_line(new_html, cur_html, report):
    N = parse_new(new_html)
    C = parse_cur(cur_html)
    nch = chars(N)
    cch = chars(C)
    # consumed markers keyed by the new-char index they precede
    markers, k = [], 0
    for it in N:
        if isinstance(it, Ch):
            k += 1
        elif it[0] == 'x':
            markers.append((k, it[1]))
    # anchors of cur keyed by cur-char index
    anchors, k = {}, 0
    for it in C:
        if isinstance(it, Ch):
            k += 1
        else:
            anchors.setdefault(k, []).append(it[1])
    nbr, k = {}, 0             # <br> of new keyed by new-char index
    for it in N:
        if isinstance(it, Ch):
            k += 1
        elif it[0] == 'a':
            nbr.setdefault(k, []).append(it[1])
    cbr = {j for j, lst in anchors.items() if '<br>' in lst}

    out = []                   # list of Ch | ('a', tag)
    def emit_anchors(j):
        for t in anchors.get(j, []):
            out.append(('a', t))

    def left_eff(i):
        return nch[i - 1].eff if i > 0 else (nch[0].eff if nch else ())

    def common(effs):
        """The effects all of effs share (big/small at their smallest depth)."""
        if not effs:
            return ()
        left = collections.Counter(effs[0])
        for e in effs[1:]:
            left &= collections.Counter(e)
        out = []
        for e in effs[0]:                  # in the order of the first
            if left[e] > 0:
                left[e] -= 1
                out.append(e)
        return tuple(out)

    def run_eff(i1, i2):
        """Formatting for text the current file has in place of new[i1:i2] (nothing, for an
        insertion): what the conversion has on both sides of it, or all over it. Text
        inserted at the edge of a formatted run stays out of the run."""
        if i2 > i1:
            inner = [nch[i].eff for i in range(i1, i2) if not nch[i].c.isspace()]
            return common(inner or [nch[i].eff for i in range(i1, i2)])
        lft = next((nch[i].eff for i in range(i1 - 1, -1, -1) if not nch[i].c.isspace()), None)
        rgt = next((nch[i].eff for i in range(i1, len(nch)) if not nch[i].c.isspace()), None)
        return common([e for e in (lft, rgt) if e is not None])

    ops = align(''.join(c.c for c in nch), ''.join(c.c for c in cch))
    eq_cur = {j for op, i1, i2, j1, j2 in ops if op == 'equal'
              for j in range(j1, j2) if not cch[j].c.isspace()}
    own = own_elements(C, eq_cur)

    def merged(new_eff, j):
        if j in own:
            return union((), cch[j].eff)
        return union(new_eff, cch[j].eff)

    present = set()            # generated groups the current file already renders in part
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal':
            present.update(nch[i].gen for i in range(i1, i2) if nch[i].gen and not nch[i].c.isspace())
    pending = []               # generated text that opens the next aligned source text
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal':
            for di in range(i2 - i1):
                i, j = i1 + di, j1 + di
                emit_anchors(j)
                if pending and not cch[j].c.isspace():
                    out.extend(pending)
                    pending.clear()
                if i in nbr and j not in cbr and '<br>' not in [x[1] for x in out[-1:] if not isinstance(x, Ch)]:
                    pass       # a <br> only the new conversion has: current line structure wins
                out.append(Ch(cch[j].c, merged(nch[i].eff, j)))
            continue
        # new-only chars: keep rule-generated text, drop the rest (cur wins)
        gen = ''.join(nch[i].c for i in range(i1, i2) if nch[i].gen and nch[i].gen not in present)
        run = ''.join(cch[j].c for j in range(j1, j2))
        if op in ('delete', 'replace'):
            genrun = [nch[i] for i in range(i1, i2) if nch[i].gen and nch[i].gen not in present]
            while genrun and genrun[0].c.isspace():
                genrun.pop(0)
            while genrun and genrun[-1].c.isspace():
                genrun.pop()
            if genrun and genrun[0].c in ',.?:;!':
                while out and isinstance(out[-1], Ch) and out[-1].c == ' ':
                    out.pop()        # punctuation a rule inserts hugs the preceding word
            nxt = nch[i2] if i2 < len(nch) else None
            opening = nxt is not None and not nxt.gen and not nxt.c.isspace()
            for g in genrun:
                (pending if opening else out).append(Ch(g.c, g.eff, True))
            if gen.strip():
                report['generated'][gen.strip()] = report['generated'].get(gen.strip(), 0) + 1
        if op in ('insert', 'replace'):
            if consumed_near(None, markers, i1, run):
                report['consumed'][run.strip()] = report['consumed'].get(run.strip(), 0) + 1
                for j in range(j1, j2):
                    emit_anchors(j)
                    if cch[j].c.isspace():
                        out.append(Ch(' ', left_eff(i1)))
            elif re.fullmatch(r'(<[A-Za-z0-9~]+>\s*)+', run.strip()):
                # a Torat Emet pseudo-tag no rule defines (<COL3>): invisible in the
                # current file, so dropping it keeps what the reader sees
                report['consumed'][run.strip()] = report['consumed'].get(run.strip(), 0) + 1
                for j in range(j1, j2):
                    emit_anchors(j)
                    if cch[j].c.isspace():
                        out.append(Ch(' ', left_eff(i1)))
            else:
                base = run_eff(i1, i2 if op == 'replace' else i1)
                for j in range(j1, j2):
                    emit_anchors(j)
                    # an extra space of the current file takes nothing from the conversion:
                    # between two runs it would join them ('<b>(32)</b>  <b>רשב''ם</b>')
                    sp = op == 'insert' and cch[j].c.isspace()
                    out.append(Ch(cch[j].c, merged((), j) if sp else merged(base, j)))
                if op == 'replace' and run.strip():
                    key = (''.join(nch[i].c for i in range(i1, i2)), run)
                    report['kept_cur'][key] = report['kept_cur'].get(key, 0) + 1
    out.extend(pending)
    emit_anchors(len(cch))
    return serialize(collapse_spaces(out))


def collapse_spaces(items):
    """One space for a run of spaces, carrying what any of them carried. tidy() would
    collapse them anyway, keeping whichever it meets first ('<b>X </b> <b>(Y)</b>' ->
    '<b>X</b> <b>(Y)</b>'), and the next run would then bold that space from the
    conversion again: the output would not be a fixed point."""
    out = []
    for it in items:
        if (isinstance(it, Ch) and it.c.isspace() and out and isinstance(out[-1], Ch)
                and out[-1].c.isspace()):
            prev = out[-1]
            out[-1] = Ch(' ', union(it.eff, prev.eff), prev.gen and it.gen)
        else:
            out.append(it)
    return out


def union(new, cur):
    """Effects of both sides, in the current file's order. For big/small the nesting
    depth of the current file wins when it has that effect at all (an editor may
    have toned it down). Any other effect appears once: <b> inside <b> is no bolder."""
    out = []
    for e in cur:
        if e in ('big', 'small') or e not in out:
            out.append(e)
    for e in new:
        if e in ('big', 'small'):
            if e not in cur and out.count(e) < new.count(e):
                out.append(e)
        elif e not in out:
            out.append(e)
    return tuple(out)


def serialize(items):
    out, cur = [], []

    def sync(target):
        i = 0
        while i < len(cur) and i < len(target) and cur[i] == target[i]:
            i += 1
        for e in reversed(cur[i:]):
            out.append(f'</{e}>')
        del cur[i:]
        for e in target[i:]:
            out.append(f'<{e}>')
            cur.append(e)

    for it in items:
        if isinstance(it, Ch):
            # <sup>/<sub> innermost: a tag nested inside <sup> makes it an inline box,
            # and two boxes in one line reverse the RTL text in the reader
            sync([e for e in it.eff if e not in ('sup', 'sub')] +
                 [e for e in it.eff if e in ('sup', 'sub')])
            out.append(html_escape(it.c))
        else:
            tag = it[1]
            if tag != '<br>':
                sync([])
            out.append(tag)
    sync([])
    s = ''.join(out)
    return tidy(s)


def html_escape(c):
    return {'<': '&lt;', '>': '&gt;'}.get(c, c)


def tidy(s):
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'<(b|i|u|big|small|sup|sub)>(\s*)</\1>', r'\2', s)
        s = re.sub(r'</(b|i|u|big|small|sup|sub)><\1>', '', s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'(<(?:b|i|u|big|small|sup|sub)>)( +)', r'\2\1', s)
        s = re.sub(r'( +)(</(?:b|i|u|big|small|sup|sub)>)', r'\2\1', s)
    s = re.sub(r' {2,}', ' ', s)
    return s.strip()


# ---------------------------------------------------------------- whole book
def key(s):
    s = re.sub(r'<[^<>]*>', '', s)
    return re.sub(r'[^א-ת0-9]', '', html_mod.unescape(s))


def new_report():
    return {'generated': {}, 'consumed': {}, 'kept_cur': {}, 'unaligned_cur': [],
            'heading_level': {}, 'kind_mismatch': [], 'pairs': {}, 'unstable': []}


def merge_pair(n, c, report, heading_levels):
    """The merged line for source line n and current line c, or None to leave c as is."""
    hm = HEAD_RE.match(c)
    if not hm and re.match(r'\s*<h[1-6]', c, re.I):
        report['unaligned_cur'].append(c)              # heading with text glued after it:
        return None                                    # would lose the heading, leave it
    if n['kind'] == 'h' and hm:
        inner = merge_line(n['html'], hm.group(3), report)
        inner = re.sub(r'</?(b|i|u|big|small)>', '', inner).strip()
        lvl = n['level'] if heading_levels == 'new' else int(hm.group(1))
        if str(n['level']) != hm.group(1):
            k = (hm.group(1), str(lvl))
            report['heading_level'][k] = report['heading_level'].get(k, 0) + 1
        return f'<h{lvl}{hm.group(2)}>{inner}</h{lvl}>'
    if hm or n['kind'] == 'h':
        report['kind_mismatch'].append(c)
        return None if hm else merge_line(n['html'], c, report)
    return merge_line(n['html'], c, report)


def merge_book(new_lines, cur_lines, report=None, heading_levels='cur', keep=()):
    """new_lines: engine dicts; cur_lines: list of str. Returns (lines, report).
    keep: 1-based lines fixed by hand that are left as they are (te_books.json "keep").
    report['pairs'] maps every merged line (0-based) to its source line in new_lines;
    report['unstable'] lists the lines a second run would change again."""
    report = report or new_report()
    for k, v in new_report().items():
        report.setdefault(k, v)
    keep = {int(l) - 1 for l in keep}
    nk = [key(l['html']) for l in new_lines]
    ck = [key(l) for l in cur_lines]
    out = list(cur_lines)
    pairs = []
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, nk, ck, autojunk=False).get_opcodes():
        if op == 'equal' or (op == 'replace' and a2 - a1 == b2 - b1):
            pairs += list(zip(range(a1, a2), range(b1, b2)))
        elif op == 'replace':
            # unequal block: pair greedily by similarity
            for b in range(b1, b2):
                best, score = None, 0.0
                for a in range(a1, a2):
                    r = difflib.SequenceMatcher(None, nk[a], ck[b], autojunk=False).quick_ratio()
                    if r > score:
                        best, score = a, r
                if best is not None and score > 0.8 and ck[b]:
                    pairs.append((best, b))
                else:
                    report['unaligned_cur'].append(b)
        else:
            report['unaligned_cur'] += list(range(b1, b2))
    for a, b in pairs:
        n, c = new_lines[a], cur_lines[b]
        if b < 2 and c.lstrip().startswith('<h1') or (b == 1):
            continue                                   # title and author lines: as edited
        side = new_report()
        if b in keep:
            continue                                   # fixed by hand: as it is
        m = merge_pair(n, c, side, heading_levels)
        for k in ('unaligned_cur', 'kind_mismatch'):
            report[k] += [b for _ in side[k]]
        for k in ('generated', 'consumed', 'kept_cur', 'heading_level'):
            for x, v in side[k].items():
                report[k][x] = report[k].get(x, 0) + v
        if m is None:
            continue
        out[b] = m
        report['pairs'][b] = a
        if m != c and merge_pair(n, m, new_report(), heading_levels) != m:
            report['unstable'].append(b)               # not a fixed point: a bug of the merge
    return out, report


# ---------------------------------------------------------------- verification & CLI
HERE = os.path.dirname(os.path.abspath(__file__))
BOOKS_ROOT = os.path.join(HERE, '..', 'ספרים', 'אוצריא')


def plain(s):
    s = re.sub(r'<(?!/?(QM|S|~|CCC|COL3)\b)[^<>]*>', '', s)
    s = s.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def textdiff(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [(a[i1:i2], b[j1:j2]) for o, i1, i2, j1, j2 in sm.get_opcodes() if o != 'equal']


def rule_texts(src):
    rules = E.rep_rules(E.cosmetics(E.parse_params(E.read_source(src).splitlines()[0])))
    froms = {f.strip() for f, t in rules if f.strip()}
    tos = {re.sub(r'<[^<>]*>', '', t).replace('_nbsp;', ' ').replace('_nbsp', ' ').strip()
           for f, t in rules}
    return froms, {t for t in tos if t}


def allowed(removed, added, froms, tos):
    removed, added = removed.strip(), added.strip()
    if removed:
        rest = removed
        for f in sorted(froms, key=len, reverse=True):
            rest = rest.replace(f, ' ')
        rest = re.sub(r'<[A-Za-z0-9~]+>', ' ', rest)
        if re.sub(r'[<>\s]', '', rest) and not all(any(p in f for f in froms)
                                                   for p in removed.split()):
            return False
    for t in sorted(tos, key=len, reverse=True):
        added = added.replace(t, ' ')        # a token repeated: '<QM><QM>' -> '??'
    return not added.strip() or all(any(p in t for t in tos) for p in added.split())


FX_TAG_RE = re.compile(r'<(/?)(b|strong|i|em|u|big|small|sup|sub)\b[^<>]*>', re.I)


def leaking_tags(line):
    """Formatting tags opened in an output line and not closed before text that follows
    them in the same line. Every Otzaria line stands alone, so such a tag is a
    formatting run that was cut at a line end instead of being closed and reopened."""
    def has_text(t):
        return bool(re.sub(r'<[^<>]*>', '', t).strip())
    stack, pos = [], 0
    for m in FX_TAG_RE.finditer(line):
        if has_text(line[pos:m.start()]):
            for t in stack:
                t[1] = True
        pos = m.end()
        name = EFFECT_TAGS[m.group(2).lower()]
        if m.group(1):
            for j in range(len(stack) - 1, -1, -1):
                if stack[j][0] == name:
                    del stack[j]
                    break
        else:
            stack.append([name, False])
    if has_text(line[pos:]):
        for t in stack:
            t[1] = True
    return [name for name, covers in stack if covers]


def rendered(html):
    """(text, [Counter of effects per char]) of a line as the reader shows it: a closer
    with no opener does nothing, and an opener left open runs to the end of the line.
    Written apart from parse_cur on purpose, so that --check does not trust the merge."""
    html = re.sub(r'</?(tex|teg)\b[^<>]*>', '', html)
    text, effs, stack, pos = [], [], [], 0
    def put(t):
        t = html_mod.unescape(re.sub(r'<[^<>]*>', '', t)).replace('\xa0', ' ')
        for ch in t:
            text.append(ch)
            effs.append(collections.Counter(stack))
    for m in FX_TAG_RE.finditer(html):
        put(html[pos:m.start()])
        pos = m.end()
        e = EFFECT_TAGS[m.group(2).lower()]
        if not m.group(1):
            stack.append(e)
        elif e in stack:
            del stack[len(stack) - 1 - stack[::-1].index(e)]
    put(html[pos:])
    return ''.join(text), effs


def foreign_effects(new_html, cur_line, out_line):
    """Formatting of out_line that is neither in the current line nor in the conversion
    of its source line: [(char index, effect)]. Text the merge kept from the current file
    only (no source text under it) may take the conversion's formatting of the text
    around it. Spaces are not checked: their formatting cannot be seen."""
    ot, oe = rendered(out_line)
    ct, ce = rendered(cur_line)
    nt, ne = rendered(new_html)
    cmap = {}
    for op, i1, i2, j1, j2 in align(ot, ct):
        if op == 'equal':
            cmap.update(zip(range(i1, i2), range(j1, j2)))
    nallow = [None] * len(ot)
    for op, i1, i2, j1, j2 in align(ot, nt):
        if op == 'equal':
            for i, j in zip(range(i1, i2), range(j1, j2)):
                nallow[i] = ne[j]
        elif i2 > i1:
            near = collections.Counter()
            for j in range(max(j1 - 1, 0), min(j2 + 1, len(nt))):
                near |= ne[j]
            for i in range(i1, i2):
                nallow[i] = near
    bad = []
    for i, ch in enumerate(ot):
        if ch.isspace():
            continue
        have = ce[cmap[i]] if i in cmap else collections.Counter()
        allow = have | (nallow[i] or collections.Counter())
        for e, n in oe[i].items():
            if n > allow[e]:
                bad.append((i, e))
    return bad


def nested_tags(line):
    """Effects opened again inside themselves in a line (<b>..<b>..</b>..</b>);
    only big/small nest meaningfully."""
    stack, out = [], []
    for m in FX_TAG_RE.finditer(line):
        e = EFFECT_TAGS[m.group(2).lower()]
        if m.group(1):
            if e in stack:
                del stack[len(stack) - 1 - stack[::-1].index(e)]
        else:
            if e in stack and e not in ('big', 'small') and e not in out:
                out.append(e)
            stack.append(e)
    return out


def allowlist(spec, name, width):
    """Entries of spec[name], each a list of `width` items: line numbers, then the tag."""
    out = []
    for ent in spec.get(name, []):
        if not isinstance(ent, list) or len(ent) != width:
            raise SystemExit(f'te_books.json: "{name}" entry {ent!r} must be a list of {width} items')
        out.append(tuple(ent))
    return out


def format_problems(conv, out, spec, max_carry, cur=None, new=None, pairs=None, unstable=()):
    """The formatting checks of --check. conv: the report of E.convert; cur, new, pairs:
    the current lines, the converted lines and report['pairs'] of merge_book."""
    probs = []
    # unclosed source tags: each must be listed in "unbalanced" as [source line, tag],
    # once for every such tag, and every entry must still match one
    found = collections.Counter((line, tag) for line, tag, effs, where in conv['unbalanced'])
    known = collections.Counter(allowlist(spec, 'unbalanced', 2))
    for line, tag, effs, where in conv['unbalanced']:
        if known[(line, tag)] < found[(line, tag)]:
            probs.append(f'source line {line}: <{tag}> ({"+".join(effs)}) is not closed '
                         + {'heading': 'before the heading after it', 'eof': 'by the end of the book',
                            'in heading': 'inside its heading'}[where])
    for (line, tag), n in (known - found).items():
        probs.append(f'te_books.json "unbalanced" {[line, tag]}: no such unclosed tag in the source'
                     + (f' ({n} listed beyond the {found[(line, tag)]} found)' if found[(line, tag)] else ''))
    # long carries: each one over max_carry source lines must be listed in "carried"
    spans = {(o, c, tag) for o, c, tag, effs in conv['carried']}
    listed = set(allowlist(spec, 'carried', 3))
    for o, c, tag, effs in conv['carried']:
        if c - o > max_carry and (o, c, tag) not in listed:
            probs.append(f'source lines {o}-{c}: <{tag}> ({"+".join(effs)}) runs over {c - o} lines')
    for ent in sorted(listed - spans):
        probs.append(f'te_books.json "carried" {list(ent)}: no such span in the source')
    # hand-fixed formatting: the line must still be the one that was fixed
    for line, snippet in allowlist(spec, 'keep', 2):
        if cur is not None and (line > len(cur) or snippet not in plain(cur[line - 1])):
            probs.append(f'te_books.json "keep" {[line, snippet]}: line {line} no longer has this text')
    for i, line in enumerate(out):
        for tag in leaking_tags(line):
            probs.append(f'line {i + 1}: <{tag}> is not closed at the end of the line')
    if cur is None:
        return probs
    for i in sorted(unstable):
        probs.append(f'line {i + 1}: a second run would change it again')
    for i, (c, o) in enumerate(zip(cur, out)):
        if c == o:
            continue
        for tag in nested_tags(o):
            probs.append(f'line {i + 1}: <{tag}> inside <{tag}>')
        if new is not None and pairs is not None and i in pairs:
            bad = foreign_effects(new[pairs[i]]['html'], c, o)
            if bad:
                effs = sorted({e for _, e in bad})
                probs.append(f'line {i + 1}: {len(bad)} chars get <{">, <".join(effs)}> '
                             'that neither the line nor the source has')
    return probs


def process(rel, spec, max_carry=10):
    path = os.path.join(BOOKS_ROOT, rel)
    raw = open(path, encoding='utf-8').read()
    bom = raw.startswith('\ufeff')
    cur = (raw[1:] if bom else raw).split('\n')
    trail = cur and cur[-1] == ''
    if trail:
        cur = cur[:-1]
    conv = {}
    _, new = E.convert(spec['src'], markers=True, report=conv)
    out, rep = merge_book(new, cur, heading_levels=spec.get('headings', 'cur'),
                          keep=[l for l, _ in allowlist(spec, 'keep', 2)])
    assert len(out) == len(cur)
    froms, tos = rule_texts(spec['src'])
    bad = [(i + 1, d, a) for i, (x, y) in enumerate(zip(cur, out))
           for d, a in textdiff(plain(x), plain(y)) if not allowed(d, a, froms, tos)]
    rep['format'] = format_problems(conv, out, spec, max_carry, cur, new, rep['pairs'], rep['unstable'])
    rep['unbalanced_known'] = conv['unbalanced'] if spec.get('unbalanced') else []
    text = ('\ufeff' if bom else '') + '\n'.join(out) + ('\n' if trail else '')
    return path, text, raw, rep, bad, sum(1 for x, y in zip(cur, out) if x != y)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--src', required=True, help='the Torat Emet books directory')
    ap.add_argument('--only', help='process only books whose path contains this')
    ap.add_argument('--max-carry', type=int, default=10, metavar='N',
                    help='fail when a formatting tag of the source runs over more than N source '
                         'lines and the span is not listed in the book\'s "carried" (default 10)')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check', action='store_true')
    g.add_argument('--write', action='store_true')
    a = ap.parse_args()
    E.SRC_ROOT = a.src
    books = json.load(open(os.path.join(HERE, 'te_books.json'), encoding='utf-8'))
    total = collections.Counter()
    failed = False
    for rel, spec in books.items():
        if a.only and a.only not in rel:
            continue
        path, text, raw, rep, bad, changed = process(rel, spec, a.max_carry)
        gen = sum(rep['generated'].values())
        con = sum(rep['consumed'].values())
        print(f'{rel}: {changed} lines changed, {con} tokens removed, {gen} rule texts added'
              + (f', {len(rep["unaligned_cur"])} lines left as is' if rep['unaligned_cur'] else '')
              + (f', {len(rep["unbalanced_known"])} known unbalanced source tags left literal'
                 if rep['unbalanced_known'] else ''))
        for k, v in list(rep['consumed'].items()) + list(rep['generated'].items()):
            total[k] += v
        if bad:
            failed = True
            print('  UNEXPECTED TEXT CHANGE:', bad[:10])
        if rep['format']:
            failed = True
            for p in rep['format'][:10]:
                print('  FORMATTING:', p)
            if len(rep['format']) > 10:
                print(f'  FORMATTING: ... {len(rep["format"]) - 10} more')
        if a.write and not bad and not rep['format'] and text != raw:
            open(path, 'w', encoding='utf-8').write(text)
    print('totals:', dict(total.most_common(25)))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
