"""Torat Emet -> Otzaria: conversion engine.

A Torat Emet book is cp1255 text. Its first line is a parameter line,
    &Key=Value&Key=Value...
and the parameter CosmeticsType carries the book's own rendering rules:
    #rep=FROM=TO^^FROM=TO#rep2=...   literal replacements, applied in order
    CosmeticsType==<UniqueId>        inherit the CosmeticsType of another book
The meaning of '[[', '{{', '((' ... is therefore different in every book: in
"בעניין מספר הפסוקים" '[[[' is an underlined big title, '[[' a small letter and
'[' a big letter; in חמדת ימים '((' is a boxed paragraph number and '[[' bold;
in Chavruta '<QM>' is a question mark. Never map a token without reading the rules.

Level sigils at the start of a line: '$' is the book title; '#', '^', '@', '~'
are TOC levels, '!' an inline label that is not a TOC entry. The default order
(Orayta htmlgen.cpp: LevelSigns = "!~@^#") is # > ^ > @ > ~, but books differ
(in מנורת המאור '^' is above '#'): pass `levels` when converting a new book.

Usage:
    python te_convert.py --src "<Torat Emet dir>" 042_IYUNIM/030_RavZilber1.txt -o out.txt
    python te_convert.py --src "<Torat Emet dir>" 042_IYUNIM/030_RavZilber1.txt --check
"""
import argparse
import base64
import sys
import html as html_mod
import json
import os
import re

SRC_ROOT = os.environ.get("TORAT_EMET_SRC", "")
CT_KEYS = ('rep|pr|MIX|is|bs|ip|su|sil|ix|nik|bp|cp|dii|rnft|irfb|cs|rus|sem|sp|rlp|rls|'
           'rnp|rns|eoi|ec|ti|orp|wp|inp|ins|id|ft|ap|mxp|eh|jjjj|dai|ddc|nts|nte|mbw|sis|'
           'download|njs|notes|ie|rsc|pomsip')
CT_KEY_RE = re.compile(r'#(' + CT_KEYS + r')(\d*)=')
LEVEL_RANK = {'#': 4, '^': 3, '@': 2, '~': 1, '!': 0}


def read_source(rel):
    return open(os.path.join(SRC_ROOT, rel), 'rb').read().decode('cp1255', errors='replace')


def parse_params(first_line):
    params = {}
    for m in re.finditer(r'&([A-Za-z]+)=(.*?)(?=&[A-Za-z]+=|$)', first_line):
        params[m.group(1)] = m.group(2)
    return params


_uid_index = None


def uid_index():
    """UniqueId -> source path, for CosmeticsType==<id> inheritance."""
    global _uid_index
    if _uid_index is None:
        _uid_index = {}
        for root, _, files in os.walk(SRC_ROOT):
            for f in files:
                if f.lower().endswith('.txt'):
                    p = os.path.join(root, f)
                    with open(p, 'rb') as fh:
                        first = fh.readline().decode('cp1255', errors='replace')
                    m = re.search(r'&UniqueId=(\d+)', first)
                    if m:
                        _uid_index.setdefault(m.group(1), os.path.relpath(p, SRC_ROOT))
    return _uid_index


def cosmetics(params, depth=0):
    ct = params.get('CosmeticsType', '')
    if ct.startswith('=') and depth < 5:
        ref = uid_index().get(ct[1:].strip())
        if ref:
            return cosmetics(parse_params(read_source(ref).splitlines()[0]), depth + 1)
        return {}
    out = {}
    marks = list(CT_KEY_RE.finditer(ct))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(ct)
        out.setdefault(m.group(1) + m.group(2), ct[m.end():end])
    return out


def rep_rules(ct):
    """Ordered (FROM, TO) list. Items inside one #rep are separated by ^^."""
    rules = []
    keys = [k for k in ct if re.fullmatch(r'rep\d*', k)]
    keys.sort(key=lambda k: int(k[3:] or 1))
    for k in keys:
        for item in ct[k].split('^^'):
            if '=' not in item:
                continue
            frm, to = item.split('=', 1)
            if frm:
                rules.append((frm, to))
    defined = {f for f, _ in rules}
    return rules + [(f, t) for f, t in FALLBACK_RULES if f not in defined]


