# Char-level extraction of the Mishneh Halachos PDFs into logical-order visual lines, per column, in reading order.
import pymupdf,re,collections
BASE='/private/tmp/claude-501/-Users-david-Documents-otzaria-books-otzaria-library/4c8380de-bafb-4867-b3cc-dae974308691/scratchpad/pdf'
MIR=str.maketrans('()[]{}<>',')(][}{><')
_docs={}
def doc(v):
    if v not in _docs: _docs[v]=pymupdf.open(f'{BASE}/mh{v}.pdf')
    return _docs[v]
def dchar(ch,font):
    o=ord(ch)
    b=None
    if 0xF000<=o<=0xF0FF: b=o-0xF000
    elif 0xC0<=o<=0xFF and not font.startswith('Minion'): b=o
    if b is None: return ch,False
    try: c=bytes([b]).decode('cp1255')
    except: c='�'
    return c.translate(MIR),True
def page_lines(v,pn):
    """pn 1-based. returns list of dict(col,y,x0,x1,text,sizes,fonts) in reading order (right col then left col)."""
    p=doc(v)[pn-1]; W=p.rect.width; mid=W/2
    chars=[]
    for b in p.get_text('rawdict')['blocks']:
        for l in b.get('lines',[]):
            for s in l['spans']:
                for c in s['chars']:
                    if not c['c'].strip() and ord(c['c'])<0xF000: 
                        chars.append(dict(c=' ',x0=c['bbox'][0],x1=c['bbox'][2],y=c['origin'][1],font=s['font'],size=round(s['size'],1),leg=False,sp=True)); continue
                    t,leg=dchar(c['c'],s['font'])
                    if t==' ' : 
                        chars.append(dict(c=' ',x0=c['bbox'][0],x1=c['bbox'][2],y=c['origin'][1],font=s['font'],size=round(s['size'],1),leg=leg,sp=True)); continue
                    chars.append(dict(c=t,x0=c['bbox'][0],x1=c['bbox'][2],y=c['origin'][1],font=s['font'],size=round(s['size'],1),leg=leg,sp=False))
    # column: by char centre; full-width lines (headers) handled by y
    groups=[]
    for col in ('R','L'):
        cs=[c for c in chars if ((c['x0']+c['x1'])/2>=mid)==(col=='R')]
        cs.sort(key=lambda c:c['y'])
        rows=[]
        for c in cs:
            if rows and abs(c['y']-rows[-1][0])<=4.5: rows[-1][1].append(c)
            else: rows.append([c['y'],[c]])
        for y,rc in rows:
            groups.append((col,y,rc))
    out=[]
    for col,y,rc in groups:
        real=[c for c in rc if not c['sp']]
        if not real: continue
        rs=sorted(real,key=lambda c:-c['x1'])
        txt='';prev=None
        for c in rs:
            if prev is not None and prev['x0']-c['x1']>1.5: txt+=' '
            txt+=c['c']; prev=c
        # re-reverse digit / latin runs (they are LTR)
        txt=re.sub(r'[0-9A-Za-z][0-9A-Za-z.,/:]*[0-9A-Za-z]|[0-9A-Za-z]',lambda m:m.group(0)[::-1],txt)
        sz=collections.Counter(); fn=collections.Counter()
        for c in real: sz[c['size']]+=1; fn[c['font']]+=1
        out.append(dict(col=col,y=round(y,1),x0=round(min(c['x0'] for c in real),1),x1=round(max(c['x1'] for c in real),1),text=re.sub(' +',' ',txt).strip(),sizes=dict(sz),fonts=dict(fn),W=p.rect.width,H=p.rect.height))
    return out
