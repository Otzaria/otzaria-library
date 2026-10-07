# docx -> Otzaria: base book + "הערות על" companion + footnotes links.
# usage: python3 convert.py <source.docx> <out_dir>
#   install target: MoreBooks/ספרים/אוצריא/שות/ראשונים/ (links -> MoreBooks/links/)
#   out_dir receives: ספר קושיות.txt, הערות על ספר קושיות.txt, ספר קושיות_links.json
# Word footnotes -> <sup>N</sup> (digits); Word endnotes (numFmt hebrew1) -> <sup>gematria</sup>.
# Both go, in call order, into one companion book merged by HearotCompanionMerge.
# docx paragraphs 0-2 precede the title heading (paragraph 3): 0 repeats the title
# and is dropped; 1-2 become gray lines under the title (library precedent markup).
import html, json, os, re, sys, zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
TITLE = 'ספר קושיות'
AUTHOR = 'אחד מן הראשונים'
NOTES = 'הערות על ' + TITLE
GRAY = '<span style="color:Gray;"><small><small>%s</small></small></span>'

def gematria(n):
    out = ''
    for v, c in ((400, 'ת'), (300, 'ש'), (200, 'ר'), (100, 'ק')):
        while n >= v:
            out += c; n -= v
    if n == 15: return out + 'טו'
    if n == 16: return out + 'טז'
    tens = ' יכלמנסעפצ'; ones = ' אבגדהוזחט'
    return out + tens[n // 10].strip() + ones[n % 10].strip()

def norm(s): return re.sub(r'\s+', ' ', s)

# NOTEREF field -> mark of the note it names, for fields saved without a result.
# Only a blank field after a space lacks its number; others are stray leftovers.
REFMARK = {}

def note_ref_marks(body):
    """_Ref bookmark name -> mark of the first note reference at/after its start."""
    pending, marks, fn_no, en_no = [], {}, 0, 0
    for x in body.iter():
        if x.tag == W + 'bookmarkStart' and x.get(W + 'name', '').startswith('_Ref'):
            pending.append(x.get(W + 'name'))
        elif x.tag in (W + 'footnoteReference', W + 'endnoteReference'):
            if x.tag == W + 'footnoteReference':
                fn_no += 1; mark = str(fn_no)
            else:
                en_no += 1; mark = gematria(en_no)
            for name in pending: marks.setdefault(name, mark)
            pending = []
    return marks

def runs_of(p):
    """(kind, text, bold) in document order; kind: t / fn / en."""
    out = []
    fld = None   # [instr, has_result] of the open field
    for r in p.iter(W + 'r'):
        rp = r.find(W + 'rPr')
        b = rp is not None and rp.find(W + 'b') is not None and \
            rp.find(W + 'b').get(W + 'val') not in ('0', 'false')
        for x in r:
            if x.tag == W + 't': out.append(('t', x.text or '', b))
            elif x.tag == W + 'tab': out.append(('t', ' ', b))
            elif x.tag == W + 'br': out.append(('t', ' ', b))
            elif x.tag == W + 'footnoteReference': out.append(('fn', x.get(W + 'id'), b))
            elif x.tag == W + 'endnoteReference': out.append(('en', x.get(W + 'id'), b))
            elif x.tag == W + 'instrText' and fld: fld[0] += x.text or ''
            elif x.tag == W + 'fldChar':
                t = x.get(W + 'fldCharType')
                if t == 'begin': fld = ['', False]
                elif t == 'separate' and fld: fld[1] = True
                elif t == 'end' and fld:
                    m = re.match(r'\s*NOTEREF\s+(\S+)', fld[0])
                    prev = ''.join(t for k, t, _ in out if k == 't')[-1:]
                    if m and not fld[1] and prev.isspace():
                        out.append(('t', REFMARK[m.group(1)], b))
                    fld = None
    return out

def render(items):
    """items: (text, bold) or ('<sup>', marker). Returns one clean line."""
    segs = []
    for t, b in items:
        if b == 'sup':
            segs.append([t, 'sup']); continue
        t = norm(t)
        if not t: continue
        if segs and segs[-1][1] == b: segs[-1][0] += t
        else: segs.append([t, b])
    out = ''
    for t, b in segs:
        if b == 'sup':
            out += '<sup>%s</sup>' % t; continue
        e = html.escape(t, quote=False)
        if b is True and e.strip():
            lead = e[:len(e) - len(e.lstrip())]; trail = e[len(e.rstrip()):]
            out += lead + '<b>' + e.strip() + '</b>' + trail
        else:
            out += e
    out = re.sub(r'</b>(\s*)<b>', r'\1', out)
    return re.sub(r'\s+', ' ', out).strip()

def notes_map(z, part, tag, reftag):
    root = ET.fromstring(z.read('word/%s.xml' % part))
    m = {}
    for n in root.findall(W + tag):
        if n.get(W + 'type'): continue
        paras = []
        for p in n.findall(W + 'p'):
            items = [(t, b) for k, t, b in runs_of(p) if k == 't']
            # drop the reference-mark run itself
            s = render(items)
            if s: paras.append(s)
        m[n.get(W + 'id')] = '<br>'.join(paras)
    return m

def main():
    src, out = sys.argv[1], sys.argv[2]
    z = zipfile.ZipFile(src)
    body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
    REFMARK.update(note_ref_marks(body))
    fns = notes_map(z, 'footnotes', 'footnote', 'footnoteRef')
    ens = notes_map(z, 'endnotes', 'endnote', 'endnoteRef')
    paras = [p for p in body.iter(W + 'p')]
    ptext = lambda p: norm(''.join(t for k, t, b in runs_of(p) if k == 't')).strip()
    assert ptext(paras[0]) == TITLE and ptext(paras[3]) == TITLE
    lines = ['<h1>%s</h1>' % TITLE, AUTHOR]
    for p in paras[1:3]:
        lines.append(GRAY % html.escape(ptext(p), quote=False))
    notes = ['<h1>%s</h1>' % NOTES]
    links = []
    fn_no = en_no = 0
    for p in paras[4:]:
        items, calls = [], []
        for k, t, b in runs_of(p):
            if k == 't': items.append((t, b)); continue
            if k == 'fn':
                fn_no += 1; mark = str(fn_no); txt = fns[t]
            else:
                en_no += 1; mark = gematria(en_no); txt = ens[t]
            items.append((mark, 'sup')); calls.append((mark, txt))
        s = render(items)
        if not s:
            assert not calls; continue
        lines.append(s)
        for mark, txt in calls:
            notes.append('<sup>%s</sup> %s' % (mark, txt))
            links.append({'line_index_1': len(lines), 'heRef_2': 'הערות',
                          'path_2': NOTES + '.txt', 'line_index_2': len(notes),
                          'Conection Type': 'footnotes'})
    assert fn_no == len(fns) and en_no == len(ens), (fn_no, len(fns), en_no, len(ens))
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, TITLE + '.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    open(os.path.join(out, NOTES + '.txt'), 'w', encoding='utf-8').write('\n'.join(notes) + '\n')
    with open(os.path.join(out, TITLE + '_links.json'), 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2); f.write('\n')
    print('base lines', len(lines), 'note lines', len(notes), 'links', len(links),
          'footnotes', fn_no, 'endnotes', en_no)

if __name__ == '__main__':
    main()