# Tokens some books use without a rule of their own: the notes on Chavruta
# (HavTempNotes, CosmeticsType==2454) write '(' and ')' as SB and SE like HavAll does.
FALLBACK_RULES = [('SB', '('), ('SE', ')')]


# ---------------------------------------------------------------- replacements
PROTECT_BASE = 0xF0000  # supplementary private use plane: never in the sources


def apply_rules(text, rules, markers=True):
    """Sequential literal replace, like the Torat Emet engine.

    The tag parts of each replacement are swapped for private-use placeholders so a
    later rule cannot match inside markup an earlier rule produced (e.g. the '(' of
    RGB(...) in a style), while the text parts stay exposed so chained rules still
    work ('{ע} ' -> ' {ע}' and then '{ע}' -> image).
    """
    store = []

    def protect(to):
        def sub(m):
            store.append(m.group(0))
            return chr(PROTECT_BASE + len(store) - 1)
        return re.sub(r'<[^<>]*>', sub, to)

    def mark(frm, to):
        # <tex d=HEX> records the consumed source token; text produced by the rule
        # is wrapped in <teg>..</teg> so a merge can tell it from source text.
        parts = re.split(r'(<[^<>]*>)', to)
        body = ''.join(p if p.startswith('<') else (f'<teg>{p}</teg>' if p.strip() else p)
                       for p in parts if p)
        text = ''.join(p for p in parts if p and not p.startswith('<'))
        if frm in text:
            return body          # the token is re-emitted as is ('(' -> '<small>('): not consumed
        return f'<tex d="{frm.encode("utf-8").hex()}">' + body

    for frm, to in rules:
        if frm in text:
            text = text.replace(frm, protect(mark(frm, to) if markers else to))
    return re.sub('[\U000F0000-\U000FFFFD]', lambda m: store[ord(m.group(0)) - PROTECT_BASE], text)


# ---------------------------------------------------------------- pictures
PIC_RE = re.compile(r'<img\b[^<>]*?\bsrc\s*=\s*["\']?\.\.[/\\]Pics[/\\]([^"\'\s<>]+)["\']?[^<>]*>', re.I)
PIC_BASE = 0x100000    # plane 16: apart from PROTECT_BASE
PIC_MIME = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif'}


def find_pic(rel):
    """Path of Pics/<rel> next to the books directory, matching names case-insensitively
    ('6.jpg' is 6.JPG on disk), or None."""
    path = os.path.join(SRC_ROOT, '..', 'Pics')
    for part in re.split(r'[/\\]', rel):
        if not os.path.isdir(path):
            return None
        names = {n.lower(): n for n in os.listdir(path)}
        if part.lower() not in names:
            return None
        path = os.path.join(path, names[part.lower()])
    return path if os.path.isfile(path) else None


def pic_tag(rel):
    """The source picture as an inline data URI, or '' when it is missing."""
    path = find_pic(rel)
    mime = PIC_MIME.get(rel.rsplit('.', 1)[-1].lower())
    if not path or not mime:
        print(f'picture not found: Pics/{rel}', file=sys.stderr)
        return ''
    data = base64.b64encode(open(path, 'rb').read()).decode('ascii')
    return f'<img src="data:{mime};base64,{data}" style="max-width: 100%;"/>'


def hide_pics(line, pics):
    """Pictures of the source line itself (not those a rule makes) -> placeholders, so
    the rules cannot replace inside them; LineRenderer emits them as data-URI images."""
    def sub(m):
        pics.append(pic_tag(m.group(1)))
        return chr(PIC_BASE + len(pics) - 1)
    return PIC_RE.sub(sub, line)


def show_pics(text):
    return re.sub('[\U00100000-\U0010FFFD]', lambda m: f'<pic n={ord(m.group(0)) - PIC_BASE}>', text)


# ---------------------------------------------------------------- tag sanitizing
SIMPLE = {'b': 'b', 'strong': 'b', 'i': 'i', 'em': 'i', 'u': 'u', 'big': 'big', 'small': 'small',
          'sup': 'sup', 'sub': 'sub'}
DROP_WITH_CONTENT = {'script', 'style'}
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'col', 'wbr'}
TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9]*)([^<>]*)>')


def style_effects(attrs):
    eff = []
    m = re.search(r'font-size\s*:\s*(\d+)\s*%', attrs, re.I)
    if m:
        v = int(m.group(1))
        if v >= 115:
            eff.append('big')
        elif v <= 85:
            eff.append('small')
    if re.search(r'font-weight\s*:\s*bold', attrs, re.I):
        eff.append('b')
    if re.search(r'font-style\s*:\s*italic', attrs, re.I):
        eff.append('i')
    if re.search(r'text-decoration\s*:\s*underline', attrs, re.I):
        eff.append('u')
    return eff


def tag_effects(name, attrs):
    name = name.lower()
    eff = [SIMPLE[name]] if name in SIMPLE else []
    for e in style_effects(attrs):
        if e not in eff:
            eff.append(e)
    return eff


class LineRenderer:
    """Turns Torat Emet HTML (after rules) into balanced Otzaria lines.

    Open inline effects are carried across lines: closed at each line end and
    reopened at the next line start, because every Otzaria line stands alone (a
    quote or a parenthesis may run over two source lines). A carried effect must
    still be closed before the next heading, or at the latest by the paragraph right
    after it: convert() finds the openers that are not (`ignore`, keyed by (source
    line, tag index in the line)), and they render as if absent, so their text stays
    literal. One unbalanced '(' or '{' in the source would otherwise format the whole
    rest of the book.
    """

    def __init__(self, ignore=(), pics=()):
        self.pics = pics       # the source's pictures, by the n of their <pic n=..> placeholder
        self.stack = []        # (tagname, [effects], (source line, tag index)) for every open source tag
        self.skip = 0          # inside <script>
        self.ignore = set(ignore)
        self.closed = []       # (tagname, effects, opening (line, index), closing line) of every effect closed

    def active(self):
        out = []
        for _, effs, _ in self.stack:
            for e in effs:
                out.append(e)
        return out

    def render(self, line, lineno=None):
        out = []
        cur = []               # effects currently open in the output
        def sync(target):
            # close everything not a prefix, then open the rest
            i = 0
            while i < len(cur) and i < len(target) and cur[i] == target[i]:
                i += 1
            for e in reversed(cur[i:]):
                out.append(f'</{e}>')
            del cur[i:]
            for e in target[i:]:
                out.append(f'<{e}>')
                cur.append(e)
        pos = 0
        for k, m in enumerate(TAG_RE.finditer(line)):
            text = line[pos:m.start()]
            pos = m.end()
            if text and not self.skip:
                sync(self.dedupe(self.active()))
                out.append(text)
            closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
            if name in DROP_WITH_CONTENT:
                self.skip += -1 if closing else 1
                self.skip = max(self.skip, 0)
                continue
            if self.skip:
                continue
            if name == 'br' and not closing:
                sync(self.dedupe(self.active()))
                out.append('<br>')
                continue
            if name in ('tex', 'teg'):
                sync(self.dedupe(self.active()))
                out.append(m.group(0))
                continue
            if name == 'pic':
                pic = self.pics[int(attrs.split('=')[1])] if self.pics else ''
                if pic:
                    sync([])
                    out.append(pic)
                continue
            if name in VOID:
                continue
            if closing:
                for j in range(len(self.stack) - 1, -1, -1):
                    if self.stack[j][0] == name:
                        ent = self.stack.pop(j)
                        if ent[1]:
                            self.closed.append((ent[0], tuple(ent[1]), ent[2], lineno))
                        break
            elif (lineno, k) not in self.ignore:
                self.stack.append((name, tag_effects(name, attrs), (lineno, k)))
        text = line[pos:]
        if text and not self.skip:
            sync(self.dedupe(self.active()))
            out.append(text)
        sync([])
        return tidy(''.join(out))

    @staticmethod
    def dedupe(effs):
        # big/small nest meaningfully (<small><small> is smaller); the rest do not
        seen, out = set(), []
        for e in effs:
            if e in ('big', 'small') or e not in seen:
                seen.add(e)
                out.append(e)
        return out


def tidy(s):
    s = re.sub(r'_nbsp;?|&nbsp;', ' ', s).replace('\xa0', ' ')
    # drop empty elements and <br> at the edges of the line
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'<(\w+)>(\s*)</\1>', r'\2', s)
        s = re.sub(r'^(\s|<br>)+', '', s)
        s = re.sub(r'(\s|<br>)+$', '', s)
        s = re.sub(r'</(\w+)><\1>', '', s)       # merge adjacent same tags
    # move spaces outside tags
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'(<(?!/)[^<>]+>)( +)', r'\2\1', s)
        s = re.sub(r'( +)(</[^<>]+>)', r'\2\1', s)
    s = re.sub(r' {2,}', ' ', s).strip()
    return s


# ---------------------------------------------------------------- book conversion
SIGIL_RE = re.compile(r'^([$#^@~!])\s?(.*)$')


def strip_tags(s):
    return re.sub(r'<[^<>]*>', '', s)


def convert(rel, text=None, markers=False, levels=None, report=None):
    """Returns (params, lines); each line is a dict(src=index, kind, level, html).

    markers=True keeps <tex>/<teg> bookkeeping tags for te_reapply.py.
    levels: sigils from the top TOC level down, e.g. '^#@~' (default: Orayta order).
    report: a dict to fill with the source's formatting spans (source lines are 1-based):
        'carried':    (open line, close line, tag, effects) of every effect that runs
                      over more than one source line and is closed in time;
        'unbalanced': (open line, tag, effects, where) of every effect left open at a
                      heading ('heading'), at the end of the book ('eof') or at the end
                      of a heading line ('in heading'), rendered as if absent.
    """
    text = read_source(rel) if text is None else text
    raw = text.splitlines()
    params = parse_params(raw[0]) if raw and raw[0].startswith('&') else {}
    body_start = 1 if params else 0
    rules = rep_rules(cosmetics(params))
    body = raw[body_start:]
    # comments may span lines: blank them out, keeping the line count
    joined = '\n'.join(body)
    joined = re.sub(r'<!--.*?-->', lambda m: '\n' * m.group(0).count('\n'), joined, flags=re.S)
    # a closing tag that landed inside a token in the source itself: '<</b>QM>'
    joined = re.sub(r'<((?:</?[a-z]+>)+)([A-Z~][A-Z0-9]*)>', r'\1<\2>', joined)
    body = joined.split('\n')
    sigils = sorted({m.group(1) for l in body if (m := SIGIL_RE.match(l)) and m.group(1) in LEVEL_RANK
                     and not l.startswith('@PicWidth')}, key=lambda c: -LEVEL_RANK[c])
    if levels:
        sigils = [c for c in levels if c in sigils] + [c for c in sigils if c not in levels]
    level_of = {c: i + 2 for i, c in enumerate(s for s in sigils if s != '!')}
    items = []                 # (source line, sigil or None, html after the rules)
    pics = []
    for i, line in enumerate(body, start=body_start):
        line = line.strip()
        if not line or line.startswith('**INDEX_WRITE') or line.startswith('@PicWidth'):
            continue
        m = SIGIL_RE.match(line)
        if m:
            items.append((i, m.group(1), apply_rules(m.group(2), rules, markers)))
        else:
            items.append((i, None, show_pics(apply_rules(hide_pics(line, pics), rules, markers))))
    # first pass: find the source tags that have no closer. A heading is rendered on its
    # own, so nothing it opens or closes reaches the text around it. A tag still open
    # at a heading may only be closed by the first paragraph after it (a Chavruta quote
    # that runs over the page heading '~ דף נא - א'); otherwise, or at the end of the
    # book, it is unbalanced.
    probe, ignore, unbalanced = LineRenderer(), set(), []
    pending = None             # origins of the tags that were open at the last heading
    def drop(origins, where):
        for ent in [e for e in probe.stack if e[2] in origins]:
            probe.stack.remove(ent)
            ignore.add(ent[2])
            if ent[1]:
                unbalanced.append((ent[2][0] + 1, ent[0], tuple(ent[1]), where))
    for i, sig, h in items:
        if sig:
            if pending:
                drop(pending, 'heading')
            pending = {e[2] for e in probe.stack}
            hp = LineRenderer()
            hp.render(h, i)
            unbalanced += [(o[0] + 1, n, tuple(e), 'in heading') for n, e, o in hp.stack if e]
        else:
            probe.render(h, i)
            if pending:
                drop(pending, 'heading')
            pending = None
    drop({e[2] for e in probe.stack}, 'eof')
    if report is not None:
        report['unbalanced'] = sorted(unbalanced)
        report['carried'] = sorted((o[0] + 1, c + 1, n, e) for n, e, o, c in probe.closed if c > o[0])
    rend = LineRenderer(ignore, pics)
    out = []
    for i, sig, h in items:
        if sig:
            h = LineRenderer().render(h, i)
            h = tidy(html_mod.unescape(strip_tags(h)))
            if sig == '$':
                out.append(dict(src=i, kind='h', level=1, html=h))
            elif sig == '!':
                out.append(dict(src=i, kind='label', level=0, html=h))
            else:
                out.append(dict(src=i, kind='h', level=level_of[sig], html=h))
            continue
        h = rend.render(h, i)
        if h:
            out.append(dict(src=i, kind='p', level=0, html=h))
    return params, out


def to_text(lines):
    res = []
    for l in lines:
        if l['kind'] == 'h':
            res.append(f"<h{l['level']}>{l['html']}</h{l['level']}>")
        else:
            res.append(l['html'])
    return '\n'.join(res) + '\n'


def main():
    ap = argparse.ArgumentParser(description='Convert a Torat Emet book to Otzaria format')
    ap.add_argument('book', help='path of the book, relative to --src')
    ap.add_argument('--src', required=True, help='the Torat Emet books directory')
    ap.add_argument('-o', '--out', help='output file (default: stdout)')
    ap.add_argument('--levels', help="TOC sigils from the top level down, e.g. '^#@~'")
    ap.add_argument('--rules', action='store_true', help="print the book's rules and exit")
    ap.add_argument('--check', action='store_true',
                    help='list the formatting tags of the source that are not closed in their section '
                         'or that run over several lines, and exit (status 1 if any is not closed)')
    a = ap.parse_args()
    global SRC_ROOT
    SRC_ROOT = a.src
    if a.rules:
        params = parse_params(read_source(a.book).splitlines()[0])
        for frm, to in rep_rules(cosmetics(params)):
            print(f'{frm!r:>16} -> {to}')
        return
    if a.check:
        rep = {}
        convert(a.book, levels=a.levels, report=rep)
        for line, tag, effs, where in rep['unbalanced']:
            print(f'not closed ({where}): source line {line} <{tag}> {"+".join(effs)}')
        for o, c, tag, effs in sorted(rep['carried'], key=lambda x: x[0] - x[1])[:10]:
            print(f'over {c - o + 1} lines: source lines {o}-{c} <{tag}> {"+".join(effs)}')
        sys.exit(1 if rep['unbalanced'] else 0)
    _, lines = convert(a.book, levels=a.levels)
    text = to_text(lines)
    if a.out:
        open(a.out, 'w', encoding='utf-8').write(text)
    else:
        sys.stdout.write(text)


if __name__ == '__main__':
    main()
